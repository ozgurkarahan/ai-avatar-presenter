"""Tests for UC2 avatar gesture selection."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.avatar import build_ssml, semantic_gesture_for


def test_lisa_intro_uses_baseline_opening_gesture() -> None:
    assert semantic_gesture_for(
        "lisa",
        "Welcome to this decarbonization overview.",
        slide_index=0,
        intro=True,
    ) == "show-front-1"


def test_lisa_numbered_steps_use_numeric_gestures() -> None:
    assert semantic_gesture_for("lisa", "First, reduce energy demand.", slide_index=1) == "numeric1-left-1"
    assert semantic_gesture_for("lisa", "Second, electrify processes.", slide_index=2) == "numeric2-left-1"
    assert semantic_gesture_for("lisa", "Third, optimize procurement.", slide_index=3) == "numeric3-left-1"


def test_lisa_question_and_benefit_use_semantic_gestures() -> None:
    assert semantic_gesture_for("lisa", "Why is this challenge important?", slide_index=1) == "think-twice-1"
    assert semantic_gesture_for("lisa", "The benefit is measurable CO2 reduction.", slide_index=2) == "thumbsup-left-1"


def test_lisa_default_rotates_show_front_gestures() -> None:
    assert semantic_gesture_for("lisa", "This slide explains the roadmap.", slide_index=1) == "show-front-3"


def test_harry_intro_uses_hello() -> None:
    assert semantic_gesture_for("harry", "Welcome.", slide_index=0, intro=True) == "hello"


def test_harry_business_falls_back_to_introduce() -> None:
    assert semantic_gesture_for("harry", "This slide explains the roadmap.", slide_index=1) == "introduce"


def test_plan_gestures_emits_one_per_sentence_with_max() -> None:
    from services.avatar import plan_gestures

    plan = plan_gestures(
        "lisa",
        "First, energy efficiency. The benefit is measurable. Why does it matter?",
        slide_index=0,
        intro=True,
        max_gestures=3,
    )
    # Slot 0 is the intro gesture (intro=True wins over keyword 'first').
    assert plan[0] == "show-front-1"
    assert plan[1] == "thumbsup-left-1"
    assert plan[2] == "think-twice-1"


def test_plan_gestures_avoids_duplicate_neighbours() -> None:
    from services.avatar import plan_gestures

    plan = plan_gestures(
        "lisa",
        "Slide one detail. Slide two detail. Slide three detail.",
        slide_index=0,
        intro=False,
        max_gestures=3,
    )
    assert all(plan[i] != plan[i - 1] for i in range(1, len(plan)) if plan[i])


def test_plan_gestures_lisa_technical_sitting_uses_pointing() -> None:
    from services.avatar import AVATAR_STYLES, plan_gestures

    AVATAR_STYLES["lisa"] = "technical-sitting"
    try:
        plan = plan_gestures(
            "lisa",
            "Look here. This is the right side. The left part shows risks.",
            slide_index=0,
            intro=False,
            max_gestures=3,
        )
        assert plan[0]  # not empty
        # All technical-sitting gestures should be in the supported set.
        from services.avatar import AVATAR_GESTURES
        supported = AVATAR_GESTURES[("lisa", "technical-sitting")]
        for g in plan:
            assert g in supported
    finally:
        AVATAR_STYLES["lisa"] = "casual-sitting"


def test_build_ssml_aligns_gestures_to_sentences() -> None:
    ssml = build_ssml(
        "Welcome here. The second step is energy efficiency.",
        "en-US",
        voice="en-US-Ava:DragonHDLatestNeural",
        gesture_names=["show-front-1", "numeric2-left-1"],
    )
    assert "<bookmark mark='gesture.show-front-1'/>Welcome here." in ssml
    assert "<bookmark mark='gesture.numeric2-left-1'/>The second step" in ssml


def test_build_ssml_rejects_unsafe_gesture_names() -> None:
    ssml = build_ssml(
        "Hello world.",
        "en-US",
        voice="en-US-Ava:DragonHDLatestNeural",
        gesture_names=["bad name'/><script>"],
    )
    assert "<bookmark" not in ssml
    assert "Hello world." in ssml


def test_build_ssml_injects_explicit_gesture_without_escaping_text() -> None:
    ssml = build_ssml(
        "CO2 reduction & materials efficiency",
        "en-US",
        voice="en-US-Ava:DragonHDLatestNeural",
        gesture_name="thumbsup-left-1",
    )
    assert "<bookmark mark='gesture.thumbsup-left-1'/>" in ssml
    assert "CO2 reduction &amp; materials efficiency" in ssml
