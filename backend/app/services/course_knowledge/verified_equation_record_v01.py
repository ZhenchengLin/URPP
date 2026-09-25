"""URPP 14D-4B4D2E.

Version-bound reviewed equation records and deterministic rendering.

This module is intentionally independent of Professor generation.

A VerifiedEquationRecordV01:
- binds one equation representation to one exact Course Source revision;
- stores normalized LaTeX that has been separately source-checked;
- records review provenance metadata;
- can be rendered deterministically without asking an LLM to reproduce
  the equation.

This module does NOT:
- authenticate a reviewer;
- prove that a review was performed correctly;
- modify a Course Pack;
- grant new access to a Course Source;
- create Mastery Evidence or Student State evidence;
- authorize a Professor explanation;
- automatically convert PDF extraction into verified mathematics.

"source_checked" is application-supplied review metadata, not a
cryptographic or institutional attestation.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import (
    Field,
    field_validator,
    model_validator,
)

from app.services.course_knowledge.models_v01 import (
    CourseContractBaseV01,
    CourseSourceRefV01,
    CourseSourceV01,
)


EquationReviewStatusV01 = Literal[
    "proposed",
    "source_checked",
    "revoked",
]


class VerifiedEquationRecordV01(
    CourseContractBaseV01
):
    """One reviewed mathematical representation bound to one source.

    normalized_latex stores the body of a display equation.
    Markdown or MathJax outer delimiters are deliberately excluded so
    rendering can be controlled deterministically by the application.

    reviewer_id and reviewed_at are provenance metadata. They are not
    authentication or proof of reviewer authority.
    """

    record_id: str = Field(
        min_length=1,
        max_length=128,
    )

    record_revision: str = Field(
        min_length=1,
        max_length=128,
    )

    equation_label: str = Field(
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$",
    )

    source_ref: CourseSourceRefV01

    equation_locator: str = Field(
        min_length=1,
        max_length=2048,
    )

    normalized_latex: str = Field(
        min_length=1,
        max_length=8000,
    )

    review_status: EquationReviewStatusV01

    reviewer_id: str | None = Field(
        default=None,
        max_length=128,
    )

    reviewed_at: datetime | None = None

    @field_validator(
        "record_id",
        "record_revision",
        "equation_locator",
    )
    @classmethod
    def reject_blank_identifier_fields(
        cls,
        value: str,
    ) -> str:
        if not value.strip():
            raise ValueError(
                "Equation record fields cannot be blank."
            )

        return value

    @field_validator("normalized_latex")
    @classmethod
    def validate_normalized_latex(
        cls,
        value: str,
    ) -> str:
        if not value.strip():
            raise ValueError(
                "Equation LaTeX cannot be blank."
            )

        if value != value.strip():
            raise ValueError(
                "Equation LaTeX must not contain outer whitespace."
            )

        # A single LaTeX backslash accidentally interpreted as a JSON
        # control escape can become characters such as backspace (\b),
        # form feed (\f), tab (\t), or carriage return (\r).
        #
        # Newline is intentionally permitted for readable equations.
        if any(
            (ord(character) < 32 and character != "\n")
            or ord(character) == 127
            for character in value
        ):
            raise ValueError(
                "Equation LaTeX contains a control character."
            )

        # Store only the equation body. The renderer owns display
        # delimiters so that a record cannot create nested or ambiguous
        # Markdown/MathJax blocks.
        if (
            "$$" in value
            or r"\[" in value
            or r"\]" in value
            or "```" in value
        ):
            raise ValueError(
                "Equation LaTeX must not contain outer display delimiters."
            )

        return value

    @model_validator(mode="after")
    def validate_review_provenance(self):
        reviewed = self.review_status in {
            "source_checked",
            "revoked",
        }

        if reviewed:
            if (
                self.reviewer_id is None
                or not self.reviewer_id.strip()
            ):
                raise ValueError(
                    "Reviewed equation requires reviewer metadata."
                )

            if self.reviewed_at is None:
                raise ValueError(
                    "Reviewed equation requires review time."
                )

            if (
                self.reviewed_at.tzinfo is None
                or self.reviewed_at.utcoffset() is None
            ):
                raise ValueError(
                    "Equation review time must be timezone-aware."
                )

        else:
            if (
                self.reviewer_id is not None
                or self.reviewed_at is not None
            ):
                raise ValueError(
                    "Proposed equation cannot claim completed review metadata."
                )

        return self


def _revalidate_record(
    record: VerifiedEquationRecordV01,
) -> VerifiedEquationRecordV01:
    """Revalidate even if model_copy(update=...) bypassed normal checks."""

    if not isinstance(
        record,
        VerifiedEquationRecordV01,
    ):
        raise TypeError(
            "Expected VerifiedEquationRecordV01."
        )

    return VerifiedEquationRecordV01.model_validate(
        record.model_dump(mode="python")
    )


def _revalidate_source(
    source: CourseSourceV01,
) -> CourseSourceV01:
    """Revalidate source digest and structural contract."""

    if not isinstance(
        source,
        CourseSourceV01,
    ):
        raise TypeError(
            "Expected CourseSourceV01."
        )

    return CourseSourceV01.model_validate(
        source.model_dump(mode="python")
    )


def validate_verified_equation_binding_v01(
    *,
    record: VerifiedEquationRecordV01,
    source: CourseSourceV01,
) -> tuple[
    VerifiedEquationRecordV01,
    CourseSourceV01,
]:
    """Validate one equation against one exact teachable source.

    This function does not discover a source and does not authorize a
    source merely because a record references it.

    The caller must supply the exact CourseSourceV01. This boundary
    checks that the source itself remains student-visible, locally
    teachable, approved, digest-valid, and identical to the source
    reference embedded in the reviewed equation.
    """

    checked_record = _revalidate_record(record)
    checked_source = _revalidate_source(source)

    if checked_record.review_status != "source_checked":
        raise ValueError(
            "Equation is not currently source-checked."
        )

    if checked_source.visibility != "student_visible":
        raise ValueError(
            "Equation source is not student-visible."
        )

    if (
        checked_source.use_permission
        != "approved_for_local_teaching"
    ):
        raise ValueError(
            "Equation source is not approved for local teaching."
        )

    if checked_source.review_status != "approved":
        raise ValueError(
            "Equation source is not approved."
        )

    if (
        checked_record.source_ref
        != checked_source.reference()
    ):
        raise ValueError(
            "Equation record does not match exact Course Source revision."
        )

    return checked_record, checked_source


def render_verified_equation_markdown_v01(
    *,
    record: VerifiedEquationRecordV01,
    source: CourseSourceV01,
) -> str:
    """Render an exact reviewed equation without model regeneration.

    Output is deterministic Markdown containing a MathJax display block.

    The equation body is taken byte-for-byte from normalized_latex after
    validation. No LLM, semantic rewriting, equation repair, or notation
    normalization occurs at render time.
    """

    checked_record, _ = (
        validate_verified_equation_binding_v01(
            record=record,
            source=source,
        )
    )

    return (
        f"**Equation ({checked_record.equation_label})**\n\n"
        "$$\n"
        f"{checked_record.normalized_latex}\n"
        "$$"
    )
