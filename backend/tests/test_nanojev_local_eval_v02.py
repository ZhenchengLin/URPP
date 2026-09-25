"""Offline tests for the frozen NanoJev v0.2 evaluation runner."""

import copy
import json

from pathlib import Path

import pytest

from app.services.course_knowledge.nanojev_local_eval_v02 import (
    MANIFEST_SHA256,
    build_configurations_v02,
    load_manifest_v02,
    manifest_path_v02,
    record_response_v02,
    summarize_records_v02,
)


@pytest.fixture(scope="module")
def manifest():
    return load_manifest_v02(
        manifest_path_v02()
    )


def test_manifest_identity_and_controls(manifest):
    assert len(MANIFEST_SHA256) == 64
    assert manifest["distinct_case_count"] == 10
    assert len(manifest["cases"]) == 10
    assert manifest["student_delivery_authorized"] is False


def test_exactly_forty_unique_configurations(manifest):
    configurations = build_configurations_v02(
        manifest
    )

    assert len(configurations) == 40

    keys = {
        (
            config["case_id"],
            config["candidate_order"],
            config["repeat"],
        )
        for config in configurations
    }

    assert len(keys) == 40


def test_configurations_do_not_mutate_manifest(manifest):
    original = copy.deepcopy(manifest)

    configurations = build_configurations_v02(
        manifest
    )

    configurations[0]["request"]["states"][0]["state"] = (
        "MUTATED"
    )

    assert manifest == original


def test_candidate_order_reverses_ids_not_meanings(manifest):
    configurations = build_configurations_v02(
        manifest
    )

    original = configurations[0]["request"]["states"][0]
    reversed_state = configurations[2]["request"]["states"][0]

    assert original["state"] == reversed_state["state"]

    for question_id in (
        "teaching_plan",
        "follow_up_check",
    ):
        original_criteria = original[
            "questions"
        ][question_id]["criteria"]

        reversed_criteria = reversed_state[
            "questions"
        ][question_id]["criteria"]

        assert list(reversed_criteria) == list(
            reversed(list(original_criteria))
        )

        assert original_criteria == reversed_criteria


def test_ambiguous_cases_never_receive_forced_reference(manifest):
    configurations = build_configurations_v02(
        manifest
    )

    ambiguous = [
        config
        for config in configurations
        if config["group"] == "ambiguous"
    ]

    assert len(ambiguous) == 8

    assert all(
        config["reference_policy"] is None
        for config in ambiguous
    )


def test_ambiguous_response_has_null_agreement(manifest):
    configuration = next(
        config
        for config in build_configurations_v02(manifest)
        if config["group"] == "ambiguous"
    )

    answers = {
        "teaching_plan": {
            "type": "choice",
            "probabilities": {
                "sign_first": 0.6,
                "calculation_first": 0.4,
            },
            "choice": "sign_first",
            "value": "sign_first",
        },
        "follow_up_check": {
            "type": "choice",
            "probabilities": {
                "ask_sign_relation": 0.7,
                "ask_row_operation": 0.3,
            },
            "choice": "ask_sign_relation",
            "value": "ask_sign_relation",
        },
    }

    record = record_response_v02(
        configuration,
        answers,
        {
            "teaching_plan": 0.0,
            "follow_up_check": 0.0,
        },
    )

    assert record["reference_policy"] is None
    assert record["plan_matches_pilot"] is None
    assert record["check_matches_pilot"] is None
    assert record["student_delivery_authorized"] is False


def test_manifest_modified_copy_fails_identity_check(
    manifest,
    tmp_path,
):
    modified = copy.deepcopy(manifest)

    modified["cases"][0]["description"] = "CHANGED"

    path = tmp_path / "modified_manifest.json"

    path.write_text(
        json.dumps(modified),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="SHA-256"):
        load_manifest_v02(path)


def test_summary_rejects_incomplete_configuration_set(manifest):
    with pytest.raises(ValueError, match="Incomplete configurations"):
        summarize_records_v02(
            [],
            manifest,
        )
