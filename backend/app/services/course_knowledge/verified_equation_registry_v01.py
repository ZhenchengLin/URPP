"""URPP 14D-4B4D2F.

Deterministic lookup for source-bound VerifiedEquationRecordV01 records.

This registry is intentionally separate from Professor generation.

It provides a fail-closed lookup boundary:

authorized Course Sources
        +
exact equation label
        +
reviewed equation registry
        ↓
zero matches -> None
one match   -> deterministic rendered equation
many matches -> reject as ambiguous

This module does NOT:
- parse student questions;
- alter Source selection;
- discover equations from PDFs;
- automatically review equations;
- modify Course Packs;
- call an LLM;
- generate Professor explanations;
- create Student State or Mastery Evidence.

A registry is a current lookup snapshot. It must not contain more than
one record for the same exact Source revision and equation label.
"""

from __future__ import annotations

import re

from dataclasses import dataclass

from pydantic import (
    Field,
    model_validator,
)

from app.services.course_knowledge.models_v01 import (
    CourseContractBaseV01,
    CourseSourceV01,
)

from app.services.course_knowledge.verified_equation_record_v01 import (
    VerifiedEquationRecordV01,
    render_verified_equation_markdown_v01,
    validate_verified_equation_binding_v01,
)


_EQUATION_LABEL = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$"
)


class VerifiedEquationRegistryV01(
    CourseContractBaseV01
):
    """One immutable snapshot of reviewed equation records.

    record_id identifies one record object.

    The binding key identifies the mathematical record that would be
    returned for one exact Source revision and equation label.

    Duplicate binding keys are rejected even when record_id or
    record_revision differs. A lookup boundary must never silently choose
    between multiple current records for the same exact equation.
    """

    records: tuple[
        VerifiedEquationRecordV01,
        ...
    ] = Field(
        min_length=1,
        max_length=512,
    )

    @model_validator(mode="after")
    def reject_duplicate_records(self):
        record_ids = [
            item.record_id
            for item in self.records
        ]

        if len(record_ids) != len(set(record_ids)):
            raise ValueError(
                "Duplicate verified equation record ID."
            )

        binding_keys = []

        for item in self.records:
            ref = item.source_ref

            binding_keys.append(
                (
                    ref.source_id,
                    ref.source_revision,
                    ref.source_locator,
                    ref.content_sha256,
                    item.equation_label,
                )
            )

        if len(binding_keys) != len(set(binding_keys)):
            raise ValueError(
                "Duplicate verified equation binding."
            )

        return self


@dataclass(
    frozen=True,
    slots=True,
)
class VerifiedEquationLookupResultV01:
    """One exact deterministic equation lookup result."""

    record: VerifiedEquationRecordV01
    source: CourseSourceV01
    rendered_markdown: str


def _revalidate_registry(
    registry: VerifiedEquationRegistryV01,
) -> VerifiedEquationRegistryV01:
    if not isinstance(
        registry,
        VerifiedEquationRegistryV01,
    ):
        raise TypeError(
            "Expected VerifiedEquationRegistryV01."
        )

    return VerifiedEquationRegistryV01.model_validate(
        registry.model_dump(mode="python")
    )


def _revalidate_sources(
    sources: tuple[
        CourseSourceV01,
        ...
    ],
) -> tuple[
    CourseSourceV01,
    ...
]:
    if (
        type(sources) is not tuple
        or not 1 <= len(sources) <= 8
    ):
        raise ValueError(
            "Equation lookup requires 1-8 Course Sources."
        )

    checked = []

    for source in sources:
        if not isinstance(
            source,
            CourseSourceV01,
        ):
            raise TypeError(
                "Equation lookup requires CourseSourceV01 records."
            )

        checked.append(
            CourseSourceV01.model_validate(
                source.model_dump(mode="python")
            )
        )

    source_ids = [
        source.source_id
        for source in checked
    ]

    if len(source_ids) != len(set(source_ids)):
        raise ValueError(
            "Equation lookup received duplicate Course Source IDs."
        )

    return tuple(checked)


def lookup_verified_equation_v01(
    *,
    registry: VerifiedEquationRegistryV01,
    sources: tuple[
        CourseSourceV01,
        ...
    ],
    equation_label: str,
) -> VerifiedEquationLookupResultV01 | None:
    """Look up one exact source-bound reviewed equation.

    sources must already be the currently authorized / selected
    CourseSourceV01 objects supplied by the application.

    The registry cannot grant access to a source that was not supplied.

    Proposed and revoked records are not eligible for deterministic
    teaching lookup.

    If more than one eligible record remains across the supplied sources,
    lookup fails closed rather than preferring source order.
    """

    checked_registry = _revalidate_registry(
        registry
    )

    checked_sources = _revalidate_sources(
        sources
    )

    if (
        type(equation_label) is not str
        or not _EQUATION_LABEL.fullmatch(
            equation_label
        )
    ):
        raise ValueError(
            "Invalid equation label."
        )

    source_by_ref = {
        (
            source.source_id,
            source.source_revision,
            source.source_locator,
            source.content_sha256,
        ): source
        for source in checked_sources
    }

    candidates = []

    for record in checked_registry.records:
        if (
            record.equation_label
            != equation_label
            or record.review_status
            != "source_checked"
        ):
            continue

        ref = record.source_ref

        key = (
            ref.source_id,
            ref.source_revision,
            ref.source_locator,
            ref.content_sha256,
        )

        source = source_by_ref.get(key)

        if source is None:
            continue

        checked_record, checked_source = (
            validate_verified_equation_binding_v01(
                record=record,
                source=source,
            )
        )

        candidates.append(
            (
                checked_record,
                checked_source,
            )
        )

    if not candidates:
        return None

    if len(candidates) != 1:
        raise ValueError(
            "Ambiguous verified equation lookup."
        )

    record, source = candidates[0]

    rendered = (
        render_verified_equation_markdown_v01(
            record=record,
            source=source,
        )
    )

    return VerifiedEquationLookupResultV01(
        record=record,
        source=source,
        rendered_markdown=rendered,
    )
