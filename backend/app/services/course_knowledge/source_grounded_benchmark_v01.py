"""URPP 14D-4B4D3 — Source-Grounded Benchmark Contract v0.1.

Contracts for independently frozen source-grounded evaluation cases
and candidate-system execution traces.

The central separation is:

    Benchmark Case
        = what SHOULD happen.

    Execution Trace
        = what ACTUALLY happened.

The gold benchmark artifact must remain outside the normal Professor
input unless an experiment explicitly defines an intervention.

This module does NOT:
- call an LLM;
- retrieve Course Sources;
- run the Professor;
- score L0/L1/L2/L3 automatically;
- modify Course Packs or Chat Sessions;
- create Student State or Mastery Evidence;
- prove that benchmark gold was reviewed correctly;
- make a private/licensed source suitable for public redistribution.

A future open benchmark may use these same contracts with openly
redistributable source material.
"""

from __future__ import annotations

from datetime import datetime
from hashlib import sha256
import json
from typing import Literal

from pydantic import (
    Field,
    field_validator,
    model_validator,
)

from app.services.course_knowledge.models_v01 import (
    CourseContractBaseV01,
    CourseSourceRefV01,
)


BenchmarkSplitV01 = Literal[
    "development",
    "holdout",
]

BenchmarkLanguageV01 = Literal[
    "en",
    "zh",
    "mixed",
    "other",
]

BenchmarkQuestionTypeV01 = Literal[
    "direct_fact",
    "equation_transcription",
    "variable_definition",
    "relationship",
    "method_attribution",
    "conceptual_explanation",
    "comparison",
    "multi_step",
    "instruction_following",
    "paraphrase",
    "follow_up",
    "unsupported",
]

BenchmarkEvidenceKindV01 = Literal[
    "fact",
    "equation",
    "definition",
    "method",
    "condition",
    "relationship",
    "context",
]

BenchmarkEvaluationCategoryV01 = Literal[
    "source_selection",
    "insufficient_evidence_handling",
    "formula_structure",
    "formula_transcription",
    "math_rendering",
    "source_extraction_artifact",
    "variable_definition",
    "method_attribution",
    "applicability_condition",
    "answer_omission",
    "unsupported_claim",
    "citation_attribution",
    "conversation_context",
    "instruction_following",
    "language_or_paraphrase_routing",
    "output_contract",
]

BenchmarkConversationRoleV01 = Literal[
    "student",
    "professor",
]

BenchmarkTraceFinalStatusV01 = Literal[
    "answered",
    "abstained",
    "error",
]

BenchmarkExpectedOutcomeV01 = Literal[
    "answer",
    "abstain",
]


_IDENTIFIER_PATTERN = (
    r"^[A-Za-z0-9]"
    r"[A-Za-z0-9._:-]{0,127}$"
)

_EQUATION_LABEL_PATTERN = (
    r"^[A-Za-z0-9]"
    r"[A-Za-z0-9._-]{0,63}$"
)


def _reject_blank(
    value: str,
    *,
    name: str,
) -> str:
    if not value.strip():
        raise ValueError(
            f"{name} cannot be blank."
        )

    return value


def _reject_duplicate_strings(
    values: tuple[str, ...],
    *,
    name: str,
) -> tuple[str, ...]:
    if len(values) != len(set(values)):
        raise ValueError(
            f"{name} contains duplicates."
        )

    return values


class BenchmarkConversationTurnV01(
    CourseContractBaseV01
):
    """One prior conversation turn supplied to a follow-up case."""

    role: BenchmarkConversationRoleV01

    text: str = Field(
        min_length=1,
        max_length=4000,
    )

    @field_validator("text")
    @classmethod
    def reject_blank_text(
        cls,
        value: str,
    ) -> str:
        return _reject_blank(
            value,
            name="Conversation text",
        )


class BenchmarkEvidenceExpectationV01(
    CourseContractBaseV01
):
    """One independently identified piece of required source evidence.

    source_ref binds the expectation to one exact source revision.
    evidence_locator narrows the supporting region inside that source,
    such as "PDF page 6, Equation (15)" or a section heading.

    rationale is benchmark-author metadata and must never be inserted
    into a normal Professor request during evaluation.
    """

    source_ref: CourseSourceRefV01

    evidence_locator: str = Field(
        min_length=1,
        max_length=2048,
    )

    evidence_kind: BenchmarkEvidenceKindV01

    rationale: str = Field(
        min_length=1,
        max_length=2000,
    )

    @field_validator(
        "evidence_locator",
        "rationale",
    )
    @classmethod
    def reject_blank_fields(
        cls,
        value: str,
    ) -> str:
        return _reject_blank(
            value,
            name="Evidence expectation field",
        )


