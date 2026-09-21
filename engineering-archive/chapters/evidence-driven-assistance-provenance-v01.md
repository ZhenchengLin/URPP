# URPP Engineering Archive · Reply 9 / 10

## Implementation 13E：Evidence-Driven Teaching、Assistance Logging、Local CLI 与 Numeric Provenance

> **历史截面**：从 `a6e1181`（13E-1）到 `a82b2ad`（13E-4B）。本章讲的是这个截面已经提交的行为，不是 13E-4C 或 V2 的已完成实现。**证据类别**：`SOURCE` = 历史源码／Diff，`TEST` = 仓库中的测试定义，`DOC` = 当时的设计文档，`USER LOG` = 此前对话中用户提供的终端反馈（本 ZIP 未收录原始 Traceback），`PROPOSAL` = 尚未实施的方案。参考标记如 `[S01:L64–157]` 可在随包的 `reply9_source_index.json` 中查到精确 ZIP member、Git Commit、SHA-256 和行号。

### 本章的四个结论

1. **13E-2B 已跑通“真实作答改变下一轮动作”，没有跑通“真实合格作答提高 Mastery”。** 提交答案 `5` 后，Attempt 的 `assistance_level=None`，该证据因 `assistance_level_unknown` 被排除，Student State 保持 `UNKNOWN`；自动决策可以根据排除原因从 `DIAGNOSTIC_ASSESSMENT` 改选 `CONCEPTUAL_REVIEW`。这是 workflow adaptation，不是学业能力的判断。[S01:L158–246] [T03:L684–895] [D21]
2. **应用报告的 Hint ≠ 学生实际看见 Hint；日志为空 ≠ 没有外部帮助。** 13E-3A 存事件；13E-3B 在应用控制的 Presenter 返回严格 `True` 后写事件。但输出与数据库写入无法组成一个原子事务。[S04:L210–326] [S05:L156–250] [D22] [D23]
3. **13E-3C 的 CLI 是一次性新建数据库的本地 Demo，不是可以再次打开同一个数据库的完整客户端。** 它可在本次执行中从“Attempt 已提交、后续状态估计报错”恢复；底层 Session 的跨连接恢复另外有测试。CLI 自身对已有文件直接拒绝，并使用固定的合成算术题及静态 Agent 内容。[S06:L145–222] [S06:L306–390] [T06:L256–315] [D24]
4. **13E-4A / 4B 只生成只读 Snapshot 和可重检 Candidate，不批准任何 Numeric Evidence。** `source_fingerprint_sha256` 是变化检测，不是签名、Reviewer Authorization、独立作答证明，也不保证简短答案的隐私。[S07:L35–80] [S08:L31–65] [S08:L73–174] [D25] [D26]

---

## 1. 读历史前先划定信任与因果边界

这轮开发连接的是四种不同的信息：**评分事实**（答题文本和 Rubric 的数值评分）、**Evidence Eligibility**（该 Attempt 是否满足纳入学习状态估计的前提）、**Student State**（根据合格证据构建的状态快照）和 **Teaching Decision**（下一轮安排的活动）。其中一个环节取得成功，并不自动赋予下一层的结论。成功解析 `5` 不证明独立作答；Agent 输出了讲解不证明已经学习；选中了 Assessment Action 不保证题目内容通过发放门禁。[D19] [D21]

13E-1 引入的 Engine **读取已有的、权威来源的 `ObjectiveStateV02`**，而不是根据自由文本、Agent 输出、排除的 evidence 重新计算 Mastery。它的自动分支是工程启发式规则，并非经过教学实验验证的最优策略。显式 Student Request 仍走已有 `PersonalizedDecisionEngineV01`；Transfer Assessment 在自动候选集中被删除，显式 Transfer 请求也不能越过下游 Delivery Gate。[S01:L43–157] [D19]

**核对方式**：打开 `reply9_source_index.json` 找到 `S01` → `archive_path`，在已经上传的 `implementation_13e_history_source_pack.zip` 中打开该 member，再跳到标出的行号。源码包有 8 个 Checkpoint、54 个源码与 Diff 条目及一个 Manifest；每个条目有 commit 和 SHA-256。当前聊天另外上传的 Reply 8 Index 可交叉查 Transfer 的上一阶段来源，但**它不能证明 13E 的运行测试已经在你的 Mac 上重新执行**。[M01] [P01] [P08]

