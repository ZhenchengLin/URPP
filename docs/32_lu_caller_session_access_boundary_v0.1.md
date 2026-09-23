# URPP LU Caller and Session Access Boundary v0.1

**Status:** Prospective design contract — not implemented

**Starting commit:** `8f27c7c`

**Scope:** Bounded 2x2 LU teaching pilot

## 1. Existing implementation

The current LU Focus Classification component identifies
a candidate focus without verifying its source.

The Session Preflight component checks whether a stored
Numeric Session matches supplied identifiers.

Neither component authenticates the caller, authorizes
Session access, resolves an authorized LU Focus, or
authorizes student-facing teaching.

The existing NanoJev implementation remains a
developer-only untrusted Shadow Evaluation component.

## 2. Core security distinction

Authentication answers:

Who is making this request?

Session access authorization answers:

May this verified caller access this particular
student, course, objective, and session?

Focus source verification answers:

Did the registered LU Focus originate from an accepted
source within the authorized workflow?

Teaching delivery authorization answers:

May this particular teaching result be delivered through
the specified student-facing workflow?

Passing one check does not imply passing another.

## 3. Proposed trusted caller boundary

A future server-side authentication layer must validate
the caller using a supported authentication mechanism.

The resulting verified principal must be established by
that trusted server-side boundary.

Client-supplied student IDs, usernames, request flags,
serialized principal objects, or model outputs must not
be treated as authentication evidence.

A plain Python dataclass or a caller-supplied
`authenticated=True` field is not an authentication
credential.

The current URPP repository does not yet provide the
complete student-facing authentication workflow required
by this contract.

## 4. Proposed Session access authorization

For a student acting on their own behalf, the application
must establish the verified student's identity independently
of the request's claimed `student_id`.

It must then verify access to the requested stored Session.

The existing Numeric Session Repository can check stored
Session identity and scope, but it cannot independently
establish caller identity or access permissions.

An authorized workflow must bind the authenticated
principal to the relevant student record and permitted
Session before permitting Session-scoped operations.

Knowledge of a valid Session ID and matching student,
course, and objective IDs is insufficient.

Access by instructors, administrators, guardians, or other
roles requires separately defined policies and tests.
Such access must not be inferred from this document.

## 5. Proposed decision sequence

1. Authenticate the caller at the trusted entry point.

2. Resolve the authorized student identity from the
   verified principal and the applicable access policy.

3. Check the requested Session access using server-side
   identity and permission information.

4. Load the stored Session and validate its student,
   course, objective, and session identifiers.

5. Classify the requested LU Focus.

6. Verify that a supported candidate Focus originated
   from an accepted source within the authorized workflow.

7. Only after the preceding checks may a future
   Authorized Focus Resolution component make a focus
   available to the deterministic LU Router.

8. Separately enforce the teaching-generation and
   student-delivery policies.

No step may silently use a model-generated Focus to
replace missing authorization information.

## 6. Failure behavior

Unauthenticated caller:

Reject access before retrieving student-specific records.

Caller without Session permission:

Reject access even if the supplied Session IDs match
an existing stored Session.

Missing or conflicting LU Focus:

Do not guess a Focus or execute the LU Router.

Unsupported LU Focus:

Do not silently map the request to a supported Focus.

Missing Session or mismatched scope:

Fail closed. Do not interpret the error as evidence
that the student has no prior learning activity.

Unverified Focus source:

Do not promote the candidate Focus to an authorized
resolution.

Failure in any authorization step:

Do not continue by falling back to NanoJev or another
model-generated teaching choice.

## 7. Separation from NanoJev

NanoJev shadow proposals must not:

- authenticate a caller;
- authorize Session access;
- declare their own source trusted;
- replace an authorized LU Focus;
- directly control the existing LU Renderer;
- update Student State, Teaching Trace, or Mastery Evidence;
- authorize student-facing delivery.

Choice probabilities are not authentication confidence,
student mastery estimates, or verified teaching-quality
measurements.

## 8. Required tests before integration

The future implementation must include offline tests for:

- valid authenticated caller with permitted Session access;
- unauthenticated caller;
- authenticated caller accessing another student's Session;
- invalid or revoked Session access;
- missing stored Session;
- mismatched course and objective;
- client-supplied forged authorization flags;
- fabricated or modified principal-like objects;
- missing, conflicting, and unsupported Focus;
- an unsupported source claiming a supported Focus;
- NanoJev output attempting to supply an authorized Focus;
- no teaching execution after any failed authorization check;
- no unauthorized Student State or evidence writes.

A test showing that Session IDs match is not a substitute
for a test of the caller's access permissions.

## 9. Implementation gate

First establish the actual authentication mechanism and
the authoritative source of Session access permissions.

Then implement a separately tested authorization service
whose trusted inputs are provided by the authenticated
application boundary.

Do not modify the existing LU Router or Renderer during
this design stage.

Do not introduce a public LU teaching API or grant student
delivery authority until the authentication, Session
authorization, Focus provenance, and delivery policies
have each been implemented and reviewed.

The present document records requirements only.
It does not establish that any proposed authentication
or authorization mechanism has been implemented.
