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
    """Generate one candidate per API request and persist accepted words immediately."""

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
                self._event("generation_paused")
                self.stats_callback(stats)
            self.stop_event.wait(0.1)
        if self.stop_event.is_set():
            return False
        if stats.status == "paused":
            stats.status = "running"
            stats.message = "Generation resumed."
            self._event("generation_resumed")
            self.stats_callback(stats)
        return True

    def run(self) -> GenerationStats:
        stats = GenerationStats(target=self.settings.target_words)
        session_id = self.store.start_session(
            {
                "target": self.settings.target_words,
                "settings": self.settings.to_dict(),
            }
        )
        started = time.monotonic()
        self._event("generation_started", session_id=session_id, target=stats.target)
        self.stats_callback(stats)
        user_prompt = build_user_prompt(self.settings.language, self.settings.part_of_speech)

        while stats.added < stats.target:
            if not self._wait_if_paused(stats):
                stats.status = "stopped"
                stats.message = "Generation stopped by the user."
                break

            accepted_this_slot = False
            attempts = 0
            while attempts < self.settings.max_attempts_per_word:
                if self.stop_event.is_set():
                    break
                if not self._wait_if_paused(stats):
                    break
                attempts += 1
                request_succeeded = False
                for retry_index in range(self.settings.max_request_retries + 1):
                    if not self._wait_if_paused(stats):
                        break
                    if self.stop_event.is_set():
                        break
                    stats.api_requests += 1
                    request_started = time.monotonic()
                    self._event("api_request", attempt=attempts, retry=retry_index)
                    try:
                        raw = self.client.generate_word(
                            system_prompt=self.settings.system_prompt,
                            user_prompt=user_prompt,
                            sampling=self.settings.sampling,
                        )
                        stats.total_latency_seconds += time.monotonic() - request_started
                        request_succeeded = True
                        break
                    except APIError as exc:
                        stats.total_latency_seconds += time.monotonic() - request_started
                        stats.api_errors += 1
                        self._event("api_error", message=str(exc), retry=retry_index)
                        self.stats_callback(stats)
                        if retry_index >= self.settings.max_request_retries:
                            stats.status = "error"
                            stats.message = str(exc)
                            break
                        delay = min(8.0, 0.5 * (2**retry_index))
                        if self.stop_event.wait(delay):
                            break
                self.stats_callback(stats)
                if not request_succeeded:
                    if stats.status == "error" or self.stop_event.is_set():
                        break
                    continue

                try:
                    candidate = normalize_word(raw)
                except WordValidationError as exc:
                    stats.invalid_responses += 1
                    self._event("invalid_response", reason=str(exc), response=raw[:120])
                    self.stats_callback(stats)
                    continue

                candidate_key = word_key(candidate)
                if candidate_key in self.store.word_keys:
                    stats.duplicates += 1
                    self._event("duplicate_rejected", word=candidate)
                    self.stats_callback(stats)
                    continue

                if not self.store.add_word(candidate):
                    # The store rechecks uniqueness immediately before writing.
                    stats.duplicates += 1
                    self._event("duplicate_rejected", word=candidate)
                    self.stats_callback(stats)
                    continue

                stats.added += 1
                accepted_this_slot = True
                self._event("word_accepted", word=candidate, added=stats.added, target=stats.target)
                self.store.save_checkpoint(
                    {
                        "session_id": session_id,
                        "target": stats.target,
                        "added": stats.added,
                        "stats": stats.to_dict(),
                        "settings": self.settings.to_dict(),
                        "status": "running",
                    }
                )
                self.stats_callback(stats)
                break

            if stats.status == "error" or self.stop_event.is_set():
                break
            if not accepted_this_slot:
                stats.status = "stalled"
                stats.message = (
                    f"Could not obtain a new unique word after "
                    f"{self.settings.max_attempts_per_word} attempts."
                )
                self._event("generation_stalled", attempts=self.settings.max_attempts_per_word)
                break

        if stats.status == "running" or stats.status == "paused":
            stats.status = "completed" if stats.added >= stats.target else "stopped"
        elapsed = time.monotonic() - started
        stats.message = stats.message or f"Finished in {elapsed:.1f} seconds."
        self.store.save_checkpoint(
            {
                "session_id": session_id,
                "target": stats.target,
                "added": stats.added,
                "stats": stats.to_dict(),
                "settings": self.settings.to_dict(),
                "status": stats.status,
                "elapsed_seconds": elapsed,
            }
        )
        self._event("generation_finished", status=stats.status, added=stats.added, elapsed=elapsed)
        self.store.finish_session(session_id, stats.to_dict(), elapsed)
        self.stats_callback(stats)
        return stats