class BenchmarkEquationGoldV01(
    CourseContractBaseV01
):
    """One independently frozen equation representation.

    normalized_latex stores only the equation body.
    It is benchmark gold, not generated Professor output.

    This gold record describes mathematical content only.
    It does not require a candidate system to use any particular
    internal record, registry, renderer, model, or tool.
    """

    equation_label: str = Field(
        pattern=_EQUATION_LABEL_PATTERN,
    )

    normalized_latex: str = Field(
        min_length=1,
        max_length=8000,
    )

    @field_validator("normalized_latex")
    @classmethod
    def validate_normalized_latex(
        cls,
        value: str,
    ) -> str:
        if not value.strip():
            raise ValueError(
                "Benchmark equation LaTeX cannot be blank."
            )

        if value != value.strip():
            raise ValueError(
                "Benchmark equation LaTeX cannot have outer whitespace."
            )

        if any(
            (
                ord(character) < 32
                and character != "\n"
            )
            or ord(character) == 127
            for character in value
        ):
            raise ValueError(
                "Benchmark equation LaTeX contains a control character."
            )

        if (
            "$$" in value
            or r"\[" in value
            or r"\]" in value
            or "```" in value
        ):
            raise ValueError(
                "Benchmark equation LaTeX must not contain display delimiters."
            )

        return value


class BenchmarkGoldV01(
    CourseContractBaseV01
):
    """Source-grounded expected content for one benchmark case.

    A case need not have a single prose reference answer. Structured
    required facts and equation representations are preferred when they
    allow more precise failure classification.
    """

    required_facts: tuple[
        str,
        ...,
    ] = Field(
        default=(),
        max_length=64,
    )

    equations: tuple[
        BenchmarkEquationGoldV01,
        ...,
    ] = Field(
        default=(),
        max_length=32,
    )

    prohibited_errors: tuple[
        str,
        ...,
    ] = Field(
        default=(),
        max_length=64,
    )

    acceptable_variants: tuple[
        str,
        ...,
    ] = Field(
        default=(),
        max_length=64,
    )

    reference_answer: str | None = Field(
        default=None,
        max_length=12000,
    )

    @field_validator(
        "required_facts",
        "prohibited_errors",
        "acceptable_variants",
    )
    @classmethod
    def validate_text_tuples(
        cls,
        values: tuple[str, ...],
    ) -> tuple[str, ...]:
        for value in values:
            if not value.strip():
                raise ValueError(
                    "Benchmark gold text items cannot be blank."
                )

        return _reject_duplicate_strings(
            values,
            name="Benchmark gold tuple",
        )

    @field_validator("reference_answer")
    @classmethod
    def validate_reference_answer(
        cls,
        value: str | None,
    ) -> str | None:
        if value is not None:
            _reject_blank(
                value,
                name="Reference answer",
            )

        return value

    @model_validator(mode="after")
    def reject_duplicate_equations(self):
        labels = tuple(
            item.equation_label
            for item in self.equations
        )

        _reject_duplicate_strings(
            labels,
            name="Benchmark equation labels",
        )

        return self

    def contains_positive_gold(self) -> bool:
        return bool(
            self.required_facts
            or self.equations
            or self.reference_answer
        )



