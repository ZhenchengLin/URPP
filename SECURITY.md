# Security Policy — URPP (Personal Professor)

URPP is a **local-first, experimental learning project**. This document describes how to report security issues, what is currently supported, and the security boundaries contributors must preserve. It is not a guarantee that the application is secure or suitable for public deployment.

## 1. Supported versions and deployment scope

| Version / deployment | Security support |
| --- | --- |
| Current `design/logical-decision-engine` development branch | Best-effort investigation and fixes; no guaranteed response time or production support. |
| Older commits, archived prototypes, and forks | Not actively supported. |
| Internet-accessible, multi-user, or production deployment | **Not supported.** Do not expose the developer demo to a LAN, public IP, tunnel, or reverse proxy. |

The local Professor, local learning workspace, and existing Chat Store are **developer-only, single-user components**. A fixed `local_profile_id` or a Session ID is **not authentication**, and course approval metadata is **not proof of licensing or reviewer identity**. A loopback-bound web server is not sufficient protection against malicious local processes or browser-origin attacks.

## 2. Privately reporting a vulnerability

**Do not publish a reproducible exploit, affected private file, API key, personal information, or security-sensitive log in a public issue or pull request.**

1. If the repository has GitHub **Private vulnerability reporting** enabled, open its **Security → Advisories → Report a vulnerability** form.
2. If private reporting is unavailable, use a private contact method explicitly published by the repository maintainer to request a secure reporting channel. Do **not** put the vulnerability details in a public issue while arranging contact.
3. Include affected commit(s), component, impact, minimal steps to reproduce using **synthetic data**, and a suggested mitigation, if known. Do not send real learner documents or credentials.

Maintainers should acknowledge reports and coordinate fixes and disclosure when possible; no fixed response or remediation SLA is currently promised. Enable GitHub private vulnerability reporting before inviting external testing.

## 3. Protected assets and trust boundaries

- **Sensitive local data:** uploaded course materials, extracted PDF text, generated Course Packs, chat history, SQLite databases, credentials, and any future student information.
- **Untrusted inputs:** document bytes, PDF internals, filenames, document text, student questions, model outputs, HTTP requests, and client-supplied Session identifiers.
- **Local model:** Ollama responses can be incorrect, adversarially influenced by document contents, or inconsistent with the Course Pack. Model output must not grant permissions, execute commands, change policy, or create assessment evidence on its own.
- **Source references:** Source IDs, content SHA-256, Course Pack digests, and version binding establish **integrity/identity checks**, not source truth, user authorization, or copyright ownership.

Never treat locally supplied `approved` metadata, a successful model response, or possession of a Session ID as an authorization decision.

## 4. Minimum rules for local use

- Run the developer web server **only on `127.0.0.1`**. Do not use `--host 0.0.0.0`, port forwarding, public tunnels, shared hosting, or a reverse proxy. Any web release must independently enforce Host/Origin/CSRF boundaries and explicitly address DNS rebinding and local-network requests.
- Run Ollama through the existing fixed loopback endpoint. Do not substitute a cloud endpoint or enable model telemetry/upload without an explicit, documented choice by the operator.
- Store original uploads, Course Packs, and SQLite chat **outside the Git repository**, in a private user-owned directory. Require owner-only directory permissions (`0700`) and owner-only sensitive file permissions (`0600`) where supported. Protect local storage with OS account security and disk encryption.
- Never commit or share `.env` files, tokens, student material, PDF uploads, chat databases, logs containing document text, or actual learner records. `.gitignore` is a backup precaution, **not a secret scanner or an authorization boundary**.
- Use only material the operator is permitted to use for local teaching. Do not distribute uploaded third-party content or extracted text merely because an importer accepted it.
- Avoid sensitive or regulated personal data in the development demo. If such data is ever needed, first add an explicit data-handling and access-control design.

## 5. Mandatory application controls before exposing a Web API

