"""Pack-generic deterministic routing for explicit verified equations."""

from __future__ import annotations

from dataclasses import dataclass
import re

from app.services.course_knowledge.models_v01 import (
    CourseLearningObjectiveV01,
    CourseSourceV01,
)
from app.services.course_knowledge.verified_equation_registry_v01 import (
    VerifiedEquationRegistryV01,
)
from app.services.course_knowledge.verified_equation_request_v01 import (
    extract_explicit_equation_labels_v01,
    resolve_verified_equation_request_v01,
)

_TRANSCRIPTION_INTENT = re.compile(
    r"\b(copy|transcribe|write|show|display|give|provide|state)\b",
    re.I,
)
_EXPLANATION_OR_COMPARE_INTENT = re.compile(
    r"\b(explain|compare)\b",
    re.I,
)

@dataclass(frozen=True, slots=True)
class VerifiedEquationProfessorRouteV01:
    status: str
    rendered_markdown: str | None
    source_ids: tuple[str, ...]
    requested_labels: tuple[str, ...]
    record_provenance: tuple[tuple[str, str], ...] = ()

def resolve_verified_equation_professor_route_v01(
    *,
    registry: VerifiedEquationRegistryV01 | None,
    objective: CourseLearningObjectiveV01,
    sources: tuple[CourseSourceV01, ...],
    question: str,
    history: tuple[object, ...] = (),
) -> VerifiedEquationProfessorRouteV01:
    """Resolve pure equation transcription against exact objective bindings.

    This path deliberately does not depend on the lexical course-source
    selector.  A verified record is usable only when its source binding can
    match an actual source authorized by the current learning objective.
    Pure transcription therefore either resolves exactly or fails closed.
    Explanation and comparison requests remain on the ordinary Professor
    path.
    """

    del history

    labels = extract_explicit_equation_labels_v01(question)

    if (
        not labels
        or not _TRANSCRIPTION_INTENT.search(question)
        or _EXPLANATION_OR_COMPARE_INTENT.search(question)
    ):
        return VerifiedEquationProfessorRouteV01(
            status="not_applicable",
            rendered_markdown=None,
            source_ids=(),
            requested_labels=labels,
        )

    if registry is None:
        return VerifiedEquationProfessorRouteV01(
            status="incomplete",
            rendered_markdown=None,
            source_ids=(),
            requested_labels=labels,
        )

    authorized_bindings = {
        (
            ref.source_id,
            ref.source_revision,
            ref.content_sha256,
        )
        for ref in objective.source_refs
    }

    scoped_sources = tuple(
        source
        for source in sources
        if (
            source.source_id,
            source.source_revision,
            source.content_sha256,
        )
        in authorized_bindings
    )

    if not scoped_sources:
        return VerifiedEquationProfessorRouteV01(
            status="incomplete",
            rendered_markdown=None,
            source_ids=(),
            requested_labels=labels,
        )

    resolution = resolve_verified_equation_request_v01(
        registry=registry,
        sources=scoped_sources,
        question=question,
    )

    if resolution.status != "verified":
        return VerifiedEquationProfessorRouteV01(
            status="incomplete",
            rendered_markdown=None,
            source_ids=(),
            requested_labels=labels,
        )

    records_by_id = {
        record.record_id: record
        for record in registry.records
    }
    record_provenance = tuple(
        (
            record_id,
            records_by_id[record_id].record_revision,
        )
        for record_id in resolution.record_ids
    )

    return VerifiedEquationProfessorRouteV01(
        status="complete",
        rendered_markdown=resolution.rendered_markdown,
        source_ids=resolution.source_ids,
        requested_labels=resolution.requested_labels,
        record_provenance=record_provenance,
    )