class SourceGroundedBenchmarkCaseV01(
    CourseContractBaseV01
):
    """One immutable source-grounded benchmark case.

    source_scope_refs defines exact source revisions available to the
    benchmark case.

    required_evidence identifies which source regions independently
    support the expected answer.

    gold and expected_outcome are evaluation-only data and MUST NOT
    be leaked into the normal candidate Professor request.

    The case deliberately does not require a particular candidate
    architecture such as VerifiedEquationRecord, deterministic
    rendering, an LLM call, or a Professor implementation.
    """

    case_id: str = Field(
        pattern=_IDENTIFIER_PATTERN,
    )

    benchmark_version: str = Field(
        pattern=_IDENTIFIER_PATTERN,
    )

    split: BenchmarkSplitV01

    language: BenchmarkLanguageV01

    question_type: BenchmarkQuestionTypeV01

    question: str = Field(
        min_length=1,
        max_length=4000,
    )

    prior_turns: tuple[
        BenchmarkConversationTurnV01,
        ...,
    ] = Field(
        default=(),
        max_length=32,
    )

    source_scope_refs: tuple[
        CourseSourceRefV01,
        ...,
    ] = Field(
        min_length=1,
        max_length=32,
    )

    required_evidence: tuple[
        BenchmarkEvidenceExpectationV01,
        ...,
    ] = Field(
        default=(),
        max_length=32,
    )

    gold: BenchmarkGoldV01

    expected_outcome: BenchmarkExpectedOutcomeV01

    evaluation_categories: tuple[
        BenchmarkEvaluationCategoryV01,
        ...,
    ] = Field(
        min_length=1,
        max_length=16,
    )

    notes: str | None = Field(
        default=None,
        max_length=4000,
    )

    @field_validator(
        "question",
    )
    @classmethod
    def reject_blank_question(
        cls,
        value: str,
    ) -> str:
        return _reject_blank(
            value,
            name="Benchmark question",
        )

    @field_validator(
        "evaluation_categories",
    )
    @classmethod
    def reject_duplicate_categories(
        cls,
        values: tuple[
            BenchmarkEvaluationCategoryV01,
            ...,
        ],
    ):
        return _reject_duplicate_strings(
            values,
            name="Evaluation categories",
        )

    @field_validator("notes")
    @classmethod
    def reject_blank_notes(
        cls,
        value: str | None,
    ) -> str | None:
        if value is not None:
            _reject_blank(
                value,
                name="Benchmark notes",
            )

        return value

    @model_validator(mode="after")
    def validate_benchmark_relationships(self):
        source_ids = tuple(
            ref.source_id
            for ref in self.source_scope_refs
        )

        _reject_duplicate_strings(
            source_ids,
            name="Source scope IDs",
        )

        source_by_id = {
            ref.source_id: ref
            for ref in self.source_scope_refs
        }

        evidence_keys = []

        for expectation in self.required_evidence:
            source_id = (
                expectation.source_ref.source_id
            )

            scoped_ref = source_by_id.get(
                source_id
            )

            if scoped_ref is None:
                raise ValueError(
                    "Required evidence references a source outside case scope."
                )

            if scoped_ref != expectation.source_ref:
                raise ValueError(
                    "Required evidence source revision does not match case scope."
                )

            evidence_keys.append(
                (
                    expectation.source_ref,
                    expectation.evidence_locator,
                    expectation.evidence_kind,
                )
            )

        if len(evidence_keys) != len(
            set(evidence_keys)
        ):
            raise ValueError(
                "Benchmark contains duplicate evidence expectations."
            )

        # The most specific semantic invariant comes first:
        # an unsupported benchmark case must evaluate abstention,
        # regardless of what other fields happen to contain.
        #
        # This ordering makes validation errors describe the real
        # contract violation instead of a downstream consequence
        # such as missing positive evidence.
        if (
            self.question_type == "unsupported"
            and self.expected_outcome != "abstain"
        ):
            raise ValueError(
                "Unsupported benchmark case must expect abstention."
            )

        if self.expected_outcome == "abstain":
            if (
                self.gold.required_facts
                or self.gold.equations
            ):
                raise ValueError(
                    "Abstention case cannot require positive facts or equations."
                )

        else:
            if not self.required_evidence:
                raise ValueError(
                    "Answered source-grounded case requires required evidence."
                )

            if not self.gold.contains_positive_gold():
                raise ValueError(
                    "Answered case requires independently frozen gold."
                )

        return self


