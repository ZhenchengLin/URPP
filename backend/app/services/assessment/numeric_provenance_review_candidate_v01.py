"""
URPP Implementation 13E-4B.

Create a source-bound Numeric Provenance Review Candidate
from a persisted Attempt Provenance Snapshot.

A candidate is not an approval.

The source fingerprint detects ordinary record changes.
It does not authenticate a reviewer, establish provenance
truth, or prevent an authorized database writer from
replacing both records and fingerprints.
"""

from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Literal

from app.services.assessment.numeric_attempt_provenance_snapshot_v01 import (
    NumericAttemptProvenanceSnapshotServiceV01,
    NumericAttemptProvenanceSnapshotV01,
)


CANDIDATE_POLICY_VERSION = (
    "numeric-provenance-candidate-v0.1"
)


@dataclass(frozen=True)
class NumericProvenanceReviewCandidateV01:
    """
    Immutable review input tied to a particular snapshot.

    The candidate deliberately contains no raw response
    text and cannot grant independent-performance status.
    """

    assignment_id: str
    attempt_id: str

    student_id: str
    session_id: str

    source_fingerprint_sha256: str

    reported_hint_count: int
    reported_solution_count: int

    external_assistance_status: Literal[
        "unknown",
    ] = "unknown"

    review_status: Literal[
        "pending_authorized_review",
    ] = "pending_authorized_review"

    verified_independence: bool = False

    accepted_as_mastery_evidence: bool = False

    policy_version: str = CANDIDATE_POLICY_VERSION


class ProvenanceSourceChangedV01(ValueError):
    """
    A candidate no longer matches the current stored
    Assignment, Attempt, and Assistance Event records.
    """


def source_fingerprint_v01(
    snapshot: NumericAttemptProvenanceSnapshotV01,
) -> str:
    """
    Deterministically fingerprint the complete V0.1
    review-input record, including the reported help.

    This is not a signature or proof of student authorship.

    A SHA-256 digest of a short answer is not anonymity
    or a privacy protection against guessing its value.
    """

    events = [
        {
            "event_id": event.event_id,
            "assignment_id": event.assignment_id,
            "student_id": event.student_id,
            "session_id": event.session_id,
            "kind": event.kind.value,
            "content_sha256": event.content_sha256,
            "occurred_at": event.occurred_at.isoformat(),
            "source": event.source,
        }
        for event in snapshot.assistance_events
    ]

    events.sort(
        key=lambda event: event["event_id"]
    )

    source = {
        "policy_version": CANDIDATE_POLICY_VERSION,
        "assignment_id": snapshot.assignment_id,
        "attempt_id": snapshot.attempt_id,
        "student_id": snapshot.student_id,
        "course_id": snapshot.course_id,
        "objective_id": snapshot.objective_id,
        "session_id": snapshot.session_id,
        "assessment_item_id": snapshot.assessment_item_id,
        "item_revision": snapshot.item_revision,
        "response_text": snapshot.response_text,
        "stored_assistance_level": (
            snapshot.stored_assistance_level
        ),
        "stored_prior_solution_exposure": (
            snapshot.stored_prior_solution_exposure
        ),
        "assistance_report_status": (
            snapshot.assistance_report_status
        ),
        "external_assistance_status": (
            snapshot.external_assistance_status
        ),
        "review_status": snapshot.review_status,
        "verified_independence": (
            snapshot.verified_independence
        ),
        "assistance_events": events,
    }

    serialized = json.dumps(
        source,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")

    return sha256(serialized).hexdigest()


def create_review_candidate_v01(
    snapshot: NumericAttemptProvenanceSnapshotV01,
) -> NumericProvenanceReviewCandidateV01:
    """
    Describe persisted provenance for later review.

    Recorded application assistance is counted, but
    never treated as proof that the student read it.

    No recorded assistance is also not evidence that
    the student worked independently.
    """

    kinds = [
        event.kind.value
        for event in snapshot.assistance_events
    ]

    return NumericProvenanceReviewCandidateV01(
        assignment_id=snapshot.assignment_id,
        attempt_id=snapshot.attempt_id,
        student_id=snapshot.student_id,
        session_id=snapshot.session_id,
        source_fingerprint_sha256=(
            source_fingerprint_v01(snapshot)
        ),
        reported_hint_count=kinds.count("hint"),
        reported_solution_count=kinds.count("solution"),
    )


class NumericProvenanceReviewCandidateServiceV01:
    """
    Assemble and recheck a candidate against the actual
    persisted records.

    This service is internal and unauthenticated.

    Rechecking is not a transactional lock and does not
    authorize a subsequent approval.
    """

    def __init__(
        self,
        *,
        snapshot_service: (
            NumericAttemptProvenanceSnapshotServiceV01
        ),
    ) -> None:
        self._snapshot_service = snapshot_service

    def create_candidate(
        self,
        *,
        assignment_id: str,
        student_id: str,
        session_id: str,
    ) -> NumericProvenanceReviewCandidateV01:
        snapshot = self._snapshot_service.build_snapshot(
            assignment_id=assignment_id,
            student_id=student_id,
            session_id=session_id,
        )

        return create_review_candidate_v01(snapshot)

    def require_current_candidate(
        self,
        candidate: NumericProvenanceReviewCandidateV01,
    ) -> NumericAttemptProvenanceSnapshotV01:
        """
        Rebuild from storage and reject mismatched candidates.

        A caller must not use this check as proof of reviewer
        authorization or as an approval of student independence.
        """

        if not isinstance(
            candidate,
            NumericProvenanceReviewCandidateV01,
        ):
            raise TypeError(
                "A NumericProvenanceReviewCandidateV01 "
                "is required."
            )

        snapshot = self._snapshot_service.build_snapshot(
            assignment_id=candidate.assignment_id,
            student_id=candidate.student_id,
            session_id=candidate.session_id,
        )

        expected = create_review_candidate_v01(
            snapshot
        )

        if candidate != expected:
            raise ProvenanceSourceChangedV01(
                "Review Candidate does not match the "
                "current persisted provenance records."
            )

        return snapshot
