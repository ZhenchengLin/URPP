"""Tests for frozen URPP 14E math-fidelity cases."""
import json
from pathlib import Path
import pytest
from app.services.course_knowledge.math_fidelity_cases_14e_v01 import (
    MATH_FIDELITY_CASE_IDS_14E_V01, PINNED_PACK_SHA256_14E_V01,
    build_math_fidelity_cases_14e_v01, math_fidelity_case_digests_14e_v01,
)
from app.services.course_knowledge.source_grounded_benchmark_v01 import (
    benchmark_case_digest_v01, validate_source_grounded_benchmark_case_v01,
)
IDS=("14e-M07-COPY","14e-M07-EXPLAIN","14e-M10-COPY","14e-M15-COPY",
     "14e-M16-COPY","14e-M15-M16","14e-M07-MISSING","14e-M07-FOLLOW")
REV="20654a6a6f607efe7d51fde54f29819957b34ec2212e09af1f2cf3b0f874179f"
FROZEN_DIGESTS={'14e-M07-COPY': '7259465621e9b22fecb32cf2ef228a74ad2420fdc25809b79f74fd5d27545357',
 '14e-M07-EXPLAIN': '0459bd1068c1679fb92e726bc888bcc24495c7883c4fc4fed5b6d5c09657aac2',
 '14e-M07-FOLLOW': 'e0e11559f612b7925891af4c1e01bba0ec84c8d3327ff78e6ae242c24dc14836',
 '14e-M07-MISSING': '15d50fccf80ce43ab7d8ce224dd81d8a54d1863164c8ddbb021c2d7e5ab5a5e2',
 '14e-M10-COPY': '2d64c130070c961f92f96c7d986a87241b0b629642590ac4448edabe47148dfe',
 '14e-M15-COPY': '3b010ac72e0be6a1c3e489b57915845e70f1f4f8ba0059fb13cc2806f2843940',
 '14e-M15-M16': '9a6f0e9f0d7e4ce1e8a2e1a3baa168957297b6a138e98d50c43800fce4bfc7f2',
 '14e-M16-COPY': '15a010b233ede9ba94e3affccb5f2f5283814d146393986b14fec21a94f9d8e4'}
PACK=Path.home()/"Library"/"Application Support"/"URPP"/"local-learning-demo-v01"/"packs"/f"{PINNED_PACK_SHA256_14E_V01}.json"

def test_case_count_and_order():
    c=build_math_fidelity_cases_14e_v01()
    assert len(c)==8 and tuple(x.case_id for x in c)==IDS
    assert MATH_FIDELITY_CASE_IDS_14E_V01==IDS

def test_each_case_validates():
    for c in build_math_fidelity_cases_14e_v01():
        validate_source_grounded_benchmark_case_v01(c)

def test_frozen_digests():
    assert math_fidelity_case_digests_14e_v01()==FROZEN_DIGESTS

def test_scope_revision():
    for c in build_math_fidelity_cases_14e_v01():
        assert all(r.source_revision==REV for r in c.source_scope_refs)

def test_missing_and_follow_contracts():
    d={c.case_id:c for c in build_math_fidelity_cases_14e_v01()}
    m=d["14e-M07-MISSING"]
    assert m.expected_outcome=="abstain"
    assert all(not r.source_id.endswith("-excerpt-4") for r in m.source_scope_refs)
    assert len(d["14e-M07-FOLLOW"].prior_turns)==1

def test_gold_latex_has_no_display_delimiters():
    for c in build_math_fidelity_cases_14e_v01():
        assert all("$$" not in e.normalized_latex for e in c.gold.equations)

def test_refs_match_local_pack_if_available():
    if not PACK.exists(): pytest.skip("pinned pack unavailable")
    raw=json.loads(PACK.read_text()); fs=("source_id","source_revision","source_locator","content_sha256")
    meta={s["source_id"]:{k:s[k] for k in fs} for s in raw["sources"]}
    for c in build_math_fidelity_cases_14e_v01():
        for r in c.source_scope_refs:
            assert {k:getattr(r,k) for k in fs}==meta[r.source_id]

def test_two_builds_have_equal_digests():
    def x(): return {c.case_id:benchmark_case_digest_v01(c) for c in build_math_fidelity_cases_14e_v01()}
    assert x()==x()==FROZEN_DIGESTS
