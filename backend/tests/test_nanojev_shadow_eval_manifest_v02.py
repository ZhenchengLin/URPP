"""
Offline validation for NanoJev Shadow Evaluation Manifest v0.2.

These tests do not load NanoJev, use MPS, access students,
or establish pedagogical effectiveness.
"""

import json

from collections import Counter
from pathlib import Path

import pytest

from app.services.course_knowledge.nanojev_shadow_adapter_v01 import (
    build_nanojev_lu_request_v01,
)

from app.services.course_knowledge.controlled_lu_teaching_v01 import (
    select_pilot_plan_v01,
)


MANIFEST_PATH = (
    Path(__file__).resolve().parents[1]
    / "evaluations"
    / "nanojev_shadow_eval_v02_manifest.json"
)


@pytest.fixture(scope="module")
def manifest():
    return json.loads(
        MANIFEST_PATH.read_text(encoding="utf-8")
    )


def cases_by_id(manifest):
    return {
        case["case_id"]: case
        for case in manifest["cases"]
    }


def test_manifest_scope_and_identity(manifest):
    assert manifest["schema_version"] == (
        "urpp-nanojev-shadow-manifest-v02"
    )

    assert manifest["status"] == "developer_audit_only"

    assert manifest["starting_commit"] == "7262d37"

    assert manifest["distinct_case_count"] == 10

    assert len(manifest["cases"]) == 10

    assert manifest["student_delivery_authorized"] is False

    assert manifest["experiment_controls"] == {
        "candidate_orders": [
            "original",
            "reversed",
        ],
        "repeats_per_configuration": 2,
        "candidate_count_per_question": 2,
        "questions_per_case": 2,
    }


def test_case_ids_unique_and_stable(manifest):
    ids = [
        case["case_id"]
        for case in manifest["cases"]
    ]

    assert len(ids) == len(set(ids))

    assert ids == [
        "baseline_sign_relation_01",
        "baseline_calculation_01",
        "paraphrase_sign_relation_01",
        "paraphrase_sign_relation_02",
        "paraphrase_calculation_01",
        "paraphrase_calculation_02",
        "candidate_description_sign_relation_01",
        "candidate_description_calculation_01",
        "ambiguous_missing_focus_01",
        "ambiguous_conflicting_focus_01",
    ]


def test_group_counts(manifest):
    counts = Counter(
        case["group"]
        for case in manifest["cases"]
    )

    assert counts == {
        "baseline": 2,
        "paraphrase": 4,
        "candidate_description": 2,
        "ambiguous": 2,
    }


@pytest.mark.parametrize(
    "focus_id",
    [
        "sign_relation",
        "calculation",
    ],
)
def test_baseline_inputs_are_exact_v01_requests(
    manifest,
    focus_id,
):
    case = cases_by_id(manifest)[
        f"baseline_{focus_id}_01"
    ]

    assert case["request"] == (
        build_nanojev_lu_request_v01(focus_id)
    )

    assert case["baseline_focus_id"] == focus_id

    expected = select_pilot_plan_v01(focus_id)

    assert case["reference_policy"] == {
        "plan_id": expected.plan_id,
        "check_id": expected.check_id,
    }


def test_all_cases_have_fixed_choice_contract(manifest):
    expected_ids = {
        "teaching_plan": {
            "sign_first",
            "calculation_first",
        },
        "follow_up_check": {
            "ask_sign_relation",
            "ask_row_operation",
        },
    }

    for case in manifest["cases"]:
        request = case["request"]

        assert set(request) == {"states"}
        assert len(request["states"]) == 1

        state = request["states"][0]

        assert state["id"] == "urpp_lu_pilot_01"
        assert isinstance(state["state"], str)
        assert state["state"].strip()

        assert set(state["questions"]) == set(expected_ids)

        for question_id, candidate_ids in expected_ids.items():
            question = state["questions"][question_id]

            assert question["type"] == "choice"
            assert isinstance(question["instructions"], str)
            assert question["instructions"].strip()

            assert set(question["criteria"]) == candidate_ids

            assert all(
                isinstance(text, str) and text.strip()
                for text in question["criteria"].values()
            )


def test_paraphrases_change_state_text_only(manifest):
    indexed = cases_by_id(manifest)

    for case in manifest["cases"]:
        if case["group"] != "paraphrase":
            continue

        baseline = indexed[
            f"baseline_{case['baseline_focus_id']}_01"
        ]

        baseline_state = baseline["request"]["states"][0]
        variant_state = case["request"]["states"][0]

        assert (
            variant_state["state"]
            != baseline_state["state"]
        )

        assert (
            variant_state["questions"]
            == baseline_state["questions"]
        )


def test_candidate_variants_change_descriptions_only(manifest):
    indexed = cases_by_id(manifest)

    for case in manifest["cases"]:
        if case["group"] != "candidate_description":
            continue

        baseline = indexed[
            f"baseline_{case['baseline_focus_id']}_01"
        ]

        baseline_state = baseline["request"]["states"][0]
        variant_state = case["request"]["states"][0]

        assert variant_state["state"] == baseline_state["state"]

        for question_id in (
            "teaching_plan",
            "follow_up_check",
        ):
            original = baseline_state["questions"][question_id]
            variant = variant_state["questions"][question_id]

            assert variant["type"] == original["type"]

            assert (
                variant["instructions"]
                == original["instructions"]
            )

            assert (
                list(variant["criteria"])
                == list(original["criteria"])
            )

            for candidate_id, text in variant["criteria"].items():
                assert text != original["criteria"][candidate_id]


def test_ambiguous_cases_have_no_forced_reference(manifest):
    for case in manifest["cases"]:
        if case["group"] == "ambiguous":
            assert case["baseline_focus_id"] is None
            assert case["reference_policy"] is None
        else:
            assert case["baseline_focus_id"] in {
                "sign_relation",
                "calculation",
            }

            assert case["reference_policy"] is not None


def test_clear_case_reference_uses_registered_policy(manifest):
    for case in manifest["cases"]:
        focus_id = case["baseline_focus_id"]

        if focus_id is None:
            continue

        registered = select_pilot_plan_v01(focus_id)

        assert case["reference_policy"] == {
            "plan_id": registered.plan_id,
            "check_id": registered.check_id,
        }


def test_ambiguous_cases_do_not_mutate_baseline(manifest):
    indexed = cases_by_id(manifest)

    original = indexed[
        "baseline_sign_relation_01"
    ]["request"]

    assert original == build_nanojev_lu_request_v01(
        "sign_relation"
    )

    for case_id in (
        "ambiguous_missing_focus_01",
        "ambiguous_conflicting_focus_01",
    ):
        ambiguous = indexed[case_id]["request"]

        assert (
            ambiguous["states"][0]["questions"]
            == original["states"][0]["questions"]
        )

        assert (
            ambiguous["states"][0]["state"]
            != original["states"][0]["state"]
        )


def test_manifest_is_valid_json_with_no_nan(manifest):
    encoded = json.dumps(
        manifest,
        allow_nan=False,
    )

    assert encoded

    assert json.loads(encoded) == manifest
