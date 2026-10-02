from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.services.course_knowledge.models_v01 import (
    CourseSourceRefV01,
)
from app.services.course_knowledge.verified_equation_record_v01 import (
    VerifiedEquationRecordV01,
)
from app.services.course_knowledge.verified_equation_registry_store_v01 import (
    load_verified_equation_registry_v01,
    verified_equation_registry_path_v01,
)
from app.services.course_knowledge.verified_equation_registry_v01 import (
    VerifiedEquationRegistryV01,
)

PACK_SHA = "a" * 64

def _registry() -> VerifiedEquationRegistryV01:
    return VerifiedEquationRegistryV01(
        records=(
            VerifiedEquationRecordV01(
                record_id="synthetic-equation-7",
                record_revision="synthetic-record-v01",
                equation_label="7",
                source_ref=CourseSourceRefV01(
                    source_id="synthetic-source-1",
                    source_revision="synthetic-source-v01",
                    source_locator="synthetic-page-1",
                    content_sha256="b" * 64,
                ),
                equation_locator="synthetic-equation-7",
                normalized_latex=r"x = y + z",
                review_status="source_checked",
                reviewer_id="synthetic-reviewer",
                reviewed_at=datetime(
                    2026, 1, 1, tzinfo=timezone.utc
                ),
            ),
        ),
    )

def test_missing_external_registry_returns_none(
    tmp_path: Path,
):
    assert (
        load_verified_equation_registry_v01(
            data_root=tmp_path,
            pack_sha256=PACK_SHA,
        )
        is None
    )

def test_external_registry_round_trip(
    tmp_path: Path,
):
    path = verified_equation_registry_path_v01(
        data_root=tmp_path,
        pack_sha256=PACK_SHA,
    )
    path.parent.mkdir()
    expected = _registry()
    path.write_text(
        expected.model_dump_json(),
        encoding="utf-8",
    )

    actual = load_verified_equation_registry_v01(
        data_root=tmp_path,
        pack_sha256=PACK_SHA,
    )

    assert actual == expected

def test_external_registry_symlink_fails_closed(
    tmp_path: Path,
):
    target = tmp_path / "target.json"
    target.write_text(
        _registry().model_dump_json(),
        encoding="utf-8",
    )

    path = verified_equation_registry_path_v01(
        data_root=tmp_path,
        pack_sha256=PACK_SHA,
    )
    path.parent.mkdir()
    path.symlink_to(target)

    with pytest.raises(
        ValueError,
        match="cannot be a symlink",
    ):
        load_verified_equation_registry_v01(
            data_root=tmp_path,
            pack_sha256=PACK_SHA,
        )

@pytest.mark.parametrize(
    "digest",
    ["", "A" * 64, "a" * 63, "../bad"],
)
def test_invalid_pack_digest_rejected(
    tmp_path: Path,
    digest: str,
):
    with pytest.raises(ValueError):
        verified_equation_registry_path_v01(
            data_root=tmp_path,
            pack_sha256=digest,
        )
