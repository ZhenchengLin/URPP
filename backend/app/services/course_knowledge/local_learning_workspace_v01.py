"""Single-user local material workspace for Implementation 14D.

Persist original local material and a digest-bound Course Pack, then reuse
URPP's existing durable Professor Chat Service. This module is neither an
HTTP interface nor an authentication boundary. No chat counts as mastery.
"""

from __future__ import annotations

import os
import re
import secrets
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Callable

from app.services.course_knowledge.course_pack_v01 import CoursePackV01
from app.services.course_knowledge.local_chat_context_v01 import (
    ConversationMessageV01, LocalChatContextV01,
)
from app.llm.local_general_knowledge_gateway_v01 import LocalGeneralKnowledgeGatewayV01
from app.services.course_knowledge.knowledge_fetch_v01 import (
    canonical_pack_bytes_v01,
    course_pack_digest_v01,
)
from app.services.course_knowledge.local_chat_store_v01 import (
    LocalChatSnapshotV01,
    LocalChatStoreV01,
)
from app.services.course_knowledge.local_material_import_v01 import (
    build_local_material_pack_v01,
)
from app.services.course_knowledge.local_pdf_import_v01 import (
    build_local_pdf_pack_v01,
)
from app.services.course_knowledge.local_professor_chat_service_v01 import (
    LocalProfessorChatServiceV01,
    LocalProfessorChatTurnV01,
)


PACK_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
COURSE_ID = "local-upload-course"
OBJECTIVE_ID = "uploaded-material"
PROFILE_ID = "local-learning-demo-profile"
STUDENT_ID = "local-learning-demo-student"  # synthetic; NOT learner state
REPO_ROOT = Path(__file__).resolve().parents[4]


@dataclass(frozen=True)
class ImportedLocalCourseV01:
    snapshot: LocalChatSnapshotV01
    filename: str
    source_count: int
    pages_without_text: tuple[int, ...]


