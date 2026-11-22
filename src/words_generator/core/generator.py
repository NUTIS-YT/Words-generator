from __future__ import annotations

import threading
import time
from collections.abc import Callable
from typing import Protocol

from words_generator.api.client import APIError
from words_generator.core.prompts import build_user_prompt
from words_generator.core.word_validator import WordValidationError, normalize_word, word_key
from words_generator.models.generation import GenerationStats
from words_generator.models.project import ProjectSettings
from words_generator.models.sampling import SamplingSettings
from words_generator.storage.project_store import ProjectStore


class WordClient(Protocol):
    def generate_word(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        sampling: SamplingSettings,
    ) -> str: ...


EventCallback = Callable[[str, dict[str, object]], None]
StatsCallback = Callable[[GenerationStats], None]


class GenerationEngine:
    """Generate until the requested number of NEW unique words has been saved.

    API request count is diagnostic only. Duplicate and malformed model responses
    never consume the target; they are rejected and followed by another request.
    """

    def __init__(
        self,
        client: WordClient,
        store: ProjectStore,
        settings: ProjectSettings,
        *,
        stop_event: threading.Event | None = None,
        pause_event: threading.Event | None = None,
        event_callback: EventCallback | None = None,
        stats_callback: StatsCallback | None = None,
    ) -> None:
        settings.validate()
        self.client = client
        self.store = store
        self.settings = settings
        self.stop_event = stop_event or threading.Event()
        # Set means paused. Clear means running.
        self.pause_event = pause_event or threading.Event()
        self.event_callback = event_callback or (lambda *_: None)
        self.stats_callback = stats_callback or (lambda *_: None)

    def _event(self, event: str, **payload: object) -> None:
        self.store.append_event(event, payload)
        self.event_callback(event, payload)

    def _wait_if_paused(self, stats: GenerationStats) -> bool:
        while self.pause_event.is_set() and not self.stop_event.is_set():
            if stats.status != "paused":
                stats.status = "paused"
                stats.message = "Generation paused."
                self._event("generation_paused", added=stats.added, target=stats.target)
                self.stats_callback(stats)
            self.stop_event.wait(0.1)
        if self.stop_event.is_set():
            return False
        if stats.status == "paused":
            stats.status = "running"
            stats.message = "Generation resumed."
            self._event("generation_resumed", added=stats.added, target=stats.target)
            self.stats_callback(stats)
        return True

    def _request_candidate(self, stats: GenerationStats, user_prompt: str) -> str | None:
        """Make one successful model request, retrying only transport/API failures.

        Duplicate and invalid responses are handled by the outer generation loop
        and do not count as request failures.
        """
        for retry_index in range(self.settings.max_request_retries + 1):
            if not self._wait_if_paused(stats) or self.stop_event.is_set():
                return None

            stats.api_requests += 1
            request_number = stats.api_requests
            request_started = time.monotonic()
            self._event("api_request", request_number=request_number, retry=retry_index)
            try:
                raw = self.client.generate_word(
                    system_prompt=self.settings.system_prompt,
                    user_prompt=user_prompt,
                    sampling=self.settings.sampling,
                )
                stats.total_latency_seconds += time.monotonic() - request_started
                self.stats_callback(stats)
                return raw
            except APIError as exc:
                stats.total_latency_seconds += time.monotonic() - request_started
                stats.api_errors += 1
                self._event("api_error", message=str(exc), retry=retry_index)
                self.stats_callback(stats)
                if retry_index >= self.settings.max_request_retries:
                    stats.status = "error"
                    stats.message = str(exc)
                    return None

                delay = min(8.0, 0.5 * (2**retry_index))
                if self.stop_event.wait(delay):
                    return None
        return None

    def run(self) -> GenerationStats:
        stats = GenerationStats(target=self.settings.target_words)
        session_id = self.store.start_session(
            {
                "target_unique_words": self.settings.target_words,
                "settings": self.settings.to_dict(),
            }
        )
        started = time.monotonic()
        self._event(
            "generation_started",
            session_id=session_id,
            target_unique_words=stats.target,
            existing_project_words=self.store.word_count,
        )
        self.stats_callback(stats)
        user_prompt = build_user_prompt(self.settings.language, self.settings.part_of_speech)

        # Only successfully persisted unique words advance stats.added.
        # Duplicates and invalid responses are retried without an attempt cap:
        # RUN ends only at the unique-word target, user stop, or API failure.
        while stats.added < stats.target:
            if not self._wait_if_paused(stats):
                stats.status = "stopped"
                stats.message = "Generation stopped by the user."
                break

            raw = self._request_candidate(stats, user_prompt)
            if raw is None:
                if self.stop_event.is_set():
                    stats.status = "stopped"
                    stats.message = "Generation stopped by the user."
                elif stats.status != "error":
                    stats.status = "stopped"
                    stats.message = "Generation stopped."
                break

            try:
                candidate = normalize_word(raw)
            except WordValidationError as exc:
                stats.invalid_responses += 1
                self._event(
                    "invalid_response",
                    reason=str(exc),
                    response=raw[:120],
                    added=stats.added,
                    target=stats.target,
                )
                self.stats_callback(stats)
                continue

            candidate_key = word_key(candidate)
            if candidate_key in self.store.word_keys:
                stats.duplicates += 1
                self._event(
                    "duplicate_rejected",
                    word=candidate,
                    added=stats.added,
                    target=stats.target,
                )
                self.stats_callback(stats)
                continue

            if not self.store.add_word(candidate):
                # The store rechecks uniqueness immediately before writing.
                stats.duplicates += 1
                self._event(
                    "duplicate_rejected",
                    word=candidate,
                    added=stats.added,
                    target=stats.target,
                )
                self.stats_callback(stats)
                continue

            stats.added += 1
            self._event(
                "word_accepted",
                word=candidate,
                unique_words_added=stats.added,
                target_unique_words=stats.target,
            )
            self.store.save_checkpoint(
                {
                    "session_id": session_id,
                    "target_unique_words": stats.target,
                    "unique_words_added": stats.added,
                    "stats": stats.to_dict(),
                    "settings": self.settings.to_dict(),
                    "status": "running",
                }
            )
            self.stats_callback(stats)

        if stats.status == "running" or stats.status == "paused":
            stats.status = "completed" if stats.added >= stats.target else "stopped"

        elapsed = time.monotonic() - started
        if not stats.message:
            stats.message = (
                f"Saved {stats.added} of {stats.target} requested unique words "
                f"in {elapsed:.1f} seconds."
            )
        self.store.save_checkpoint(
            {
                "session_id": session_id,
                "target_unique_words": stats.target,
                "unique_words_added": stats.added,
                "stats": stats.to_dict(),
                "settings": self.settings.to_dict(),
                "status": stats.status,
                "elapsed_seconds": elapsed,
            }
        )
        self._event(
            "generation_finished",
            status=stats.status,
            unique_words_added=stats.added,
            target_unique_words=stats.target,
            api_requests=stats.api_requests,
            duplicates_rejected=stats.duplicates,
            elapsed=elapsed,
        )
        self.store.finish_session(session_id, stats.to_dict(), elapsed)
        self.stats_callback(stats)
        return stats