## 2. 八个 Commit：从“只选动作”走到“保存但不擅自批准证据”

| 阶段 | Commit | 引入或修改的范围 | 解决的边界／注意事项 |
|---|---|---|---|
| 13E-1 | `a6e1181` | `evidence_driven_engine_v01.py`；`DecisionSelectionSourceV01` 增加 `EVIDENCE_DRIVEN` | 对已有 State 做确定性自动选择；尚未连接教学执行。[S01] [P01] |
| 13E-2A | `beab3df` | `evidence_driven_turn_wiring_v01.py`；Orchestrator 接收共享 Decision Port | opt-in 接线、一次决策后分派 Agent；额外的前置 Transfer Guard 只覆盖该 Factory。[S02] [P02] |
| 13E-2B | `836bb71` | UNKNOWN + 唯一排除原因分支；SQLite 集成测试 | 真实提交的无效证据可以调整 workflow，但不增加 included evidence 或 Mastery。[S01] [T03] [P03] |
| 13E-3A | `add51d0` | `assessment_assistance_log_v01.py` | 按 Assignment 保存应用报告的 Hint/Solution，不声明用户看到内容。[S04] [P04] |
| 13E-3B | `6dc1bd4` | `assessment_assistance_presentation_v01.py` | Presenter 成功后写 Log，显示成功／记录失败要显式返回部分操作异常。[S05] [P05] |
| 13E-3C | `b8abf71` | Local CLI、子进程测试、Demo 文档 | 提供真实 Terminal 输出 + 新建 SQLite Demo；不是 Web/LLM/重启旧库的产品实现。[S06] [T06] [P06] |
| 13E-4A | `ccb4a5a` | `numeric_attempt_provenance_snapshot_v01.py` | 从已完成 Assignment/Attempt 和 Log 拼只读审查输入，保留 unknown。[S07] [P07] |
| 13E-4B | `a82b2ad` | `numeric_provenance_review_candidate_v01.py` | 绑定来源指纹并重检，仍待授权审核且绝不纳入 Mastery。[S08] [T08] [P08] |

`13E-4C` 是下一步研究方向：本 ZIP 中没有对应 Commit。把它写进“待决策”，不要在产品介绍、测试覆盖或工作报告中写成现成的 Authorized Review 系统。[D26]

## 3. 13E-1：Evidence-Driven Decision Engine

### 3.1 为什么新建 Engine 而不是直接改旧 Controller？

此前 `PersonalizedDecisionEngineV01` 能处理显式 Student Request，但没有一个单独的、可选择启用的“无请求时读取已有 Evidence Summary 的自动策略”。新 `EvidenceDrivenDecisionEngineV01` 采用 opt-in 实例化，`decide()` 的输入仍是 `PersonalizedDecisionContextV01`。当 `student_request is not None`，立即委托旧 Request Engine；否则读取 Context 内的 `objective_state`，再通过 `PedagogicalPolicyV01.allowed_actions(...)` 取得允许集合，剔除 `TRANSFER_ASSESSMENT`。自动选择的动作若不在剩余允许集合里，直接报错；决策前后以 `model_dump(mode="json")` 对照 State 未被修改。[S01:L43–157] [P01]

该节点还添加 `DecisionSelectionSourceV01.EVIDENCE_DRIVEN` 和独立版本号、解释性 `selection_reason`。这是**“动作为什么被选中”的 Provenance**，不是“这次教学内容已实际发给学生”的记录。旧引擎的默认实例没有被整体替换。[S01:L15–157] [D19]

### 3.2 自动规则的逐项解释

