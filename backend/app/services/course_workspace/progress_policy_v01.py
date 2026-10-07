"""Deterministic next step per topic from practice observed in URPP (docs/33 §4).

Observations are not mastery evidence (docs/27, decision 1): a correct answer
cannot rule out help from outside URPP. They only steer the next teaching step.
Thresholds are engineering defaults, not validated learning science.
"""

from __future__ import annotations

from app.services.decision.models_v01 import TeachingActionV01

PRACTICED_DISTINCT_ITEMS_V01 = 2
STRUGGLING_ERRORS_V01 = 2

REASONS_V01 = {
    "prerequisite_not_practiced":
        "This topic builds on an earlier topic you have not practiced yet.",
    "topic_not_started": "You have not studied this topic yet.",
    "no_practice_evidence":
        "You have studied the lesson but not answered a check question yet.",
    "repeated_errors":
        "You missed two check questions in a row, so re-reading the lesson comes first.",
    "recent_error":
        "Your last answer was not correct. Try another question; a hint is available.",
    "assisted_success_needs_unassisted_check":
        "You got it right after a hint or solution. Try a new question without help.",
    "single_success_needs_confirmation":
        "One correct answer without help. One more new question will confirm it.",
    "ready_for_next_topic":
        "You answered two different questions correctly without help. Move on.",
    "course_practiced": "You have practiced every topic in this course path.",
}


def summarize_topic_v01(topic_id: str, attempts: list[dict], events: list[dict]) -> dict:
    mine = [a for a in attempts if a["topic_id"] == topic_id]
    opened = any(e["topic_id"] == topic_id and e["kind"] == "lesson_opened" for e in events)
    unassisted_items = {
        a["item_id"] for a in mine
        if a["correct"] and not a["hint_shown"] and not a["solution_shown"]
    }
    errors = sum(1 for a in mine if not a["correct"])
    last = mine[-1] if mine else None
    trailing_errors = 0
    for attempt in reversed(mine):
        if attempt["correct"]:
            break
        trailing_errors += 1
    # Re-opening the lesson after the latest miss counts as having re-studied.
    restudied = last is not None and any(
        e["topic_id"] == topic_id and e["kind"] == "lesson_opened"
        and e["occurred_at"] > last["submitted_at"] for e in events
    )
    if len(unassisted_items) >= PRACTICED_DISTINCT_ITEMS_V01:
        status = "practiced"
    elif not opened and not mine:
        status = "not_started"
    elif trailing_errors >= STRUGGLING_ERRORS_V01:
        status = "struggling"
    else:
        status = "learning"
    return {
        "topic_id": topic_id,
        "status": status,
        "lesson_opened": opened,
        "attempts": len(mine),
        "correct_unassisted_items": len(unassisted_items),
        "correct_assisted": sum(
            1 for a in mine if a["correct"] and (a["hint_shown"] or a["solution_shown"])
        ),
        "incorrect": errors,
        "consecutive_errors": trailing_errors,
        "restudied_after_last_error": restudied,
        "last_attempt": (
            None if last is None else {
                "correct": bool(last["correct"]),
                "assisted": bool(last["hint_shown"] or last["solution_shown"]),
            }
        ),
    }


def _step(code: str, action: TeachingActionV01, topic_id: str, kind: str) -> dict:
    return {
        "reason_code": code,
        "reason": REASONS_V01[code],
        "teaching_action": action.value,
        "step": kind,
        "topic_id": topic_id,
        "policy_version": "course-practice-policy-v0.1",
    }


def next_step_v01(outline: dict, topic_id: str, summaries: dict[str, dict]) -> dict:
    topics = {topic["topic_id"]: topic for topic in outline["topics"]}
    topic = topics[topic_id]
    for prerequisite in topic["prerequisite_topic_ids"]:
        if prerequisite in summaries and summaries[prerequisite]["status"] != "practiced":
            return _step("prerequisite_not_practiced", TeachingActionV01.CONCEPTUAL_REVIEW,
                         prerequisite, "go_to_topic")
    summary = summaries[topic_id]
    last = summary["last_attempt"]
    if summary["status"] == "practiced":
        for candidate in sorted(outline["topics"], key=lambda t: t["order"]):
            if summaries[candidate["topic_id"]]["status"] != "practiced":
                return _step("ready_for_next_topic", TeachingActionV01.CONCEPTUAL_REVIEW,
                             candidate["topic_id"], "go_to_topic")
        return _step("course_practiced", TeachingActionV01.SELF_EXPLANATION,
                     topic_id, "review_course")
    if not summary["lesson_opened"]:
        return _step("topic_not_started", TeachingActionV01.CONCEPTUAL_REVIEW,
                     topic_id, "study_lesson")
    if last is None:
        return _step("no_practice_evidence", TeachingActionV01.DIAGNOSTIC_ASSESSMENT,
                     topic_id, "answer_check")
    if not last["correct"]:
        if (summary["consecutive_errors"] >= STRUGGLING_ERRORS_V01
                and not summary["restudied_after_last_error"]):
            return _step("repeated_errors", TeachingActionV01.CONCEPTUAL_REVIEW,
                         topic_id, "study_lesson")
        return _step("recent_error", TeachingActionV01.CONCEPTUAL_HINT,
                     topic_id, "answer_check")
    if last["assisted"]:
        return _step("assisted_success_needs_unassisted_check",
                     TeachingActionV01.INDEPENDENT_PRACTICE, topic_id, "answer_check")
    return _step("single_success_needs_confirmation",
                 TeachingActionV01.INDEPENDENT_PRACTICE, topic_id, "answer_check")


def recommended_topic_v01(outline: dict, summaries: dict[str, dict]) -> str:
    """The first topic in path order that is not yet practiced."""
    for topic in sorted(outline["topics"], key=lambda t: t["order"]):
        if summaries[topic["topic_id"]]["status"] != "practiced":
            return topic["topic_id"]
    return outline["topics"][-1]["topic_id"]
