"""14C-2: explicit, in-memory verification capability routing.

Knowledge retrieval and source permission are separate concerns.  A successful
capability check is *not* certified teaching prose, assessment, mastery, or
permission to present.  No LLM, filesystem, database, or network calls here.
"""

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Literal, Mapping, Protocol

from app.services.course_knowledge.lu2x2_verification_v01 import (
    verify_lu2x2_candidate_v01,
)


LU2X2_CAPABILITY_V01 = "math.lu2x2.integer_no_swap.v01"
VerificationStatusV01 = Literal["passed", "failed", "unsupported"]


@dataclass(frozen=True)
class VerificationRequestV01:
    """Caller-selected verifier and inputs; routing never guesses a capability."""

    capability_id: str
    inputs: Mapping[str, Any]
    candidate: Mapping[str, Any]
    context: Mapping[str, Any]


@dataclass(frozen=True)
class VerificationResultV01:
    """Scope-limited check; neither 'passed' nor 'failed' authorizes delivery."""

    capability_id: str
    status: VerificationStatusV01
    verified_claims: tuple[str, ...]
    unverified_claims: tuple[str, ...]
    errors: tuple[str, ...]

    @property
    def arithmetic_accepted(self) -> bool:
        """Only this LU adapter currently claims structured arithmetic."""
        return (
            self.capability_id == LU2X2_CAPABILITY_V01
            and self.status == "passed"
            and "structured_lu2x2_arithmetic" in self.verified_claims
        )


class VerificationCapabilityV01(Protocol):
    capability_id: str

    def verify(self, request: VerificationRequestV01) -> VerificationResultV01:
        ...


_UNVERIFIED_LU = (
    "teaching_prose",
    "source_authenticity_and_permissions",
    "student_mastery_and_assessment",
)


class LU2x2VerificationAdapterV01:
    """Translate one narrow LU case into the previously tested 14C-1 gate."""

    capability_id = LU2X2_CAPABILITY_V01

    def verify(self, request: VerificationRequestV01) -> VerificationResultV01:
        if request.capability_id != self.capability_id:
            raise ValueError("Verifier/capability mismatch.")

        try:
            source_locator = request.context["expected_source_locator"]
            provenance = request.context["expected_provenance"]
            matrix_a = request.inputs["matrix_a"]
            checked = verify_lu2x2_candidate_v01(
                matrix_a=matrix_a,
                candidate=request.candidate,
                expected_source_locator=source_locator,
                expected_provenance=provenance,
            )
        except (KeyError, TypeError, ValueError) as exc:
            # Bad requests are failed, never silently routed to another verifier.
            return VerificationResultV01(
                capability_id=self.capability_id,
                status="failed",
                verified_claims=(),
                unverified_claims=_UNVERIFIED_LU,
                errors=(f"Invalid LU verification request: {type(exc).__name__}",),
            )

        return VerificationResultV01(
            capability_id=self.capability_id,
            status="passed" if checked.accepted_arithmetic else "failed",
            verified_claims=("structured_lu2x2_arithmetic",) if checked.accepted_arithmetic else (),
            unverified_claims=_UNVERIFIED_LU,
            errors=checked.errors,
        )


class VerificationRegistryV01:
    """An explicit static registry; never auto-loads arbitrary student code."""

    def __init__(self, capabilities: tuple[VerificationCapabilityV01, ...]) -> None:
        registry: dict[str, VerificationCapabilityV01] = {}
        for capability in capabilities:
            name = capability.capability_id
            if not isinstance(name, str) or not name.strip() or name in registry:
                raise ValueError("Invalid or duplicate verification capability ID.")
            registry[name] = capability
        self._capabilities: Mapping[str, VerificationCapabilityV01] = MappingProxyType(registry)

    def verify(self, request: VerificationRequestV01) -> VerificationResultV01:
        if not isinstance(request, VerificationRequestV01):
            raise TypeError("Expected VerificationRequestV01.")
        if not isinstance(request.capability_id, str) or not request.capability_id.strip():
            raise ValueError("Capability ID must be nonempty.")

        capability = self._capabilities.get(request.capability_id)
        if capability is None:
            return VerificationResultV01(
                capability_id=request.capability_id,
                status="unsupported",
                verified_claims=(),
                unverified_claims=("all_candidate_claims",),
                errors=("Requested verification capability is not registered.",),
            )
        if (
            not isinstance(request.inputs, Mapping)
            or not isinstance(request.candidate, Mapping)
            or not isinstance(request.context, Mapping)
        ):
            return VerificationResultV01(
                capability_id=request.capability_id,
                status="failed",
                verified_claims=(),
                unverified_claims=("all_candidate_claims",),
                errors=("Verification inputs, candidate, and context must be mappings.",),
            )
        result = capability.verify(request)
        if not isinstance(result, VerificationResultV01) or result.capability_id != request.capability_id:
            raise RuntimeError("Verification capability violated the result contract.")
        if result.status not in ("passed", "failed", "unsupported"):
            raise RuntimeError("Verification capability returned an unknown status.")
        if result.status != "passed" and result.verified_claims:
            raise RuntimeError("Nonpassing verification cannot assert verified claims.")
        if result.status == "passed" and (not result.verified_claims or result.errors):
            raise RuntimeError("Passing verification must name claims and have no errors.")
        return result


def local_math_registry_v01() -> VerificationRegistryV01:
    """Explicit local pilot registry: only the 14C-1 LU checker is enabled."""
    return VerificationRegistryV01((LU2x2VerificationAdapterV01(),))