| State 及已纳入证据状况 | 默认动作 | 源码中这条规则的含义 |
|---|---|---|
| `UNKNOWN`，没有 included distinct assessment | `DIAGNOSTIC_ASSESSMENT` | 没有可用证据，先安排诊断；不是判定学生薄弱。[S01:L203–246] |
| `UNKNOWN`，已有 included distinct assessment | `INDEPENDENT_PRACTICE` | 获取进一步直接表现；并非由 UNKNOWN 标签推断能力。[S01:L240–246] |
| `EMERGING` / `DEVELOPING`，没有 included distinct assessment | `CONCEPTUAL_REVIEW` | 讲解而不是编造具体 misconception。[S01:L248–260] |
| 同上，已纳入证据但没有 independent success | `CONCEPTUAL_HINT` | 不能把 assisted performance 记为独立掌握。[S01:L262–270] |
| 同上，有 independent success | `INDEPENDENT_PRACTICE` | 再获取证据。[S01:L272–278] |
| `COMPETENT`，无 independent success | `SELF_EXPLANATION` | 不把 State 标签本身当成独立作答证明。[S01:L280–289] |
| `COMPETENT`，有 independent success | `INDEPENDENT_PRACTICE` | 继续练习，不推断 Transfer 已验证。[S01:L290–297] |
| `STRONG`，无 independent success | `INDEPENDENT_PRACTICE` | 寻找更多直接表现。[S01:L299–307] |
| `STRONG`，有 independent success | `SELF_EXPLANATION` | 安排自我解释，不擅自开放 Transfer Delivery。[S01:L309–315] |

表格描述的是源码的当前规则，不是对哪个教学动作效果更好的经验排名；合成 State 测试验证分支，并没有证明真实学生通过题目进入这些所有状态。[T01] [D19]

### 3.3 最重要的反例：学生想做 Transfer

当学生明确 `REQUEST_TRANSFER`，Engine 允许旧 Request Engine 处理“选择动作”，但真实发放仍由 Transfer Delivery Gate 决定。**选择 ≠ 发放**。13E-2A 的新 Factory 还在调用 Assessment Agent **之前**做一次 Guard；Recoverable Numeric Session 里原本的后置独立 Gate 继续存在。不能把这两层检查混写成整个项目统一的前置拦截：Factory 的 Guard 只对通过它构造的 Orchestrator 生效。[S01:L64–97] [S02:L36–89] [D20]

## 4. 13E-2A：把选择接入教学轮次，但不绕过 Repository

`create_evidence_driven_personalized_turn_v01(professor_agent, assessment_agent)` 返回原有 `PersonalizedTeachingTurnOrchestratorV01` 的实例，其中注入新 Engine 与 `_TransferGuardedAssessmentAgentV01`。这是一种 **composition / dependency injection**：不重写整个 Session，只换入有共同接口的决策实现。Orchestrator 一次教学轮次决策一次，然后按动作将生成请求路由给 Agent；它**不负责**从数据库读取权威 Student State、认证学生或保存答题记录。[S02:L68–89] [D20]

旧的 `PersonalizedNumericSessionTurnAdapterV01` 可以连接到这个新 Orchestrator，但它只适合 assessment-oriented numeric delivery；`CONCEPTUAL_HINT` / `CONCEPTUAL_REVIEW` 等 Professor Action 应调用教学 Orchestrator，而不是被包装成 Numeric Assignment。这个边界在 13E-2B 的真实 SQLite 集成测试中也被直接遵守。[D20] [T03:L842–871]

**守护测试**：`test_explicit_transfer_is_blocked_before_assessment_agent` 验证新的 opt-in Guard 不会先让 Assessment Agent 生成内容；`test_adapter_does_not_misrepresent_professor_action_as_assessment` 验证不能把讲解伪装成发题。这些是已提交测试定义，不是已证实发生过的生产事故。[T02]

## 5. 13E-2B：真实作答改变下一轮 Teaching Action，但没有提升 Mastery

### 5.1 代码前后变化

13E-1 的 UNKNOWN + 无 included distinct evidence 默认安排 `DIAGNOSTIC_ASSESSMENT`。13E-2B 加入更靠前的特例：仅当 `included_count == 0`、`distinct_count == 0`、**存在 excluded evidence**，且**所有这些 excluded evidence 的原因严格等于 `assistance_level_unknown`** 时，返回 `CONCEPTUAL_REVIEW`。只要混入别的排除原因，该特例就不触发；显式 Student Request 的优先级不变。[S01:L195–246] [T01:L427–536] [P03]

