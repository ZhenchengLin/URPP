"""Offline tests for the developer-only NanoJev Evaluation Runner."""

import math

import pytest

from app.services.course_knowledge.nanojev_local_eval_v01 import (
    answer_from_scores_v01,
    build_eval_cases_v01,
    encode_choice_v01,
)


class DummyTokenizer:
    eos_token_id = 151645

    def __init__(self):
        self.calls = []

    def encode(self, text, add_special_tokens=False):
        assert add_special_tokens is False
        self.calls.append(text)
        return list(text.encode("utf-8"))


def test_exactly_eight_fixed_cases():
    cases = build_eval_cases_v01()

    assert len(cases) == 8

    assert {
        (case["focus_id"], case["candidate_order"], case["repeat"])
        for case in cases
    } == {
        (focus, order, repeat)
        for focus in ("sign_relation", "calculation")
        for order in ("original", "reversed")
        for repeat in (1, 2)
    }


@pytest.mark.parametrize(
    "focus,plan,check",
    [
        ("sign_relation", "sign_first", "ask_sign_relation"),
        ("calculation", "calculation_first", "ask_row_operation"),
    ],
)
def test_registered_pilot_reference(focus, plan, check):
    cases = [
        case
        for case in build_eval_cases_v01()
        if case["focus_id"] == focus
    ]

    assert len(cases) == 4

    for case in cases:
        assert case["registered_pilot"] == {
            "plan_id": plan,
            "check_id": check,
        }


def test_reversed_order_preserves_candidate_identity():
    cases = build_eval_cases_v01()

    original = cases[0]["request"]["states"][0]["questions"]
    reversed_questions = cases[2]["request"]["states"][0]["questions"]

    for question_id in ("teaching_plan", "follow_up_check"):
        original_ids = list(original[question_id]["criteria"])
        reversed_ids = list(reversed_questions[question_id]["criteria"])

        assert reversed_ids == list(reversed(original_ids))

        assert original[question_id]["criteria"] == (
            reversed_questions[question_id]["criteria"]
        )


def test_case_requests_do_not_share_mutable_dictionaries():
    cases = build_eval_cases_v01()

    first = cases[0]["request"]["states"][0]["questions"]
    second = cases[1]["request"]["states"][0]["questions"]

    first["teaching_plan"]["criteria"]["sign_first"] = "CHANGED"

    assert (
        second["teaching_plan"]["criteria"]["sign_first"]
        != "CHANGED"
    )


def test_candidate_segments_are_encoded_separately():
    question = (
        build_eval_cases_v01()[0]
        ["request"]["states"][0]["questions"]["teaching_plan"]
    )

    tokenizer = DummyTokenizer()

    ids, paths = encode_choice_v01(
        tokenizer,
        "synthetic",
        question,
        max_length=1000,
    )

    assert ids == ["sign_first", "calculation_first"]

    assert len(paths) == 2

    assert all(path[-1] == 151645 for path in paths)

    assert len(tokenizer.calls) == 4

    assert tokenizer.calls[0] == "State:\nsynthetic\n"

    assert tokenizer.calls[1].startswith("Question type: choice\n")

    assert tokenizer.calls[2].startswith("Candidate:\n")

    assert tokenizer.calls[3].startswith("Candidate:\n")


def test_candidate_overlength_fails_closed():
    question = (
        build_eval_cases_v01()[0]
        ["request"]["states"][0]["questions"]["teaching_plan"]
    )

    with pytest.raises(ValueError, match="context limit"):
        encode_choice_v01(
            DummyTokenizer(),
            "synthetic",
            question,
            max_length=2,
        )


def test_scores_choose_maximum_without_model_inference():
    answer = answer_from_scores_v01(
        ["a", "b"],
        [-1.0, 2.0],
    )

    assert answer["choice"] == "b"
    assert answer["value"] == "b"
    assert answer["type"] == "choice"

    probabilities = answer["probabilities"]

    assert probabilities["b"] > probabilities["a"]

    assert math.isclose(
        math.fsum(probabilities.values()),
        1.0,
        abs_tol=1e-12,
    )


@pytest.mark.parametrize(
    "scores",
    [
        [float("nan"), 0.0],
        [float("inf"), 0.0],
        [0.0, float("-inf")],
        [0.0],
    ],
)
def test_invalid_scores_fail_closed(scores):
    with pytest.raises(ValueError):
        answer_from_scores_v01(
            ["a", "b"],
            scores,
        )


def test_dry_run_is_deterministic():
    assert build_eval_cases_v01() == build_eval_cases_v01()
