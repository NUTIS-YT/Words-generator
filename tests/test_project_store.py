from pathlib import Path

import pytest

from words_generator.models.project import ProjectSettings
from words_generator.storage.project_store import ProjectError, ProjectStore


def test_create_append_deduplicate_and_reopen(tmp_path: Path) -> None:
    project_path = tmp_path / "vocabulary"
    store = ProjectStore.create(project_path, ProjectSettings(name="Vocabulary"))

    assert store.add_word("Apple") is True
    assert store.add_word(" apple. ") is False
    assert store.add_word("mother-in-law") is True
    assert store.word_count == 2
    assert (project_path / "words.txt").read_text(encoding="utf-8") == "Apple\nmother-in-law\n"

    reopened = ProjectStore.open(project_path)
    assert reopened.word_count == 2
    assert reopened.add_word("APPLE") is False


def test_refuses_nonempty_directory(tmp_path: Path) -> None:
    project_path = tmp_path / "not-empty"
    project_path.mkdir()
    (project_path / "important.txt").write_text("keep", encoding="utf-8")
    with pytest.raises(ProjectError):
        ProjectStore.create(project_path, ProjectSettings())
    assert (project_path / "important.txt").read_text(encoding="utf-8") == "keep"


def test_checkpoint_is_written_atomically(tmp_path: Path) -> None:
    store = ProjectStore.create(tmp_path / "project", ProjectSettings())
    store.save_checkpoint({"status": "running", "added": 2})
    assert store.load_checkpoint() == {
        "status": "running",
        "added": 2,
        "updated_at": store.load_checkpoint()["updated_at"],
    }