### 5.2 对真实 SQLite 的执行轨迹

`test_real_excluded_assessment_changes_next_evidence_driven_action` 不是只手工构造一个 `UNKNOWN` State：它创建隔离 SQLite 文件，保存符合发放条件的 Item，启动真实 Recoverable Numeric Session，自动发出 Diagnostic，提交 `response_text="5"`，然后**新建 SQLAlchemy Engine 与 Repository 实例并重新打开该 SQLite 文件**。恢复后的 State 满足：`state=unknown`、included evidence 为空、independent success 为零、排除项恰有一项且原因是 `assistance_level_unknown`。第二轮改由 Professor Agent 执行 `CONCEPTUAL_REVIEW`，并检验没有生成新 Assignment 或假造 Mastery Evidence。[T03:L684–895] [D21]

> **正确表达**：一次真实提交的 Attempt 使下一轮的 *workflow* 发生变化。**不能表达成**“系统通过已验证独立作答把学生提升到更高 Mastery”。评分正确与 Evidence Eligible 是两个检查；本例演示的是合格证据仍为零的情境。[T03:L820–890] [D21]

此处的“恢复”确实跨越了数据库连接／Repository 实例；它与下文 **CLI 自身不能打开旧数据库** 是两个不同层级的能力。[T03:L775–812] [S06:L165–189]

## 6. 13E-3A：Assistance Event Log 的数据模型、写入门禁与限制

13E-3A 新增表 `assessment_assistance_events_v01`。一条 `RecordedAssessmentAssistanceV01` 保存 `event_id`、`assignment_id`、`student_id`、`session_id`、`kind`（仅 `hint` 或 `solution`）、`content_sha256`、带时区的 `occurred_at`，以及固定的 `source="application_reported"`。数据库字段约束 `kind` 和 `source`；Assignment ID 是指向 `numeric_assignments_v01.assignment_id` 的外键。**内容不以明文保存在 Assistance Event 表中**，但 SHA-256 指纹不等于针对低熵内容的保密机制。[S04:L46–129] [D22]

`record_application_assistance(...)` 在事务中查找 Assignment 并检查 Student/Session Scope、Pending 状态、没有完成 Attempt、事件时间不早于 Assigned At，然后插入记录；`list_assistance_for_assignment(...)` 先验证 Scope 再读取。默认接口未提供修改或删除方法，但不能把 Repository API 的这种限制等同于数据库层不可篡改或权限认证：这个内部方法可以被任意可访问它的调用者传入虚构的内容。[S04:L210–326] [S04:L328–389] [D22]

**为什么不写入 `assistance_level=0`？** 因为只知道应用曾报告 Hint/Solution，并不能观察学生在设备外是否得到帮助；空日志也不能证明独立完成。13E-3A 不修改 `StudentAttemptV02`、Numeric Submission、Evidence Eligibility 或 State Estimator，真实 Attempt 的 assistance 与 prior-solution 字段仍未知。[D22] [D21]

## 7. 13E-3B：Presentation 与 SQLite Logging 的不可原子化边界

### 7.1 精确执行次序

`AssessmentAssistancePresentationServiceV01.present_assistance(...)` 首先校验输入与 Pending Assignment，调用由应用层提供的 `presenter.present(...)` **一次**；只有返回**严格的布尔值 `True`**才去调用 Assistance Log Repository；Repository 在写入前再次检查 Assignment 是否仍 Pending。Presenter 返回 `False`／其他值或抛异常会产生 `AssistancePresentationFailedV01`，服务不会主动写事件；Presenter 返回 True 后数据库写入失败，则抛 `AssistancePresentationUnloggedV01`。[S05:L156–250]

这两次 Pending 检查不是一种把“屏幕输出 + SQL INSERT”合并成原子事务的魔法。在初次检查之后、日志插入之前，Assignment 可能已完成；或输出正常而数据库失败。此时用户**可能已看到帮助，但 Log 为空**。后续系统不能据此判定“没有帮助”，也不能自动重放输出以假装得到 exactly-once delivery。[S05:L110–154] [S05:L205–250] [D23]

