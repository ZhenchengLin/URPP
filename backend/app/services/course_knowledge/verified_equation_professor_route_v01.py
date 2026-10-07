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
    equation_request_requires_explanation_v01,
    extract_explicit_equation_labels_v01,
    resolve_verified_equation_request_v01,
)

# Explicit requests to display an equation, in English or Chinese.
# The Chinese alternatives are needed because the 14E cases (and the
# real learner) ask in Chinese; an English-only pattern left the
# verified path unreachable in the first 14F run.
_TRANSCRIPTION_INTENT = re.compile(
    r"(?:"
    r"\b(?:copy|transcribe|write|show|display|give|provide|state)\b|"
    r"写出|写下|抄|默写|给出|列出|展示|显示|发给|贴出"
    r")",
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
    """Resolve explicitly named equations against exact objective bindings.

    This path deliberately does not depend on the lexical course-source
    selector.  A verified record is usable only when its source binding can
    match an actual source authorized by the current learning objective.

    Statuses:

    - ``complete``: pure transcription; render verified records only.
    - ``complete_with_explanation``: the question names equations that all
      resolve, but also asks for semantic material (or is not a pure
      transcription request).  The caller shows the verified records
      verbatim and lets the Professor add a generated explanation.
    - ``incomplete``: pure transcription that cannot resolve exactly;
      the caller fails closed.
    - ``not_applicable``: no registry configured, no explicit equation
      label, or a semantic question whose equations do not resolve;
      ordinary Professor path.
    """

    del history

    labels = extract_explicit_equation_labels_v01(question)

    if not labels:
        return VerifiedEquationProfessorRouteV01(
            status="not_applicable",
            rendered_markdown=None,
            source_ids=(),
            requested_labels=labels,
        )

    pure_transcription = bool(
        _TRANSCRIPTION_INTENT.search(question)
    ) and not equation_request_requires_explanation_v01(question)

    # A semantic question that cannot be grounded in verified records
    # keeps the pre-14F behavior instead of being refused.
    unresolved_status = (
        "incomplete" if pure_transcription else "not_applicable"
    )

    # No registry configured means the 14F route is switched off for
    # this pack: keep the pre-14F Professor behavior.  Fail-closed
    # refusal applies only when a registry exists but cannot resolve.
    if registry is None:
        return VerifiedEquationProfessorRouteV01(
            status="not_applicable",
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
            status=unresolved_status,
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
            status=unresolved_status,
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
        status=(
            "complete"
            if pure_transcription
            else "complete_with_explanation"
        ),
        rendered_markdown=resolution.rendered_markdown,
        source_ids=resolution.source_ids,
        requested_labels=resolution.requested_labels,
        record_provenance=record_provenance,
    )
