"""Offline, exact-integer LU(2x2) output checks for a *narrow* URPP pilot.

This checks a machine-readable candidate, not the truthfulness of accompanying
teaching prose. It never authorizes student presentation, grades an answer,
creates Mastery Evidence, accesses an LLM, or changes persistent state.
"""

from dataclasses import dataclass
from typing import Any, Mapping


Matrix2 = tuple[tuple[int, int], tuple[int, int]]


@dataclass(frozen=True)
class LU2x2CheckV01:
    accepted_arithmetic: bool
    errors: tuple[str, ...]
    # This arithmetic result must NOT be interpreted as validated teaching.
    teaching_prose_reviewed: bool = False


def _matrix(value: Any) -> Matrix2 | None:
    if (
        not isinstance(value, (list, tuple))
        or len(value) != 2
        or any(
            not isinstance(row, (list, tuple))
            or len(row) != 2
            or any(type(entry) is not int for entry in row)
            for row in value
        )
    ):
        return None
    return ((value[0][0], value[0][1]), (value[1][0], value[1][1]))


def _multiply(left: Matrix2, right: Matrix2) -> Matrix2:
    return (
        (
            left[0][0] * right[0][0] + left[0][1] * right[1][0],
            left[0][0] * right[0][1] + left[0][1] * right[1][1],
        ),
        (
            left[1][0] * right[0][0] + left[1][1] * right[1][0],
            left[1][0] * right[0][1] + left[1][1] * right[1][1],
        ),
    )


def verify_lu2x2_candidate_v01(
    *,
    matrix_a: Any,
    candidate: Mapping[str, Any],
    expected_source_locator: str,
    expected_provenance: str,
) -> LU2x2CheckV01:
    """Fail closed on malformed, inconsistent or incorrect *structured* data.

    Scope: integer 2x2 A, nonzero pivot, integer multiplier, no row exchange.
    Does not parse or certify any natural-language explanation or citations.
    """
    a = _matrix(matrix_a)
    if a is None:
        raise ValueError("A must be a 2x2 matrix of exact integers.")
    if not isinstance(candidate, Mapping):
        raise TypeError("candidate must be a mapping.")
    if not isinstance(expected_source_locator, str) or not expected_source_locator:
        raise ValueError("expected_source_locator must be nonempty.")
    if expected_provenance not in ("lecture_example", "new_practice"):
        raise ValueError("Unsupported provenance label.")

    pivot, upper = a[0]
    lower, bottom = a[1]
    if pivot == 0 or lower % pivot != 0:
        raise ValueError("Pilot requires a nonzero pivot and integer multiplier.")
    m = lower // pivot
    expected_e: Matrix2 = ((1, 0), (-m, 1))
    expected_l: Matrix2 = ((1, 0), (m, 1))
    expected_u: Matrix2 = ((pivot, upper), (0, bottom - m * upper))
    expected_product = a
    errors: list[str] = []

    def require(test: bool, message: str) -> None:
        if not test:
            errors.append(message)

    require(type(candidate.get("multiplier")) is int and candidate["multiplier"] == m,
            "multiplier must equal a21/a11 (not the signed row coefficient)")
    require(candidate.get("row_operation") == f"R2 <- R2 - {m}*R1",
            "row_operation does not match the required elimination")

    actual: dict[str, Matrix2 | None] = {}
    for field, expected in (
        ("E", expected_e), ("L", expected_l),
        ("U", expected_u), ("product", expected_product),
    ):
        actual[field] = _matrix(candidate.get(field))
        require(actual[field] is not None and actual[field] == expected,
                f"{field} is malformed or mathematically incorrect")

    if actual["E"] is not None and actual["U"] is not None:
        require(_multiply(actual["E"], a) == actual["U"],
                "candidate E*A does not equal candidate U")
    if actual["L"] is not None and actual["U"] is not None:
        product = _multiply(actual["L"], actual["U"])
        require(product == a, "candidate L*U does not equal original A")
        if actual["product"] is not None:
            require(product == actual["product"],
                    "candidate product does not equal candidate L*U")

    require(candidate.get("source_locator") == expected_source_locator,
            "source_locator mismatch")
    require(candidate.get("provenance") == expected_provenance,
            "provenance mismatch")
    return LU2x2CheckV01(accepted_arithmetic=not errors, errors=tuple(errors))