### 7.2 真实实现与 Test Double 的区别

13E-3B 起初使用 Test Presenter 验证契约，而不是宣称有浏览器 UI。13E-3C 才新增 `TerminalAssistancePresenterV01`，实际将 `[HINT]` / `[SOLUTION]` 和内容写到终端；它仍只能报告程序已执行输出，不能证明学生观看、理解或注意到内容。[S06:L113–142] [D23] [D24]

**Guard Case，不是生产事故**：测试中的 `CompletingPresenter` 在 `present()` 回调里主动提交答案，然后返回 True；第二次 Pending 检查拒绝写事件，测试期待 `AssistancePresentationUnloggedV01`、Log 为空而 Assignment 已完成。这证明部分操作失败会被**显式表达**，不证明真实用户曾在生产中遭遇相同竞态。[T05:L748–817]

## 8. 13E-3C：Local Numeric Teaching CLI —— 有哪些“真实”，又有哪些“只限 Demo”？

### 8.1 可重复的本地操作顺序

Demo 在新数据库里建立一名合成学生、一门合成算术课程，以及静态题 `What is 2 + 3?`，Numeric Rubric 期望 `5.0`、绝对容差 `0.0`。它通过已有的 Assessment Repository 和 Recoverable Session 发放题目；输入 `hint` / `solution` 触发 Terminal Presenter 与 Log，输入 `5` 走真实 Numeric Submission，再读取 State、统计记录帮助并安排下一轮自动教学。**Agent 文本静态、Assessment 合成、没有外部 LLM，也没有真实学生的授权评审。**[S06:L80–94] [S06:L145–162] [S06:L306–390] [S06:L418–579] [D24]

测试 `test_real_cli_hint_answer_and_sqlite_recovery` 以子进程输入 `hint\n5\n`，确认终端输出 Hint、SQLite 中一个 completed Assignment / 一个 Hint Event / 一个 Attempt、`response_text="5"`、`assistance_level=None`、`prior_solution_exposure=None`，下一轮动作为 `conceptual_review`，included evidence 与 independent successes 均为零。无帮助路径也保留两个 None，不会因为 Log 为空伪造独立作答。[T06:L79–158] [T06:L203–254]

### 8.2 “Recoverable” 不等于“CLI 允许重开旧数据库”

`create_new_demo_database(...)` 先拒绝现有路径，并使用 `os.O_CREAT | os.O_EXCL` 新建权限模式 `0o600` 的文件；只对这份新 Demo Database 运行 `Base.metadata.create_all`。`test_cli_refuses_existing_database_without_modifying_it` 明确验证旧文件不被打开／覆盖。CLI 在本次进程中可以恢复已经持久化的提交，底层 Recoverable Session 可以跨连接恢复，**但这个 CLI 命令不能用 `--database` 再打开该文件继续下一次教学**。网站其他章节如果笼统写“CLI 重启后继续同一 Lesson”，应依据这一事实纠正。[S06:L165–222] [T06:L256–284] [D24]

### 8.3 两次时间戳问题：来源分层的 Debugging Case

**用户此前提供的 Terminal 反馈（USER LOG，完整原始 Traceback 不在本包）**描述两阶段：先在提交后发生 State Estimation 的 `as_of` 早于 Repository 提交时间；一次中间修复将恢复时间人为加一秒，随后下一轮 Decision 时间早于未来的 State Snapshot。此 ZIP 只含最终 Commit `b8abf71` 的 CLI 文件与测试，**没有中间试错版本，也不含两次失败的完整日志**；所以这里不能把具体 traceback 行号、失败次数或中间改动视作可由本包独立复核的 Git 事实。[S06:L480–556] [D24]

**已经由最终源码确认的代码路径**：`submit_numeric_answer(..., as_of=now_utc())` 可能先持久化 Attempt，然后因 `"State-estimation time precedes submission."` 抛 `ValueError`。CLI 针对这一确切错误调用 `resume(as_of=now_utc())` **而不重新提交**；下一轮 Orchestrator 使用 `requested_at=completed.state.as_of`，不再使用可能早于 State Snapshot 的独立时钟值。[S06:L480–511] [S06:L549–557] [D24]

