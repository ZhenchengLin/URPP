"""14C-3: explicit, digest-pinned Course Knowledge fetch boundary.

This is an in-memory *contract and store adapter*, not a remote service,
production access-control system, or automatic source-license verification.
The fetcher always uses the 14A-2 source/approval/digest checks; permission
and review metadata in a user-supplied pack remain untrusted assertions.
No LLM, filesystem, network, persistence, Student State, or Mastery operations.
"""

from dataclasses import dataclass
from hashlib import sha256
import json
import re
from types import MappingProxyType
from typing import Mapping, Protocol

from app.services.course_knowledge.course_pack_v01 import (
    CoursePackV01,
    resolve_course_knowledge_v01,
)
from app.services.course_knowledge.models_v01 import (
    CourseKnowledgeContextV01,
    CourseSourceRefV01,
)


_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


def _required(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a nonblank string.")
    return value


def canonical_pack_bytes_v01(pack: CoursePackV01) -> bytes:
    """Canonical digest over the *whole* pack; not a signature or authority proof."""
    if not isinstance(pack, CoursePackV01):
        raise TypeError("Expected CoursePackV01.")
    # Revalidation detects invalid model_copy(update=...) mutations.
    validated = CoursePackV01.model_validate(pack.model_dump(mode="json"))
    return json.dumps(
        validated.model_dump(mode="json"),
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")


def course_pack_digest_v01(pack: CoursePackV01) -> str:
    return sha256(canonical_pack_bytes_v01(pack)).hexdigest()


@dataclass(frozen=True)
class CourseKnowledgeFetchRequestV01:
    course_id: str
    objective_id: str
    pack_id: str
    pack_revision: str
    expected_pack_sha256: str

    def __post_init__(self) -> None:
        for name in ("course_id", "objective_id", "pack_id", "pack_revision"):
            _required(getattr(self, name), name)
        if not isinstance(self.expected_pack_sha256, str) or not _SHA256.fullmatch(
            self.expected_pack_sha256
        ):
            raise ValueError("expected_pack_sha256 must be an exact lowercase SHA-256.")


@dataclass(frozen=True)
class CourseKnowledgeFetchResultV01:
    """Validated teaching input only; no inference about authenticity or delivery."""
    knowledge: CourseKnowledgeContextV01
    pack_id: str
    pack_revision: str
    pack_sha256: str
    source_refs: tuple[CourseSourceRefV01, ...]


class CoursePackStorePortV01(Protocol):
    """Adapter returns an exact named pack snapshot or raises LookupError.

    Future SQLite/remote adapters must not perform silent 'latest' fallback.
    The fetcher validates returned identity, full digest and source scope.
    """

    def load_exact(self, *, course_id: str, pack_id: str,
                   pack_revision: str) -> CoursePackV01:
        ...


class InMemoryCoursePackStoreV01:
    """Explicit snapshots for testing. Stores validated canonical bytes, not aliases."""

    def __init__(self, packs: tuple[CoursePackV01, ...]) -> None:
        entries: dict[tuple[str, str, str], bytes] = {}
        for pack in packs:
            encoded = canonical_pack_bytes_v01(pack)
            validated = CoursePackV01.model_validate_json(encoded)
            key = (validated.course_id, validated.pack_id, validated.pack_revision)
            if key in entries:
                raise ValueError("Duplicate Course Pack snapshot identity.")
            entries[key] = encoded
        self._entries: Mapping[tuple[str, str, str], bytes] = MappingProxyType(entries)

    def load_exact(self, *, course_id: str, pack_id: str,
                   pack_revision: str) -> CoursePackV01:
        key = (course_id, pack_id, pack_revision)
        try:
            encoded = self._entries[key]
        except (KeyError, TypeError) as exc:
            raise LookupError("Exact Course Pack snapshot not found.") from exc
        return CoursePackV01.model_validate_json(encoded)


class CourseKnowledgeFetcherV01:
    """Central lookup policy; fail closed before exposing any source content."""

    def __init__(self, store: CoursePackStorePortV01) -> None:
        self._store = store

    def fetch(self, request: CourseKnowledgeFetchRequestV01) -> CourseKnowledgeFetchResultV01:
        if not isinstance(request, CourseKnowledgeFetchRequestV01):
            raise TypeError("Expected CourseKnowledgeFetchRequestV01.")
        # Never choose a course or revision on the student's behalf.
        pack = self._store.load_exact(
            course_id=request.course_id,
            pack_id=request.pack_id,
            pack_revision=request.pack_revision,
        )
        if not isinstance(pack, CoursePackV01):
            raise TypeError("Course Pack store returned an invalid type.")
        # Revalidate, including every source digest, before reading identity.
        pack = CoursePackV01.model_validate(pack.model_dump(mode="json"))
        if (pack.course_id, pack.pack_id, pack.pack_revision) != (
            request.course_id, request.pack_id, request.pack_revision
        ):
            raise ValueError("Course Pack store returned the wrong snapshot identity.")
        digest = course_pack_digest_v01(pack)
        if digest != request.expected_pack_sha256:
            raise ValueError("Course Pack content digest mismatch.")
        knowledge = resolve_course_knowledge_v01(
            pack=pack,
            course_id=request.course_id,
            objective_id=request.objective_id,
            expected_pack_revision=request.pack_revision,
        )
        return CourseKnowledgeFetchResultV01(
            knowledge=knowledge,
            pack_id=pack.pack_id,
            pack_revision=pack.pack_revision,
            pack_sha256=digest,
            source_refs=knowledge.objective.source_refs,
        )
