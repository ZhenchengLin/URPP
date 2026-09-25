"""14C-5A: local, opt-in, policy-bounded LU tool experiment.

An untrusted router (eventually Jev) can *propose* a known capability and data,
but cannot execute Python, choose source permissions, authorize a teaching turn,
or issue assessment/mastery evidence. The caller supplies an already fetched,
digest-pinned Course Knowledge result. This module has no model, network,
database, persistence, or student-facing delivery operation.

Only the MIT LU pilot objective and exact-integer, no-swap 2x2 arithmetic are
supported. Its arithmetic verification DOES NOT certify prose or sources.
"""

from dataclasses import dataclass
from typing import Any, Literal

from app.services.course_knowledge.knowledge_fetch_v01 import (
    CourseKnowledgeFetchResultV01,
)
from app.services.course_knowledge.models_v01 import CourseKnowledgeContextV01
from app.services.course_knowledge.verification_framework_v01 import (
    LU2X2_CAPABILITY_V01,
    VerificationRequestV01,
    VerificationResultV01,
    local_math_registry_v01,
)

MIT_LU_COURSE_V01 = "mit-18-06sc-fall-2011"
MIT_LU_OBJECTIVE_V01 = "derive-and-verify-lu-no-row-exchanges-2x2"
Matrix2 = tuple[tuple[int, int], tuple[int, int]]


@dataclass(frozen=True)
class MathToolProposalV01:
    """Untrusted routing suggestion: no arbitrary code, file paths or URLs."""

    capability_id: str
    action: str
    matrix_a: Any


@dataclass(frozen=True)
class LocalLUToolResultV01:
    """Immutable tool output for developer inspection, never a teaching trace."""

    matrix_a: Matrix2
    multiplier: int
    elimination: Matrix2
    lower: Matrix2
    upper: Matrix2
    product: Matrix2
    source_locator: str
    pack_sha256: str
    verification: VerificationResultV01
    status: Literal["developer_audit_only"] = "developer_audit_only"

    def reference_data(self) -> dict[str, Any]:
        """Give a local language model a fresh copy; it cannot mutate this result."""
        def rows(matrix: Matrix2) -> list[list[int]]:
            return [list(row) for row in matrix]

        return {
            "A": rows(self.matrix_a),
            "multiplier": self.multiplier,
            "row_operation": f"R2 <- R2 - {self.multiplier}*R1",
            "E": rows(self.elimination),
            "L": rows(self.lower),
            "U": rows(self.upper),
            "product": rows(self.product),
            "source_locator": self.source_locator,
            "provenance": "new_practice",
        }


def _bounded_matrix(value: Any) -> Matrix2:
    """Reject unsupported shapes/types and huge integers before arithmetic."""
    if (not isinstance(value, (list, tuple)) or len(value) != 2
        or any(not isinstance(row, (list, tuple)) or len(row) != 2
               for row in value)
        or any(type(number) is not int or abs(number) > 1_000_000
               for row in value for number in row)):
        raise ValueError("Tool accepts only bounded, exact-integer 2x2 matrices.")
    return ((value[0][0], value[0][1]), (value[1][0], value[1][1]))


def _multiply(left: Matrix2, right: Matrix2) -> Matrix2:
    return (
        (left[0][0] * right[0][0] + left[0][1] * right[1][0],
         left[0][0] * right[0][1] + left[0][1] * right[1][1]),
        (left[1][0] * right[0][0] + left[1][1] * right[1][0],
         left[1][0] * right[0][1] + left[1][1] * right[1][1]),
    )


def execute_lu_tool_proposal_v01(
    *, fetched: CourseKnowledgeFetchResultV01,
    proposal: MathToolProposalV01,
) -> LocalLUToolResultV01:
    """Local pilot policy authorizes a *named tool*, then verifies its output.

    The fetched result must be supplied by CourseKnowledgeFetcherV01; this
    module cannot establish who is authorized to publish source metadata.
    Unsupported routing suggestions fail closed; there is no fallback tool.
    """
    if not isinstance(fetched, CourseKnowledgeFetchResultV01):
        raise TypeError("Expected a fetched Course Knowledge result.")
    if not isinstance(proposal, MathToolProposalV01):
        raise TypeError("Expected a structured tool proposal.")
    if proposal.action != "compute_lu" or proposal.capability_id != LU2X2_CAPABILITY_V01:
        raise ValueError("Router proposal is not allowed by the LU pilot policy.")
    if (fetched.knowledge.course_id != MIT_LU_COURSE_V01
        or fetched.knowledge.objective_id != MIT_LU_OBJECTIVE_V01):
        raise ValueError("Tool is not authorized for this course/objective scope.")

    # Revalidate even when a model_copy(update=...) might have bypassed Pydantic.
    knowledge = CourseKnowledgeContextV01.model_validate(
        fetched.knowledge.model_dump(mode="json")
    )
    if len(knowledge.sources) != 1 or fetched.source_refs != knowledge.objective.source_refs:
        raise ValueError("Pilot requires exactly one matching referenced source.")
    source = knowledge.sources[0]

    matrix = _bounded_matrix(proposal.matrix_a)
    (a, b), (c, d) = matrix
    if a == 0 or c % a != 0:
        raise ValueError("Tool requires a nonzero pivot and integer elimination multiplier.")
    m = c // a
    e: Matrix2 = ((1, 0), (-m, 1))
    l: Matrix2 = ((1, 0), (m, 1))
    u: Matrix2 = ((a, b), (0, d - m * b))
    product = _multiply(l, u)
    if _multiply(e, matrix) != u or product != matrix:
        raise RuntimeError("Independent reference equations failed.")

    # The tool result, not Qwen's copied matrix fields, is checked here.
    candidate = {
        "multiplier": m,
        "row_operation": f"R2 <- R2 - {m}*R1",
        "E": e, "L": l, "U": u, "product": product,
        "source_locator": source.source_locator,
        "provenance": "new_practice",
    }
    result = local_math_registry_v01().verify(VerificationRequestV01(
        capability_id=LU2X2_CAPABILITY_V01,
        inputs={"matrix_a": matrix},
        candidate=candidate,
        context={
            "expected_source_locator": source.source_locator,
            "expected_provenance": "new_practice",
        },
    ))
    if not result.arithmetic_accepted or result.status != "passed":
        raise RuntimeError("Independent arithmetic verification failed closed.")

    return LocalLUToolResultV01(
        matrix_a=matrix, multiplier=m, elimination=e, lower=l,
        upper=u, product=product, source_locator=source.source_locator,
        pack_sha256=fetched.pack_sha256, verification=result,
    )