**根因链（来自最终实现的时间关系及此前 USER LOG）**：读取 `as_of=t0` → Repository 记录提交 `t1>t0` → 写入成功而 State Estimation 拒绝旧时间 → 从已提交结果恢复 → 下一轮 Decision 不得早于其依赖的 State Snapshot。人为把 Snapshot 时间设为未来可使恢复步骤通过，却可能制造第二个 Decision 时序冲突。这里的修复位于**本地 CLI 集成**，不能据此宣称 Repository 已拥有通用的跨服务 post-commit recovery API。[S06:L487–556] [D24]

**仍需保留的风险**：最终实现依赖异常消息字符串匹配来识别特定 post-commit 错误；源码留下了未使用的 `timedelta` import。这是可检查的当前实现细节，不是另一次已发生的故障。若未来做产品化，应先通过结果类型区分“未提交／已提交但后处理失败”，不要随意把本 CLI 的消息匹配复制到 Web API。[S06:L487–507] [PROPOSAL]

## 9. 13E-4A：只读 Numeric Attempt Provenance Snapshot

为什么不能直接复用 Open-Response 的 Signed Review Approval？其批准的是另一种对象——Open-Response 的评分审核，不能自动覆盖 Numeric Attempt 的“使用何种帮助”问题；签名 Key 或填写的 Reviewer ID 也不构成应用层真实身份认证。[D25]

`NumericAttemptProvenanceSnapshotServiceV01.build_snapshot(...)` 要求 Assignment 已完成，关联的 Attempt 确实存在，且 Attempt 的 student/course/objective/session/item ID 与 Assignment 及 Item Revision 一致。读取保存的答案、已有 `assistance_level` 和 `prior_solution_exposure` 后，再向 Assistance Log Repository 查询该 Assignment 的应用报告事件。结果为 frozen dataclass，`external_assistance_status="unknown"`、`review_status="requires_authorized_review"`、`verified_independence=False`。[S07:L35–80] [S07:L113–243]

**重要数据一致性限制**：Assignment/Attempt 在一个 Session 中读取，Assistance Events 在另一次 Repository 调用中读取；这不是跨两个读取过程的统一事务快照。输出是审查输入，不是已经授权的审核结果，更不会写回 Attempt、替换 Eligibility 或触发 Student State 更新。将 `no_application_report` 解释为“没有记录”即可，不能译成“独立作答已验证”。[S07:L204–243] [D25]

测试包括 Pending 拒绝、完成 Attempt 与 Hint 匹配、空 Log 保持未知、Student/Session Scope 不匹配拒绝、数据库重新打开后可重建 Snapshot；它们验证对象关系与限制，不构成真实 Reviewer 服务上线的证据。[T07]

## 10. 13E-4B：Candidate Fingerprint 可以查变化，不能授予权限

`create_review_candidate_v01(snapshot)` 生成 `NumericProvenanceReviewCandidateV01`，包含 Assignment/Attempt 与 Student/Session ID、Hint/Solution 报告次数、Source SHA-256 Fingerprint；不直接提供原始 Answer 字段，但 Hash 输入仍含 `response_text`。Candidate 的默认值硬性保留 `pending_authorized_review`、`external_assistance_status="unknown"`、`verified_independence=False`、`accepted_as_mastery_evidence=False`。[S08:L26–65] [S08:L73–174]

指纹按固定字段生成 JSON、对 Assistance Events 按 `event_id` 排序、`sort_keys=True` 后计算 SHA-256。`require_current_candidate(...)` 重新从持久化源构建 Snapshot 与 Candidate，完整比较两者；如果数据库源发生变化，抛 `ProvenanceSourceChangedV01`。这**只**能发现 Candidate 与当前来源记录不一致：它不是签名，不具备数据库攻击者不能同时替换记录及摘要的保证；重检以后再发生的并发写入也未被事务锁住。[S08:L73–174] [S08:L176–247] [D26]