class BenchmarkExecutionTraceV01(
    CourseContractBaseV01
):
    """What one candidate system actually did for one benchmark case.

    This record intentionally stores provenance and observable behavior,
    not a PASS/FAIL judgment. L0/L1/L2/L3 evaluation belongs to a later
    evaluator boundary.

    Candidate-specific observations such as verified_record_ids may be
    empty for systems that do not implement those mechanisms. They are
    observations, never benchmark requirements.

    case_sha256 binds this run to the exact frozen benchmark artifact,
    not merely to a reusable case_id.

    raw_model_output may contain private material or generated content
    and therefore belongs in an appropriately protected evaluation store.
    """

    trace_version: str = Field(
        pattern=_IDENTIFIER_PATTERN,
    )

    run_id: str = Field(
        pattern=_IDENTIFIER_PATTERN,
    )

    case_id: str = Field(
        pattern=_IDENTIFIER_PATTERN,
    )

    case_sha256: str = Field(
        pattern=r"^[0-9a-f]{64}$",
    )

    candidate_system: str = Field(
        min_length=1,
        max_length=128,
    )

    candidate_version: str = Field(
        min_length=1,
        max_length=256,
    )

    run_started_at: datetime

    selected_source_refs: tuple[
        CourseSourceRefV01,
        ...,
    ] = Field(
        default=(),
        max_length=32,
    )

    extracted_equation_labels: tuple[
        str,
        ...,
    ] = Field(
        default=(),
        max_length=32,
    )

    verified_record_ids: tuple[
        str,
        ...,
    ] = Field(
        default=(),
        max_length=32,
    )

    model_called: bool

    model_id: str | None = Field(
        default=None,
        max_length=256,
    )

    contract_valid: bool | None = None

    session_write_performed: bool | None = None

    system_answer_status: str | None = Field(
        default=None,
        max_length=128,
    )

    final_status: BenchmarkTraceFinalStatusV01

    raw_model_output: str | None = Field(
        default=None,
        max_length=30000,
    )

    final_answer: str | None = Field(
        default=None,
        max_length=20000,
    )

    error_code: str | None = Field(
        default=None,
        max_length=256,
    )

    @field_validator(
        "candidate_system",
        "candidate_version",
    )
    @classmethod
    def reject_blank_candidate_fields(
        cls,
        value: str,
    ) -> str:
        return _reject_blank(
            value,
            name="Candidate field",
        )

    @field_validator(
        "extracted_equation_labels",
        "verified_record_ids",
    )
    @classmethod
    def reject_duplicate_trace_strings(
        cls,
        values: tuple[str, ...],
    ) -> tuple[str, ...]:
        for value in values:
            if not value.strip():
                raise ValueError(
                    "Execution trace identifiers cannot be blank."
                )

        return _reject_duplicate_strings(
            values,
            name="Execution trace tuple",
        )

    @field_validator(
        "model_id",
        "system_answer_status",
        "raw_model_output",
        "final_answer",
        "error_code",
    )
    @classmethod
    def reject_blank_optional_strings(
        cls,
        value: str | None,
    ) -> str | None:
        if value is not None:
            _reject_blank(
                value,
                name="Execution trace optional field",
            )

        return value

    @model_validator(mode="after")
    def validate_execution_trace(self):
        if (
            self.run_started_at.tzinfo is None
            or self.run_started_at.utcoffset()
            is None
        ):
            raise ValueError(
                "Execution trace time must be timezone-aware."
            )

        source_ids = tuple(
            ref.source_id
            for ref in self.selected_source_refs
        )

        _reject_duplicate_strings(
            source_ids,
            name="Selected source IDs",
        )

        if self.model_called:
            if self.model_id is None:
                raise ValueError(
                    "Model call requires model_id."
                )

        else:
            if self.model_id is not None:
                raise ValueError(
                    "Trace without model call cannot claim model_id."
                )

            if self.raw_model_output is not None:
                raise ValueError(
                    "Trace without model call cannot contain raw model output."
                )

        if (
            self.raw_model_output is not None
            and not self.model_called
        ):
            raise ValueError(
                "Raw model output requires a model call."
            )

        if self.final_status == "answered":
            if self.final_answer is None:
                raise ValueError(
                    "Answered trace requires final_answer."
                )

            if self.error_code is not None:
                raise ValueError(
                    "Answered trace cannot contain error_code."
                )

        elif self.final_status == "error":
            if self.error_code is None:
                raise ValueError(
                    "Error trace requires error_code."
                )

        elif self.final_status == "abstained":
            if self.error_code is not None:
                raise ValueError(
                    "Abstained trace cannot contain error_code."
                )

        return self


def validate_source_grounded_benchmark_case_v01(
    case: SourceGroundedBenchmarkCaseV01,
) -> SourceGroundedBenchmarkCaseV01:
    """Revalidate a case even after model_copy(update=...) use."""

    if not isinstance(
        case,
        SourceGroundedBenchmarkCaseV01,
    ):
        raise TypeError(
            "Expected SourceGroundedBenchmarkCaseV01."
        )

    return (
        SourceGroundedBenchmarkCaseV01
        .model_validate(
            case.model_dump(
                mode="python"
            )
        )
    )


def canonical_benchmark_case_bytes_v01(
    case: SourceGroundedBenchmarkCaseV01,
) -> bytes:
    """Canonical frozen benchmark representation.

    The digest is a reproducibility identifier for the benchmark
    artifact. It is not a signature, reviewer credential, or license
    assertion.
    """

    validated = (
        validate_source_grounded_benchmark_case_v01(
            case
        )
    )

    return json.dumps(
        validated.model_dump(
            mode="json"
        ),
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")


def benchmark_case_digest_v01(
    case: SourceGroundedBenchmarkCaseV01,
) -> str:
    """Return lowercase SHA-256 of the whole frozen case."""

    return sha256(
        canonical_benchmark_case_bytes_v01(
            case
        )
    ).hexdigest()


def validate_benchmark_execution_trace_v01(
    trace: BenchmarkExecutionTraceV01,
) -> BenchmarkExecutionTraceV01:
    """Revalidate one candidate execution trace."""

    if not isinstance(
        trace,
        BenchmarkExecutionTraceV01,
    ):
        raise TypeError(
            "Expected BenchmarkExecutionTraceV01."
        )

    return (
        BenchmarkExecutionTraceV01
        .model_validate(
            trace.model_dump(
                mode="python"
            )
        )
    )