- **Request controls:** accept only known file types; enforce byte limits before buffering or Base64 decoding; bound request bodies, filenames, page counts, extracted text, excerpts, and message lengths; reject malformed input with predictable errors.
- **File/path controls:** never use user-supplied filenames as output paths. Use server-generated identifiers, reject traversal and symlinks, verify storage ownership and permissions, and test parent-directory/symlink-race behavior. Publish immutable files atomically; never overwrite an existing file with conflicting content.
- **PDF controls:** treat PDFs as hostile input; use the supported parser version, catch parsing failures, enforce processing/resource limits, and state clearly that scanned PDFs require a separate OCR workflow. Do not execute embedded PDF content, external references, or document-supplied commands.
- **HTTP controls:** bind to loopback and reject untrusted `Host` and `Origin` values; protect state-changing routes against cross-origin requests and CSRF; limit request size and concurrency; disable automatic public-facing documentation in the demo. **These controls do not replace authentication.**
- **Session controls:** bind every chat action to the exact Session ID, local profile, course, learning objective, Course Pack revision, and whole-Pack digest; reject mismatches and stale expected message counts. Before introducing multiple users, implement real authentication, per-user authorization, session expiry/revocation, and authorization tests.
- **Database controls:** use parameterized SQL and atomic message-pair commits. Avoid sharing a SQLite connection across threads. Establish connection cleanup, cross-process write/concurrency behavior, backup, recovery, deletion, and retention policies before claiming production readiness.
- **AI controls:** isolate document text and student messages as untrusted data; prevent prompt injection from overriding role, tool, or source constraints. Validate structured model output and every source reference against the active Course Pack. On invalid citations or unsupported answers, fail closed or label the limitation; do not fabricate a citation.
- **Learning-state controls:** generated explanations, chat text, and self-reported understanding are **not** Mastery Evidence. Only an independently validated assessment flow may update Student State.
- **Output controls:** render untrusted document and model text as text, not `innerHTML`; do not execute generated JavaScript or shell commands. Avoid reflecting full internal paths, document contents, credentials, or stack traces in HTTP error responses.

## 6. Dependency and change hygiene

- Keep the Python environment isolated. Declare direct dependencies in `backend/pyproject.toml`; constrain versions, review dependency changes, and maintain an environment-specific lock or pinned resolution for reproducible release builds.
- Review Python, FastAPI, `pypdf`, SQLite/SQLAlchemy, frontend, and Ollama updates for security advisories. Enable repository dependency alerts and automated update proposals where available; review changes before merging.
- Run targeted tests while developing and the **full backend regression** before merging or releasing an integrated feature. Include negative tests for untrusted documents, invalid digest/revision, path traversal, malformed Base64/PDF, permissions, cross-origin requests, concurrent chat writes, and failed model generation.
- Review every staged file before commit: `git diff --cached --name-status` and `git diff --cached --check`. Stage only intended paths. Never use `git add .` or destructive repository cleanup as a shortcut when unrelated work is present.
- Use branch protection/rulesets and required status checks for shared development branches. Store credentials only in the provider's secret store; never put them in Git history or a generated patch.

## 7. Incident response and data handling

If a secret or sensitive file is committed or exposed: stop sharing the affected artifact; revoke/rotate any exposed credential **first**; restrict access; assess which data and commits are affected; then coordinate removal of Git history/caches where appropriate. Deleting a file in a new commit alone does **not** remove it from earlier commits or clones.

For suspected local data exposure: stop the demo server, preserve minimal non-sensitive diagnostic evidence, assess uploads/SQLite/logs/backups, patch the underlying issue, and notify affected people if required. Do not silently delete user data during a repair.

The development workspace currently has **no complete retention, account deletion, encryption-at-rest, or production incident-response program**. Document and implement these before handling real multi-user data.

## 8. Security release gate

Do not describe URPP as production-ready until the team has verified: authenticated users and authorized per-user data access; browser-origin and request-size defenses; secure filesystem and database lifecycle; dependency/security scanning; prompt-injection and output-validation tests; data retention/deletion and recovery; incident reporting; and end-to-end testing of the exact released build.

This policy is guidance and reporting information; implementation and automated verification are still required for every control above.
