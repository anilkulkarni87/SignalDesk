from __future__ import annotations

from pathlib import Path

from course.tools.audit import REQUIRED_SECTIONS, audit_curriculum
from course.tools.checks import check_lesson
from course.tools.learning import (
    ROOT,
    empty_progress,
    load_curriculum,
    load_progress,
    main,
    save_progress,
)


AVAILABLE_LESSONS = {"01", "02", "04", "06", "10", "18"}


def test_curriculum_maps_all_18_lessons_and_six_pilot_guides() -> None:
    curriculum = load_curriculum()
    assert [lesson["id"] for lesson in curriculum["lessons"]] == [
        f"{number:02d}" for number in range(1, 19)
    ]
    available = {
        lesson["id"]
        for lesson in curriculum["lessons"]
        if lesson["status"] == "available"
    }
    assert available == AVAILABLE_LESSONS


def test_available_lessons_follow_the_learning_contract() -> None:
    curriculum = load_curriculum()
    for lesson in curriculum["lessons"]:
        if lesson["status"] != "available":
            continue
        content = (ROOT / lesson["lesson_path"]).read_text(encoding="utf-8")
        assert "Learning scope" in content
        assert "synthetic" in content.lower()
        for heading in REQUIRED_SECTIONS:
            assert heading in content, (lesson["id"], heading)


def test_curriculum_audit_has_no_structural_or_link_errors() -> None:
    assert audit_curriculum(ROOT, load_curriculum()) == []


def test_frozen_pilot_evidence_passes_without_model_calls() -> None:
    for lesson_id in sorted(AVAILABLE_LESSONS):
        assert check_lesson(ROOT, lesson_id)


def test_progress_round_trip(tmp_path: Path) -> None:
    curriculum = load_curriculum()
    progress = empty_progress()
    progress["lessons"]["01"] = {
        "status": "complete",
        "reflection": "The workflow hypothesis must precede a model choice.",
    }
    path = tmp_path / "LEARNING.md"
    save_progress(curriculum, progress, path)
    restored = load_progress(path)
    assert restored["lessons"]["01"]["status"] == "complete"
    assert "Available pilot lessons completed: **1/6**" in path.read_text(
        encoding="utf-8"
    )


def test_cli_start_check_and_complete_keep_reflection_separate(
    tmp_path: Path,
    monkeypatch,
) -> None:
    progress_file = tmp_path / "LEARNING.md"
    monkeypatch.setenv("SIGNALDESK_LEARNING_FILE", str(progress_file))

    assert main(["start", "01"]) == 0
    started = load_progress(progress_file)
    assert started["lessons"]["01"]["status"] == "in_progress"
    assert "verified_at" not in started["lessons"]["01"]

    assert main(["check", "01"]) == 0
    verified = load_progress(progress_file)
    assert verified["lessons"]["01"]["status"] == "in_progress"
    assert verified["lessons"]["01"]["verified_at"]

    reflection = "I can separate the workflow hypothesis from the model choice."
    assert main(["complete", "01", "--reflection", reflection]) == 0
    completed = load_progress(progress_file)
    assert completed["lessons"]["01"]["status"] == "complete"
    assert completed["lessons"]["01"]["reflection"] == reflection


def test_cli_rejects_completion_before_verification(
    tmp_path: Path,
    monkeypatch,
) -> None:
    progress_file = tmp_path / "LEARNING.md"
    monkeypatch.setenv("SIGNALDESK_LEARNING_FILE", str(progress_file))
    assert main(["start", "02"]) == 0
    assert main(
        [
            "complete",
            "02",
            "--reflection",
            "Synthetic truth must remain outside the serving contract.",
        ]
    ) == 1
