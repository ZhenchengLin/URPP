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
                "等待原始 Roadmap、Git History 和设计文档核对。" +
                "当前占位不代表该阶段没有实际实现。",
        })
    ),

    timeline: [

        {
            commit: "93e3680",
            title: "Initial URPP V0 Architecture",
            description:
                "建立最初的工程骨架、核心领域目录、" +
                "产品规范、架构文档、课程模型和教学策略设计。",
            status: "CHAT_LOG_CONFIRMED",
            source: "SRC-001",
        },

        {
            commit: "0dda011",
            title: "Student State Update Engine V0 Design",
            description:
                "建立早期 Student State Update Engine 设计文档。",
            status: "CHAT_LOG_CONFIRMED",
            source: "SRC-002",
        },

        {
            commit: "f61cd4b",
            title: "Student State Estimator Specification V0.2",
            description:
                "修订 Student State Estimator 的设计。",
            status: "CHAT_LOG_CONFIRMED",
            source: "SRC-002",
        },

        {
            commit: "2de3b83",
            title: "Evidence Schema and Eligibility Policy V0.2",
            description:
                "增加 V0.2 Evidence Schema、Eligibility Policy。" +
                "保存的专项测试记录为 9 passed。",
            status: "CHAT_LOG_CONFIRMED",
            source: "SRC-002",
        },

        {
            commit: "e52095f",
            title: "13C-2B SQLite Recovery Integration Tests",
            description:
                "修复错误测试断言，验证 Personalized Numeric " +
                "Session 的 SQLite 恢复。" +
                "专项测试 26 passed，完整回归 324 passed。",
            status: "CHAT_LOG_CONFIRMED",
            source: "SRC-003",
        },

        {
            commit: "b8abf71",
            title: "13E-3C Local Numeric Teaching CLI",
            description:
                "完成本地教学 CLI。" +
                "经历提交后 State 恢复时间和下一轮 Decision " +
                "时间不一致的问题。" +
                "最终完整回归 468 passed。",
            status: "USER_LOG_CONFIRMED",
            source: "SRC-004",
        },

        {
            commit: "ccb4a5a",
            title: "13E-4A Numeric Attempt Provenance Snapshot",
            description:
                "新增读取真实 Assignment、Attempt 和" +
                "应用程序报告的帮助事件的 Snapshot Service。" +
                "完整回归 473 passed。",
            status: "USER_LOG_CONFIRMED",
            source: "SRC-005",
        },

        {
            commit: "a82b2ad",
            title: "13E-4B Numeric Provenance Review Candidate",
            description:
                "新增来源指纹和重新检查机制。" +
                "Candidate 不构成审核批准。" +
                "完整回归 479 passed。",
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
                "验证 explanation request 不会错误发放 " +
                "Numeric Assignment 的测试失败。" +
                "第一次运行结果为 1 failed, 25 passed。",

            error:
                "assert not stack.last_assessment_agent\n" +
                "AssertionError: assert not <RecordingAgent object ...>",

            investigation:
                "测试断言检验了 Agent 对象是否存在，" +
                "却没有准确检验 Agent 是否真正执行了 Assessment。" +
                "对象已创建并不等于 Assessment 已发生。",

            resolution:
                "原始修复记录显示，调整新测试文件中的两个错误断言。" +
                "没有修改生产代码。",

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
                "学生提交答案后，Attempt 已写入 SQLite，" +
                "但 CLI 仍报告答案未被接受。" +
                "首次测试为 2 failed, 57 passed。",

            error:
                "State-estimation time precedes submission.\n" +
                "The submission may already be committed.",

            investigation:
                "CLI 取得的 as_of 早于 Repository 后续生成的 " +
                "submitted_at。" +
                "错误发生在 Attempt 已经提交后的状态估计阶段。",

            resolution:
                "针对该特定错误使用 resume() " +
                "恢复已提交的结果，避免再次提交答案。" +
                "首次修复使用未来一秒的恢复时间，" +
                "又引出了下一轮 Decision 的时间顺序错误。" +
                "最终取消未来一秒，并让下一轮 Decision " +
                "使用恢复后 Student State 的快照时间。",

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
                "第一次提交后恢复修复成功，" +
                "但创建下一轮 Decision 时发生新的验证错误。",

            error:
                "Decision cannot precede its Student State snapshot.",

            investigation:
                "恢复 State 时使用 now_utc() + 1 秒；" +
                "创建 Decision 时使用普通 now_utc()。" +
                "因此 Decision 时间早于 Student State 快照时间。",

            resolution:
                "恢复时使用新的当前时间，" +
                "下一轮 Decision 使用恢复后 State 的 as_of。" +
                "不修改 Decision Engine 的时间顺序约束。",

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
                "原始聊天中的初始化和首次提交日志。" +
                "尚待与本地 Git History 交叉核对。",
        },

        {
            id: "SRC-002",
            kind: "Design and commit logs",
            title: "Early Student State evolution",
            locator:
                "Commits 0dda011, f61cd4b, 2de3b83",
            note:
                "早期 Student State 设计与 Evidence Schema 日志。",
        },

        {
            id: "SRC-003",
            kind: "Original pytest and git log",
            title: "13C-2B integration-test repair",
            locator:
                "Commit e52095f; " +
                "test_personalized_numeric_session_sqlite_v01.py",
            note:
                "包含原始失败、错误断言、" +
                "修复后测试和最终提交记录。",
        },

        {
            id: "SRC-004",
            kind: "Original user-supplied test logs",
            title: "13E-3C timestamp failures",
            locator:
                "Commit b8abf71; " +
                "run_local_numeric_lesson_v01.py",
            note:
                "包含两次失败、修复过程、" +
                "最终 CLI 测试及完整回归。",
        },

        {
            id: "SRC-005",
            kind: "Original user-supplied test log",
            title: "13E-4A provenance snapshot",
            locator:
                "Commit ccb4a5a; " +
                "numeric_attempt_provenance_snapshot_v01.py",
            note:
                "记录 SQLite Snapshot 集成测试和提交结果。",
        },

        {
            id: "SRC-006",
            kind: "Original user-supplied test log",
            title: "13E-4B review candidate",
            locator:
                "Commit a82b2ad; " +
                "numeric_provenance_review_candidate_v01.py",
            note:
                "记录来源检查、完整回归和提交结果。",
        },

    ],

    gaps: [

        "需要取得 Implementation 0–13 的原始 Roadmap，" +
        "确认准确的阶段名称、边界和顺序。",

        "需要取得完整 Git Commit History，" +
        "核对每次实现与设计文件的对应关系。",

        "Git History 不一定包含提交前失败的测试日志。" +
        "这些内容需要从原始聊天、Terminal 输出或保存的日志恢复。",

        "需要区分当时记录的设计理由与现在根据代码做出的事后分析。",

        "需要核对同一功能是否曾经经历多次实现、" +
        "废弃、重构或回滚。",

        "需要确定 Implementation 13 各子阶段的完整边界，" +
        "不能把所有后期功能都归入 13E。",

        "Architecture V2 和 NeoHorse-1 相关研究属于后续规划，" +
        "不能写成 Implementation 0–13 已经完成的功能。",
    ],

};
