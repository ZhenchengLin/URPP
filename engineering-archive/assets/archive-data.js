"use strict";

/*
 * URPP Engineering Archive
 *
 * Initial curated records from existing conversation logs.
 *
 * The full Implementation 0–13 historical mapping has not
 * yet been verified against the original roadmap and local
 * Git history.
 *
 * Do not convert missing history into invented milestones.
 */

window.URPP_ARCHIVE = {

    archiveVersion: "0.1",

    phase: "Reply 1 / 10",

    chapters: Array.from(
        {length: 14},
        (_, index) => ({
            number: index,
            title: `Implementation ${index}`,
            status: "HISTORICAL_MAPPING_PENDING",
            description:
                "Pending verification against the original Roadmap, Git History, and design documents. " +
                "This placeholder does not mean the stage had no real implementation.",
        })
    ),

    timeline: [

        {
            commit: "93e3680",
            title: "Initial URPP V0 Architecture",
            description:
                "Set up the initial engineering skeleton, core domain directories, " +
                "product spec, architecture docs, course model, and teaching-policy design.",
            status: "CHAT_LOG_CONFIRMED",
            source: "SRC-001",
        },

        {
            commit: "0dda011",
            title: "Student State Update Engine V0 Design",
            description:
                "Wrote the early Student State Update Engine design document.",
            status: "CHAT_LOG_CONFIRMED",
            source: "SRC-002",
        },

        {
            commit: "f61cd4b",
            title: "Student State Estimator Specification V0.2",
            description:
                "Revised the Student State Estimator design.",
            status: "CHAT_LOG_CONFIRMED",
            source: "SRC-002",
        },

        {
            commit: "2de3b83",
            title: "Evidence Schema and Eligibility Policy V0.2",
            description:
                "Added the V0.2 Evidence Schema and Eligibility Policy. " +
                "The saved focused test record is 9 passed.",
            status: "CHAT_LOG_CONFIRMED",
            source: "SRC-002",
        },

        {
            commit: "e52095f",
            title: "13C-2B SQLite Recovery Integration Tests",
            description:
                "Fixed wrong test assertions and verified SQLite recovery of the Personalized Numeric " +
                "Session. " +
                "Focused tests 26 passed; full regression 324 passed.",
            status: "CHAT_LOG_CONFIRMED",
            source: "SRC-003",
        },

        {
            commit: "b8abf71",
            title: "13E-3C Local Numeric Teaching CLI",
            description:
                "Completed the local teaching CLI. " +
                "Went through a mismatch between the post-commit State recovery time and the next Decision " +
                "time. " +
                "Final full regression 468 passed.",
            status: "USER_LOG_CONFIRMED",
            source: "SRC-004",
        },

        {
            commit: "ccb4a5a",
            title: "13E-4A Numeric Attempt Provenance Snapshot",
            description:
                "Added a Snapshot Service that reads real Assignments, Attempts, and " +
                "application-reported help events. " +
                "Full regression 473 passed.",
            status: "USER_LOG_CONFIRMED",
            source: "SRC-005",
        },

        {
            commit: "a82b2ad",
            title: "13E-4B Numeric Provenance Review Candidate",
            description:
                "Added a source fingerprint and re-check mechanism. " +
                "A Candidate is not a review approval. " +
                "Full regression 479 passed.",
            status: "USER_LOG_CONFIRMED",
            source: "SRC-006",
        },
    ],

    cases: [

        {
            id: "BUG-13C-2B-001",

            title:
                "An existing Agent object was mistaken " +
                "for an executed assessment action",

            implementation: "13C-2B",

            status: "RESOLVED",

            symptom:
                "The test verifying that an explanation request does not wrongly issue a " +
                "Numeric Assignment failed. " +
                "The first run gave 1 failed, 25 passed.",

            error:
                "assert not stack.last_assessment_agent\n" +
                "AssertionError: assert not <RecordingAgent object ...>",

            investigation:
                "The test assertion checked whether the Agent object existed, " +
                "not whether the Agent actually executed an Assessment. " +
                "An object being created does not mean an Assessment happened.",

            resolution:
                "The original fix record shows two wrong assertions in the new test file were adjusted. " +
                "No production code was changed.",

            verification:
                "Targeted: 26 passed\n" +
                "Full backend: 324 passed\n" +
                "Commit: e52095f",

            source: "SRC-003",
        },

        {
            id: "BUG-13E-3C-001",

            title:
                "State estimation timestamp precedes " +
                "a committed numeric submission",

            implementation: "13E-3C",

            status: "RESOLVED",

            symptom:
                "After the student submitted an answer, the Attempt was written to SQLite, " +
                "but the CLI still reported the answer as not accepted. " +
                "The first test run was 2 failed, 57 passed.",

            error:
                "State-estimation time precedes submission.\n" +
                "The submission may already be committed.",

            investigation:
                "The as_of taken by the CLI was earlier than the " +
                "submitted_at the Repository generated later. " +
                "The error happened in the state-estimation step after the Attempt was committed.",

            resolution:
                "For this specific error, resume() is used " +
                "to recover the committed result and avoid resubmitting the answer. " +
                "The first fix used a recovery time one second in the future, " +
                "which caused a time-ordering error in the next Decision. " +
                "Finally the one-second offset was removed, and the next Decision " +
                "uses the snapshot time of the recovered Student State.",

            verification:
                "Initial tests: 2 failed, 57 passed\n" +
                "Intermediate tests: 3 failed, 2 passed\n" +
                "Final CLI: 5 passed\n" +
                "Targeted regression: 59 passed\n" +
                "Full backend: 468 passed\n" +
                "Commit: b8abf71",

            source: "SRC-004",
        },

        {
            id: "BUG-13E-3C-002",

            title:
                "Decision timestamp precedes " +
                "the recovered Student State snapshot",

            implementation: "13E-3C",

            status: "RESOLVED",

            symptom:
                "The first post-submission recovery fix succeeded, " +
                "but a new validation error occurred when creating the next Decision.",

            error:
                "Decision cannot precede its Student State snapshot.",

            investigation:
                "State recovery used now_utc() + 1 second; " +
                "Decision creation used a plain now_utc(). " +
                "So the Decision time was earlier than the Student State snapshot time.",

            resolution:
                "Recovery uses a fresh current time, " +
                "and the next Decision uses the recovered State's as_of. " +
                "The Decision Engine's time-ordering constraint is not changed.",

            verification:
                "CLI: 5 passed\n" +
                "Targeted regression: 59 passed\n" +
                "Full backend: 468 passed\n" +
                "Commit: b8abf71",

            source: "SRC-004",
        },

    ],

    sources: [

        {
            id: "SRC-001",
            kind: "Original terminal log",
            title: "Initial URPP V0 architecture",
            locator: "Git commit 93e3680",
            note:
                "Initialization and first-commit logs from the original chat. " +
                "Still to be cross-checked with the local Git History.",
        },

        {
            id: "SRC-002",
            kind: "Design and commit logs",
            title: "Early Student State evolution",
            locator:
                "Commits 0dda011, f61cd4b, 2de3b83",
            note:
                "Early Student State design and Evidence Schema logs.",
        },

        {
            id: "SRC-003",
            kind: "Original pytest and git log",
            title: "13C-2B integration-test repair",
            locator:
                "Commit e52095f; " +
                "test_personalized_numeric_session_sqlite_v01.py",
            note:
                "Contains the original failure, the wrong assertion, " +
                "the post-fix tests, and the final commit record.",
        },

        {
            id: "SRC-004",
            kind: "Original user-supplied test logs",
            title: "13E-3C timestamp failures",
            locator:
                "Commit b8abf71; " +
                "run_local_numeric_lesson_v01.py",
            note:
                "Contains the two failures, the fix process, " +
                "the final CLI tests, and the full regression.",
        },

        {
            id: "SRC-005",
            kind: "Original user-supplied test log",
            title: "13E-4A provenance snapshot",
            locator:
                "Commit ccb4a5a; " +
                "numeric_attempt_provenance_snapshot_v01.py",
            note:
                "Records the SQLite Snapshot integration tests and commit result.",
        },

        {
            id: "SRC-006",
            kind: "Original user-supplied test log",
            title: "13E-4B review candidate",
            locator:
                "Commit a82b2ad; " +
                "numeric_provenance_review_candidate_v01.py",
            note:
                "Records the source check, full regression, and commit result.",
        },

    ],

    gaps: [

        "Obtain the original Implementation 0–13 Roadmap " +
        "to confirm the exact stage names, boundaries, and order.",

        "Obtain the complete Git Commit History " +
        "to check how each implementation corresponds to the design files.",

        "Git History does not necessarily include failing test logs from before a commit. " +
        "These must be recovered from the original chats, terminal output, or saved logs.",

        "Distinguish design reasons recorded at the time from after-the-fact analysis based on the code now.",

        "Check whether the same feature went through multiple implementations, " +
        "abandonment, refactoring, or rollback.",

        "Determine the full boundaries of each Implementation 13 sub-stage; " +
        "not every later feature belongs in 13E.",

        "Architecture V2 and NeoHorse-1 research belong to later planning " +
        "and must not be written as features completed in Implementation 0–13.",
    ],

};
