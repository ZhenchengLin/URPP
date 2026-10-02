"""URPP 14D-4B4D4 — Local Professor Benchmark Adapter v0.1.

Run one frozen SourceGroundedBenchmarkCaseV01 through the current
URPP Local Professor candidate and return a BenchmarkExecutionTraceV01.

This is a candidate-specific adapter around the architecture-neutral
benchmark contract.

The benchmark case defines WHAT should happen.
This adapter records WHAT the current URPP candidate actually did.

The adapter uses the real:
- CoursePackV01;
- Course Knowledge validation;
- Local Course Source Selector;
- Personalized Decision Engine;
- StructuredProfessorAdapterV01;
- LocalOllamaProfessorGatewayV01;
- Professor output contract.

Chat persistence is intercepted at the final append boundary so the
generated Student/Professor exchange is NOT written.

Benchmark gold, required-evidence rationale, prohibited errors, and
expected outcome are NEVER added to the Professor request.

Current v0.1 limitation:
- prior benchmark conversation turns are not yet replayed.
  Follow-up benchmark execution will be added separately rather than
  silently approximating production conversation state.

This module does NOT:
- evaluate L0/L1/L2/L3;
- determine whether generated facts are semantically correct;
- modify Student State or Mastery Evidence;
- use VerifiedEquationRecord unless the candidate architecture itself
  is later changed to do so;
- write to the user's existing local-learning database.
"""

from __future__ import annotations

from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path
import re
import tempfile
from typing import Callable

from app.llm.local_ollama_professor_gateway_v01 import (
    LocalOllamaProfessorGatewayV01,
    LocalProfessorGenerationErrorV01,
)

from app.services.course_knowledge.course_pack_v01 import (
    CoursePackV01,
    resolve_course_knowledge_v01,
)

from app.services.course_knowledge.local_chat_store_v01 import (
    LocalChatStoreV01,
)

from app.services.course_knowledge.local_professor_chat_service_v01 import (
    LocalProfessorChatServiceV01,
)

from app.services.course_knowledge.models_v01 import (
    CourseSourceRefV01,
)

from app.services.course_knowledge.source_grounded_benchmark_v01 import (
    BenchmarkExecutionTraceV01,
    SourceGroundedBenchmarkCaseV01,
    benchmark_case_digest_v01,
    validate_source_grounded_benchmark_case_v01,
)

from app.services.course_knowledge.structured_professor_adapter_v01 import (
    ProfessorOutputContractErrorV01,
)


_IDENTIFIER = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$"
)

CANDIDATE_SYSTEM_V01 = (
    "urpp-local-professor-current-chain"
)

TRACE_VERSION_V01 = "v0.1"


def _required_identifier(
    value: str,
    *,
    name: str,
) -> str:
    if (
        type(value) is not str
        or not _IDENTIFIER.fullmatch(value)
    ):
        raise ValueError(
            f"{name} must be a valid bounded identifier."
        )

    return value


def _required_candidate_version(
    value: str,
) -> str:
    if (
        type(value) is not str
        or not value.strip()
        or len(value) > 256
    ):
        raise ValueError(
            "candidate_version must contain "
            "1–256 nonblank characters."
        )

    return value


def _source_ref_from_model_payload(
    source: dict,
) -> CourseSourceRefV01:
    expected = {
        "source_id",
        "source_revision",
        "source_locator",
        "content",
    }

    if (
        type(source) is not dict
        or set(source) != expected
        or not all(
            type(value) is str
            for value in source.values()
        )
    ):
        raise RuntimeError(
            "Observed Professor source payload is invalid."
        )

    return CourseSourceRefV01(
        source_id=source["source_id"],
        source_revision=source["source_revision"],
        source_locator=source["source_locator"],
        content_sha256=sha256(
            source["content"].encode(
                "utf-8"
            )
        ).hexdigest(),
    )


def _observed_contract_validity(
    *,
    execution_error: Exception | None,
    append_arguments: dict | None,
    raw_model_output: str | None,
) -> bool | None:
    """Classify only what the adapter can actually establish.

    True:
        the candidate completed successfully, or reached the
        final persistence boundary after upstream validation.

    False:
        an observed model/Professor output violated its explicit
        generation or Professor output contract.

    None:
        the failure occurred at a boundary for which this adapter
        cannot truthfully attribute the failure to the Professor
        output contract.

    In particular, a downstream Chat-message size failure must
    not be mislabeled as a Professor output-contract failure.
    """

    if execution_error is None:
        return True

    if append_arguments is not None:
        return True

    if isinstance(
        execution_error,
        ProfessorOutputContractErrorV01,
    ):
        return False

    if isinstance(
        execution_error,
        LocalProfessorGenerationErrorV01,
    ):
        # If provider/model content was observed and the real
        # gateway rejected it, an output-contract failure was
        # directly observed. A transport failure with no output
        # does not establish a contract verdict.
        return (
            False
            if raw_model_output is not None
            else None
        )

    return None


