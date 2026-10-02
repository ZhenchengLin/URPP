"""Load immutable verified-equation registry snapshots outside Git."""

from __future__ import annotations

from pathlib import Path
import re

from app.services.course_knowledge.verified_equation_registry_v01 import (
    VerifiedEquationRegistryV01,
)

_PACK_SHA256 = re.compile(r"^[0-9a-f]{64}$")

def verified_equation_registry_path_v01(
    *,
    data_root: Path,
    pack_sha256: str,
) -> Path:
    """Return the pack-bound external registry path without creating it."""

    if (
        type(pack_sha256) is not str
        or not _PACK_SHA256.fullmatch(pack_sha256)
    ):
        raise ValueError("Invalid Course Pack digest.")

    root = Path(data_root).expanduser().absolute()

    if root.is_symlink():
        raise ValueError("Workspace path cannot be a symlink.")

    return (
        root
        / "verified-equations"
        / f"{pack_sha256}.json"
    )

def load_verified_equation_registry_v01(
    *,
    data_root: Path,
    pack_sha256: str,
) -> VerifiedEquationRegistryV01 | None:
    """Load one optional pack-keyed registry snapshot, failing closed.

    Absence means that no deterministic verified equations are available.
    A present snapshot must be a regular, non-symlink JSON file that
    validates as the existing immutable registry contract.
    """

    path = verified_equation_registry_path_v01(
        data_root=data_root,
        pack_sha256=pack_sha256,
    )

    if path.is_symlink():
        raise ValueError(
            "Verified-equation registry cannot be a symlink."
        )

    if not path.exists():
        return None

    if not path.is_file():
        raise ValueError(
            "Verified-equation registry must be a regular file."
        )

    return VerifiedEquationRegistryV01.model_validate_json(
        path.read_bytes()
    )