**Guard Case**：测试在完成 Attempt 之后，使用特权 SQL 直接修改 Event 的 `content_sha256`，确认旧 Candidate 的重检失败；这是一项**模拟篡改的测试**，不能写成项目真的遭遇过数据库攻击。另有空 Log 不证明独立、Candidate 字段被手动修改应拒绝、重开 SQLite 后重检不变等测试。[T08:L178–337]

对于短答案 `5`，SHA-256 不是匿名化：当猜测空间很小，攻击者可以尝试候选答案的摘要；而 Source Fingerprint 还包括其他字段。实际产品如果处理学生隐私，不能因为 Candidate 不展示 `response_text`，就声称其 Fingerprint 是安全的匿名 ID。[S08:L73–144] [D26]

## 11. Debugging Casebook：真实反馈与 Guard Case 不混用

| 记录 | 证据等级 | 触发方式与后果 | 当前已确认的处理／限制 |
|---|---|---|---|
| C-09-01：提交后估计时间过早 | USER LOG + SOURCE | CLI 在调用 submit 取了 `as_of`；实际 Repository 提交晚于该时间；答案可能已经持久化而后续 State Estimation 报错。 | 针对特定异常用 `resume(now_utc())` 读取已提交结果，禁止重复提交；本 ZIP 无原始 Traceback。[S06:L480–511] [D24] |
| C-09-02：中间修复使用未来时间 | USER LOG + SOURCE | 先前终端反馈提到给恢复时间 `+1s` 后，下一次 Decision 早于 Snapshot；本 ZIP 未保留中间版补丁。 | 最终实现 `requested_at=completed.state.as_of`，满足不早于依赖的 Snapshot；不能由此倒推出实际发生次数。[S06:L549–557] [D24] |
| G-09-01：展示成功但 Log 写入失败 | TEST / GUARD | Test Presenter 在回调期间完成 Assignment；随后 Event 插入被拒绝。 | 抛 `AssistancePresentationUnloggedV01`，不自动重播、不声称空 Log 表示无帮助。[T05:L748–817] [S05:L233–250] |
| G-09-02：Scope 错、Assignment 已完成、输入无效 | TEST / GUARD | 错学生或 Session、无效 Kind、完成后要求展示或记帮助。 | Presenter 前与 Repository 写入前分别检查；具体覆盖详见测试。[T05] [S04:L210–326] [S05:L110–209] |
| G-09-03：无日志推断独立 | TEST / GUARD | 在没有报告帮助的 Demo 答 `5`。 | 两个 Attempt 相关字段仍为 `None`；Included Evidence 与 independent successes 为 0。[T06:L203–254] |
| G-09-04：旧 Database 被 CLI 覆盖 | TEST / GUARD | 使用已有路径启动本地 Demo。 | 拒绝启动、保留原文件内容；这也说明 CLI 不能用来恢复旧库的交互。[T06:L256–284] |
| G-09-05：Candidate 与源记录不一致 | TEST / GUARD | 测试通过特权 SQL 人为改变 Event 指纹。 | 重检时抛 `ProvenanceSourceChangedV01`，只表明变化可检测，不证明来源不可篡改。[T08:L235–292] |

**注意**：源码、测试定义和设计文档可以支持“代码设计成怎样”；本包没有每次提交的 `pytest` 原始输出，也没有 CLI 两次失败的完整原始日志，因此本章不报告未经核实的每阶段 passed 数、不制造错误截图或额外的生产事故。`test_...` 名称代表测试用例存在，不等于我在当前环境成功运行了 Mac 后端测试。[M01]

## 12. Architecture Decisions：哪些保持，哪些留待后续讨论？

**ADR-09-01｜把 Learning Evidence 与 Workflow Signal 分开。** `excluded_evidence_ids` 与 `exclusion_reasons` 可用于决定“不重复刚才的诊断”，但绝不能因已评分成功而改写 `included_evidence_ids` 或 Mastery 标签。13E-2B 的 `CONCEPTUAL_REVIEW` 是基于事件状态的临时工作流选择，不是把 UNKNOWN 解释为学习能力差。[S01:L195–246] [D21]