def run_local_professor_benchmark_case_v01(
    *,
    case: SourceGroundedBenchmarkCaseV01,
    pack: CoursePackV01,
    objective_id: str,
    candidate_version: str,
    run_id: str,
    run_started_at: datetime,
    model_id: str = "qwen3.5:4b",
    transport: Callable[[dict], dict] | None = None,
) -> BenchmarkExecutionTraceV01:
    """Run one frozen case through the current Local Professor.

    Configuration errors in the benchmark harness itself raise.

    Candidate execution failures are represented as an error
    BenchmarkExecutionTraceV01 when possible.

    The returned trace is a summary trace. raw_model_output records
    the latest exact provider message content observed by this adapter.
    A future detailed event-log contract may preserve provider retries
    as separate events.
    """

    checked_case = (
        validate_source_grounded_benchmark_case_v01(
            case
        )
    )

    if not isinstance(
        pack,
        CoursePackV01,
    ):
        raise TypeError(
            "Expected CoursePackV01."
        )

    checked_pack = (
        CoursePackV01.model_validate(
            pack.model_dump(
                mode="python"
            )
        )
    )

    if (
        type(objective_id) is not str
        or not objective_id.strip()
        or len(objective_id) > 128
    ):
        raise ValueError(
            "objective_id must contain "
            "1–128 nonblank characters."
        )

    _required_identifier(
        run_id,
        name="run_id",
    )

    candidate_version = (
        _required_candidate_version(
            candidate_version
        )
    )

    if (
        not isinstance(
            run_started_at,
            datetime,
        )
        or run_started_at.tzinfo is None
        or run_started_at.utcoffset()
        is None
    ):
        raise ValueError(
            "run_started_at must be timezone-aware."
        )

    if checked_case.prior_turns:
        raise ValueError(
            "Current Professor benchmark adapter "
            "does not yet support prior_turns."
        )

    # Resolve the exact candidate-visible objective and source scope
    # independently of benchmark gold.
    knowledge = resolve_course_knowledge_v01(
        pack=checked_pack,
        course_id=checked_pack.course_id,
        objective_id=objective_id,
        expected_pack_revision=(
            checked_pack.pack_revision
        ),
    )

    # For a fair benchmark run, the candidate must receive exactly the
    # frozen source scope and source ordering defined by the case.
    #
    # required_evidence and gold are NOT used here.
    if (
        checked_case.source_scope_refs
        != knowledge.objective.source_refs
    ):
        raise ValueError(
            "Benchmark source scope must exactly match "
            "the candidate Course Objective source scope."
        )

    case_sha256 = (
        benchmark_case_digest_v01(
            checked_case
        )
    )

    observed = {
        "model_called": False,
        "selected_source_refs": None,
        "raw_model_output": None,
        "append_arguments": None,
    }

    def instrument(
        request: dict,
    ) -> dict:
        observed["model_called"] = True

        try:
            user_content = (
                request["messages"][1][
                    "content"
                ]
            )

            professor_payload = json.loads(
                user_content
            )

            sources = professor_payload[
                "sources"
            ]

        except (
            KeyError,
            IndexError,
            TypeError,
            json.JSONDecodeError,
        ) as exc:
            raise RuntimeError(
                "Could not inspect real Professor request."
            ) from exc

        selected_refs = tuple(
            _source_ref_from_model_payload(
                source
            )
            for source in sources
        )

        previous = observed[
            "selected_source_refs"
        ]

        if previous is None:
            observed[
                "selected_source_refs"
            ] = selected_refs

        elif previous != selected_refs:
            raise RuntimeError(
                "Professor source scope changed "
                "across provider attempts."
            )

        response = (
            LocalOllamaProfessorGatewayV01
            ._post_local(request)
            if transport is None
            else transport(request)
        )

        if type(response) is dict:
            message = response.get(
                "message"
            )

            if type(message) is dict:
                raw = message.get(
                    "content"
                )

                if (
                    type(raw) is str
                    and raw.strip()
                ):
                    observed[
                        "raw_model_output"
                    ] = raw

        return response

    with tempfile.TemporaryDirectory(
        prefix="urpp-benchmark-professor-",
    ) as folder:
        database = (
            Path(folder)
            / "chat.sqlite3"
        )

        store = (
            LocalChatStoreV01.create_new(
                database
            )
        )

        gateway = (
            LocalOllamaProfessorGatewayV01(
                model=model_id,
                transport=instrument,
            )
        )

        service = (
            LocalProfessorChatServiceV01(
                chat_store=store,
                pack=checked_pack,
                gateway=gateway,
                local_profile_id=(
                    "benchmark-local-profile"
                ),
                synthetic_student_id=(
                    "benchmark-synthetic-student"
                ),
            )
        )

        session_id = (
            service.start_session(
                objective_id=objective_id,
            )
        )

        before = (
            service.resume_session(
                session_id=session_id,
                objective_id=objective_id,
            )
        )

        def suppress_append(
            **kwargs,
        ):
            if (
                observed[
                    "append_arguments"
                ]
                is not None
            ):
                raise RuntimeError(
                    "Professor attempted more than "
                    "one benchmark exchange write."
                )

            observed[
                "append_arguments"
            ] = dict(kwargs)

            # Return the unchanged snapshot so the real
            # service can finish constructing its result
            # without persisting the exchange.
            return before

        # Intercept only the final persistence boundary.
        # All upstream candidate logic remains real.
        store.append_exchange = (
            suppress_append
        )

        execution_error = None
        professor_text = None
        answer_status = None

        try:
            turn = (
                service.send_explanation(
                    session_id=session_id,
                    objective_id=objective_id,
                    student_text=(
                        checked_case.question
                    ),
                    expected_message_count=0,
                )
            )

            professor_text = (
                turn.professor_text
            )

            write_arguments = observed[
                "append_arguments"
            ]

            if write_arguments is None:
                raise RuntimeError(
                    "Professor did not reach "
                    "the persistence boundary."
                )

            answer_status = (
                write_arguments.get(
                    "answer_status"
                )
            )

            if answer_status not in {
                "course_grounded",
                "insufficient_evidence",
            }:
                raise RuntimeError(
                    "Professor produced an "
                    "unexpected answer status."
                )

        except Exception as exc:
            execution_error = exc

        after = (
            service.resume_session(
                session_id=session_id,
                objective_id=objective_id,
            )
        )

        if (
            after.messages
            != before.messages
            or after.answer_statuses
            != before.answer_statuses
        ):
            raise RuntimeError(
                "Benchmark isolation failure: "
                "disposable Session changed."
            )

    model_called = bool(
        observed["model_called"]
    )

    selected_source_refs = (
        observed[
            "selected_source_refs"
        ]
        or ()
    )

    raw_model_output = observed[
        "raw_model_output"
    ]

    contract_valid = (
        _observed_contract_validity(
            execution_error=execution_error,
            append_arguments=observed[
                "append_arguments"
            ],
            raw_model_output=raw_model_output,
        )
    )

    if execution_error is None:
        if (
            answer_status
            == "course_grounded"
        ):
            final_status = "answered"

        else:
            final_status = "abstained"

        error_code = None
        final_answer = professor_text

    else:
        final_status = "error"

        error_code = type(
            execution_error
        ).__name__

        final_answer = None
        answer_status = None

    return BenchmarkExecutionTraceV01(
        trace_version=TRACE_VERSION_V01,
        run_id=run_id,
        case_id=checked_case.case_id,
        case_sha256=case_sha256,
        candidate_system=(
            CANDIDATE_SYSTEM_V01
        ),
        candidate_version=(
            candidate_version
        ),
        run_started_at=(
            run_started_at
        ),
        selected_source_refs=(
            selected_source_refs
        ),

        # The current production Professor chain does not
        # use the Verified Equation request resolver.
        extracted_equation_labels=(),
        verified_record_ids=(),

        model_called=model_called,
        model_id=(
            model_id
            if model_called
            else None
        ),
        contract_valid=contract_valid,

        # The final exchange persistence call was intercepted.
        session_write_performed=False,

        system_answer_status=(
            answer_status
        ),
        final_status=final_status,
        raw_model_output=(
            raw_model_output
        ),
        final_answer=final_answer,
        error_code=error_code,
    )