class LocalLearningWorkspaceV01:
    """Store immutable uploads and pinned packs outside Git, with chat in SQLite."""

    def __init__(
        self, *, data_root: Path, gateway_factory: Callable,
        general_gateway_factory: Callable | None = None,
    ) -> None:
        if not callable(gateway_factory):
            raise TypeError("gateway_factory must be callable.")
        if general_gateway_factory is not None and not callable(general_gateway_factory):
            raise TypeError("general_gateway_factory must be callable.")

        supplied = Path(data_root).expanduser().absolute()
        if supplied.is_symlink():
            raise ValueError("Workspace path cannot be a symlink.")
        self.root = supplied.resolve()
        if self.root.is_relative_to(REPO_ROOT):
            raise ValueError("Workspace must be outside the Git repository.")

        # Do not change the permissions of any pre-existing user directory.
        for directory in (self.root, self.root / "uploads", self.root / "packs"):
            if directory.is_symlink():
                raise ValueError("Workspace directory cannot be a symlink.")
            directory.mkdir(parents=True, exist_ok=True, mode=0o700)
            if directory.stat().st_mode & 0o077:
                raise PermissionError("Workspace directory is not private (0700 required).")

        database = self.root / "chat.sqlite3"
        if database.is_symlink():
            raise ValueError("Chat database cannot be a symlink.")
        self.store = (
            LocalChatStoreV01.open_existing(database)
            if database.exists()
            else LocalChatStoreV01.create_new(database)
        )
        self._gateway_factory = gateway_factory
        self._general_gateway_factory = (
            general_gateway_factory or LocalGeneralKnowledgeGatewayV01
        )

    @staticmethod
    def _save_once(directory: Path, name: str, content: bytes) -> None:
        """Publish a complete immutable file; never overwrite an existing one."""
        destination = directory / name
        temporary = directory / (f".{name}.{secrets.token_hex(12)}.tmp")
        fd = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            try:
                os.link(temporary, destination)
            except FileExistsError:
                if (
                    destination.is_symlink()
                    or not destination.is_file()
                    or destination.read_bytes() != content
                ):
                    raise ValueError("Existing stored file conflicts with the upload.")
        finally:
            temporary.unlink(missing_ok=True)

    def _load_pack(self, pack_sha256: str) -> CoursePackV01:
        if type(pack_sha256) is not str or not PACK_DIGEST.fullmatch(pack_sha256):
            raise ValueError("Invalid Course Pack digest.")
        path = self.root / "packs" / f"{pack_sha256}.json"
        if path.is_symlink() or not path.is_file():
            raise LookupError("Exact saved Course Pack not found.")
        pack = CoursePackV01.model_validate_json(path.read_bytes())
        if course_pack_digest_v01(pack) != pack_sha256:
            raise ValueError("Stored Course Pack digest mismatch.")
        return pack

    def _service(self, pack_sha256: str) -> LocalProfessorChatServiceV01:
        pack = self._load_pack(pack_sha256)
        return LocalProfessorChatServiceV01(
            chat_store=self.store,
            pack=pack,
            gateway=self._gateway_factory(),
            local_profile_id=PROFILE_ID,
            synthetic_student_id=STUDENT_ID,
        )

    def import_document(
        self,
        *,
        filename: str,
        content: bytes,
        objective_description: str,
        allow_local_teaching: bool,
    ) -> ImportedLocalCourseV01:
        """Validate all material before saving any bytes or creating a session."""
        options = dict(
            filename=filename,
            course_id=COURSE_ID,
            objective_id=OBJECTIVE_ID,
            objective_description=objective_description,
            allow_local_teaching=allow_local_teaching,
        )
        if type(filename) is not str:
            raise ValueError("Material filename is required.")
        if filename.lower().endswith(".pdf"):
            imported = build_local_pdf_pack_v01(pdf_bytes=content, **options)
            pack = imported.pack
            blank_pages = imported.pages_without_text
        else:
            pack = build_local_material_pack_v01(file_bytes=content, **options)
            blank_pages = ()

        encoded_pack = canonical_pack_bytes_v01(pack)
        pack_digest = course_pack_digest_v01(pack)
        original_digest = sha256(content).hexdigest()
        self._save_once(self.root / "uploads", f"{original_digest}.bin", content)
        self._save_once(self.root / "packs", f"{pack_digest}.json", encoded_pack)

        service = self._service(pack_digest)
        session_id = service.start_session(objective_id=OBJECTIVE_ID)
        return ImportedLocalCourseV01(
            snapshot=service.resume_session(
                session_id=session_id, objective_id=OBJECTIVE_ID,
            ),
            filename=filename,
            source_count=len(pack.sources),
            pages_without_text=blank_pages,
        )

    def resume(self, *, pack_sha256: str, session_id: str) -> LocalChatSnapshotV01:
        """Recover an exact digest-pinned session and full stored history."""
        return self._service(pack_sha256).resume_session(
            session_id=session_id, objective_id=OBJECTIVE_ID,
        )

    def explain(
        self,
        *,
        pack_sha256: str,
        session_id: str,
        question: str,
        expected_message_count: int,
    ) -> LocalProfessorChatTurnV01:
        """Reuse the existing teaching pipeline and atomic two-message write."""
        return self._service(pack_sha256).send_explanation(
            session_id=session_id,
            objective_id=OBJECTIVE_ID,
            student_text=question,
            expected_message_count=expected_message_count,
        )

    def explain_general(
        self, *, pack_sha256: str, session_id: str,
        question: str, expected_message_count: int,
    ) -> LocalChatSnapshotV01:
        """User-selected general answer, with no Course Pack text sent to model.

        Session binding is still verified. No model call on invalid/stale input.
        The fixed provenance label is persisted with the answer; it is not
        an LLM-authored citation. Use a single process for this local pilot.
        """
        if (type(expected_message_count) is not int
                or expected_message_count < 0 or expected_message_count % 2):
            raise ValueError("Expected message count must be a nonnegative even integer.")
        # Reuse exact pack/session verification rather than looking up a user-
        # supplied Session ID without its pinned Course Pack identity.
        snapshot = self.resume(pack_sha256=pack_sha256, session_id=session_id)
        if len(snapshot.messages) != expected_message_count:
            raise ValueError("Chat Session advanced since the caller loaded its history.")
        # Do not pass prior course dialogue or uploaded excerpts into the
        # source-free general path, even when the gateway is injected.
        student = ConversationMessageV01(role="student", text=question)
        context = LocalChatContextV01(
            course_id=snapshot.course_id,
            objective_id=snapshot.objective_id,
            current_student_message=student.text,
        )
        gateway = self._general_gateway_factory()
        if not callable(getattr(gateway, "generate_general", None)):
            raise TypeError("General gateway must implement generate_general.")
        answer = gateway.generate_general(context=context)
        if type(answer) is not str or not answer.strip() or len(answer) > 1300:
            raise ValueError("General answer is empty or oversized.")
        # This label survives Session recovery; it cannot be supplied by model.
        labeled = "[GENERAL KNOWLEDGE — not from uploaded material]\n" + answer.strip()
        ConversationMessageV01(role="professor", text=labeled)
        return self.store.append_exchange(
            session_id=snapshot.session_id,
            local_profile_id=snapshot.local_profile_id,
            course_id=snapshot.course_id,
            objective_id=snapshot.objective_id,
            pack_id=snapshot.pack_id,
            pack_revision=snapshot.pack_revision,
            pack_sha256=snapshot.pack_sha256,
            expected_message_count=expected_message_count,
            student_text=context.current_student_message,
            professor_text=labeled,
        )