**ADR-09-02｜Presenter 承诺的边界要明确。** 测试 Callback 的 True 是应用声明；Terminal `print/flush` 只能证明输出尝试被程序执行，不证明学生看见。必须显式保留“展示已发生而 Log 未写入”的不确定状态，不能以空日志转换成无帮助。未来 Browser Presenter 应先设计确认/重试与 durable uncertainty semantics，再考虑自动调整 `assistance_level`。[S05:L32–75] [D23] [PROPOSAL]

**ADR-09-03｜首次真实集成采用隔离 Demo，而不是偷偷复用学生数据。** CLI `O_EXCL` 和已有库拒绝机制减轻误操作风险；其代价是不能作为生产 Session Resume UI。若未来要支持继续学习，需要**单独设计**已有库开启策略、身份/Session 访问、Schema Readiness 与生命周期管理，不能直接删除 `exists()` 检查作为临时修复。[S06:L165–222] [D24] [PROPOSAL]

**ADR-09-04｜Snapshot 与 Candidate 不等于 Approval。** 读取保存的事实、比对 SHA-256、记录 Review Status，均不能证明真实学生独立作答。未来必须另设 Reviewer Authorization、明确可观察帮助范围、处理不可见外部帮助、原子或版本化来源快照与审核决定的审计信息。不能直接照搬 Transfer Review 的当前接口，就宣称 Numeric Provenance 自动完成。[S07] [S08] [D25] [D26] [PROPOSAL]

**ADR-09-05｜改进 Post-Commit API，而不复制 CLI 的异常字符串判断。** 现在的本地 CLI 针对特定异常可恢复已提交结果；后续如果扩展到实际客户端，应使用结构化提交结果与显式幂等提交标识，并测试“提交已成功但后续处理失败”。这是提出的工程方向，不是 13E-4B 已实现功能。[S06:L480–511] [PROPOSAL]

**ADR-09-06｜保留一条简洁的 Personal Professor 产品主线。** 本章所有验证来自合成算术例子；没有真实用户行为、真实 LLM、浏览器教学 UI、独立帮助监测或可量化学习收益证据。实施 14 / V2 的课程、Observation、长期学习状态应该以明确的用户体验和最小可信数据合同来取舍，而非因能添加更多 Fingerprint 就把它们当作必须完成的学生学习能力。[D24] [D25] [D26] [PROPOSAL]

## 13. 本章覆盖范围、未完成事项与 Reply 10 的交接

截至 `a82b2ad`，可以准确说：已有 opt-in Evidence-Driven Engine；SQLite 集成测试验证无效证据造成下一轮动作调整；Assignment-scoped 应用帮助记录；Terminal 本地合成教学 Demo；只读 Provenance Snapshot；Source-bound Review Candidate。**不能**说：有已部署 Web Frontend、真实 LLM、可复用旧数据库的 CLI、可信外部帮助排除机制、已认证 Numeric Reviewer、自动把 Candidate 转成 Eligible Evidence，或 13E-4C 的已提交代码。[M01] [D19] [D21] [D24] [D26]

Reply 10 应做的不是再复制这些文件，而是将 0–13 的章节连接到统一导航／搜索和证据目录；为每条历史故障链接到其直接证据；把 Reviewer、Mastery、Transfer 和 Assistance 的未完成边界做成“Implemented / Tested / Proposal”状态卡。若需要补充两次 CLI 失败的原始 Traceback，必须从此前真实终端记录另行导入，而不能从当前源码反推。[M01]

---

### 源码检索说明

- 本章自带 `evidence/reply9_source_index.json`：`aliases` 将 `S01`–`S08`（最终源码）、`T01`–`T08`（关键测试）、`D19`–`D26`（设计文档）、`P01`–`P08`（各次 Git Diff）、`M01`（Manifest）映射到来源 ZIP 的具体 member；附 SHA-256、源码行数与 Commit。`T03` 特别指向 13E-2B 的历史 SQLite 集成测试，`T05` 指向 13E-3B 之后的 Presentation Test，`T06` 是 CLI Test。
- **代码事实以本 ZIP 的历史内容为准；** 本章节不是对你 Mac 当前工作树、外部服务或真实学生数据库的实时审计。本轮只制作网站文档及其来源索引，不改 Backend、SQLite 或 Git 历史。
