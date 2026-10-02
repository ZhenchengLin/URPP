from datetime import datetime, timezone

from app.services.course_knowledge.models_v01 import (
    CourseLearningObjectiveV01,
    CourseSourceRefV01,
    CourseSourceV01,
)
from app.services.course_knowledge.verified_equation_professor_route_v01 import (
    resolve_verified_equation_professor_route_v01,
)
from app.services.course_knowledge.verified_equation_record_v01 import (
    VerifiedEquationRecordV01,
)
from app.services.course_knowledge.verified_equation_registry_v01 import (
    VerifiedEquationRegistryV01,
)

def _source(
    *,
    source_id: str = "synthetic-source-7",
    revision: str = "synthetic-revision-v01",
    content: str = "Synthetic equation (7).",
    digest: str | None = None,
) -> CourseSourceV01:
    if digest is None:
        digest = __import__("hashlib").sha256(
            content.encode("utf-8")
        ).hexdigest()

    return CourseSourceV01(
        course_id="synthetic-course",
        source_id=source_id,
        source_revision=revision,
        source_locator="synthetic-page-7",
        content=content,
        content_sha256=digest,
        visibility="student_visible",
        use_permission="approved_for_local_teaching",
        review_status="approved",
    )

def _registry(
    source: CourseSourceV01,
    *,
    label: str = "7",
    latex: str = r"x = y + z",
) -> VerifiedEquationRegistryV01:
    return VerifiedEquationRegistryV01(
        records=(
            VerifiedEquationRecordV01(
                record_id=f"synthetic-equation-{label}",
                record_revision="synthetic-record-v01",
                equation_label=label,
                source_ref=source.reference(),
                equation_locator=f"synthetic-equation-{label}",
                normalized_latex=latex,
                review_status="source_checked",
                reviewer_id="synthetic-reviewer",
                reviewed_at=datetime(
                    2026, 1, 1, tzinfo=timezone.utc
                ),
            ),
        ),
    )

def _objective(
    source: CourseSourceV01,
) -> CourseLearningObjectiveV01:
    return CourseLearningObjectiveV01(
        course_id="synthetic-course",
        objective_id="synthetic-objective",
        description="Synthetic equation objective",
        review_status="approved",
        source_refs=(source.reference(),),
    )

def test_transcription_uses_exact_verified_latex():
    source = _source()
    route = resolve_verified_equation_professor_route_v01(
        registry=_registry(source),
        objective=_objective(source),
        sources=(source,),
        question="Please copy Eq. (7).",
    )

    assert route.status == "complete"
    assert r"x = y + z" in route.rendered_markdown
    assert route.source_ids == (source.source_id,)

def test_missing_registry_fails_closed():
    source = _source()
    route = resolve_verified_equation_professor_route_v01(
        registry=None,
        objective=_objective(source),
        sources=(source,),
        question="Please copy Eq. (7).",
    )
    assert route.status == "incomplete"
    assert route.rendered_markdown is None

def test_wrong_source_revision_fails_closed():
    source = _source()
    stale = _source(revision="stale-revision")
    route = resolve_verified_equation_professor_route_v01(
        registry=_registry(stale),
        objective=_objective(source),
        sources=(source,),
        question="Please copy Eq. (7).",
    )
    assert route.status == "incomplete"

def test_wrong_content_sha256_fails_closed():
    source = _source()
    changed = _source(content="Changed synthetic source content.")
    route = resolve_verified_equation_professor_route_v01(
        registry=_registry(changed),
        objective=_objective(source),
        sources=(source,),
        question="Please copy Eq. (7).",
    )
    assert route.status == "incomplete"

def test_unknown_label_fails_closed():
    source = _source()
    route = resolve_verified_equation_professor_route_v01(
        registry=_registry(source, label="10"),
        objective=_objective(source),
        sources=(source,),
        question="Please copy Eq. (7).",
    )
    assert route.status == "incomplete"

def test_source_outside_objective_scope_fails_closed():
    allowed = _source(source_id="allowed-source")
    outside = _source(source_id="outside-source")
    route = resolve_verified_equation_professor_route_v01(
        registry=_registry(outside),
        objective=_objective(allowed),
        sources=(allowed, outside),
        question="Please copy Eq. (7).",
    )
    assert route.status == "incomplete"

def test_non_transcription_request_stays_on_professor_path():
    source = _source()
    route = resolve_verified_equation_professor_route_v01(
        registry=_registry(source),
        objective=_objective(source),
        sources=(source,),
        question="Explain Eq. (7).",
    )
    assert route.status == "not_applicable"


import pytest

@pytest.mark.parametrize("label", ("7", "10", "15", "16"))
def test_required_labels_use_exact_verified_latex(label):
    source = _source(
        source_id=f"synthetic-source-{label}",
        content=f"Synthetic equation ({label}).",
    )
    latex = rf"verified_{{{label}}} = exact"
    route = resolve_verified_equation_professor_route_v01(
        registry=_registry(source, label=label, latex=latex),
        objective=_objective(source),
        sources=(source,),
        question=f"Please copy Eq. ({label}).",
    )
    assert route.status == "complete"
    assert latex in route.rendered_markdown
    assert route.source_ids == (source.source_id,)
