# URPP Engineering Archive — Reply 6 / 10

## Persistence · Numeric Assignment · Session Recovery · SQLite Migration

> **文档版本**：Archive Chapter V0.1。**历史源范围**：用户提交的 `persistence_recovery_history_source_pack.zip`，内含 19 个已解析的历史 Git Checkpoint、71 个历史源码/测试条目及 `SOURCE_MANIFEST.json`。**本章的确认状态**：以各指定 Commit 的代码、文档与测试为准；未在这份 ZIP 中观察到的历史 pytest 失败不虚构为事故。**时间戳实际故障**取自此前用户提供的 13E-3C CLI 运行与修复记录，在本资料包中仅有其最终代码和成功路径测试，因此独立标注来源与证据缺口。

**本章目录**：① 问题与职责边界 → ② 19 个 Git 历史节点 → ③ 数据契约和约束 → ④ 发题流程 → ⑤ 原子提交 → ⑥ 三种恢复路径 → ⑦ 重建 Student State → ⑧ 规则为何从 Python 下沉 SQLite → ⑨ 两代 Migration → ⑩ Readiness 与 Engine → ⑪ 启动和依赖注入 → ⑫ CLI 的两次真实时间戳故障 → ⑬ Guard Casebook → ⑭ 后续维护中的未覆盖边界 → ⑮ 源码与测试定位。

---

## 01. 从“保存答案”到“恢复一次尚未结束的教学”

最初的教学流程可以在内存中保留一个 `pending_assignment`，但用户关闭程序之后，内存并不能回答：上一次题目是否已经发放？学生应该回答哪道题的哪个 Revision？某次提交是否已经成功保存？重启后该先恢复 Pending Assignment，还是新建另一道题？

这里存在三个不能合并的实体：

| 实体 | 创建时间 | 生命周期与职责 | 不能替代什么 |
|---|---|---|---|
| `AssessmentItemV02` + Revision | 题目存储阶段 | 定义题目文本、Objective 和 Rubric 的特定历史版本 | 它不是“已经向学生发题”的证据 |
| `NumericAssignmentRow` | 选定 Assessment Action 且发题入库时 | 固定 Session、Decision、Item Revision、发题时间、Pending/Completed 状态 | 它不是学生答案，也不能仅凭 Pending 证明屏幕实际被学生看到 |
| `StudentAttemptRow` | 学生提交回答时 | 记录服务器端生成的 Attempt ID、关联 Item Revision、响应文本和提交时间 | 它不能独自说明此前是否已发放合法 Assignment |

第三种持久化实体是 `NumericTeachingSessionRowV01`：保存 `session_id + student_id + course_id + objective_id + started_at`。它记录“这个会话是谁的、何时开始”，而**不复制维护一份需要随每道题更新的会话进度表**。进度由 Assignment 与 Attempt 重建。这是 `numeric_session_records_v01.py` 的类文档和 `list_assignment_ids()` 的实际实现，而非我们事后补充的新需求。

完整关系：

```text
Stored Item (item_id, revision, prompt, rubric)
              │
              │ immutable revision reference
              ▼
Registered Teaching Session ───► Assignment (pending)
  student/course/objective           │
  started_at                         │ student submits text
                                     ▼
                               Attempt INSERT
                                     │ same DB transaction
                                     ▼
                              Assignment UPDATE
                              pending → completed
                                     │
                                     ▼
              Recover session from stored assignments
                                     │
                       stored Item + stored Attempt
                                     ▼
                     Numeric Scoring → Eligibility
                                     ▼
                          Student State Estimator
                                     ▼
                           Next Teaching Decision
```

**注意“原子性”的精确边界**：Assignment 与 Attempt 在 `submit_numeric_response()` 中共享一个事务；Session Registration 与后续 Assignment Issuance 是两个操作，不构成贯穿整个教学会话的单一事务；评分、教学动作选择、终端显示、Assistance Log 也不包含在同一事务内。把一次课程笼统写成“端到端原子”是不准确的。

**源锚点**：`b36c7b5` 的 `numeric_assignment_v01.py`；`cf9ab746` 的 `numeric_session_records_v01.py` 和 `recoverable_numeric_session_v01.py`；`f86f68d7` 的 Assignment / Recoverable Session 最终历史快照。

---

## 02. 按真实 Git Checkpoint 重建设计演进

以下按资料包 Manifest 顺序列出 19 个节点。名称采用资料包中的阶段标签及对应变更，不把这些标签擅自等同于完整的 Implementation 0–13 原始 Roadmap。源码包包含的，是每个节点**当时新增或修改的相关文件**，并不是整个仓库的完整源码快照；`final_snapshot_f86f68d7b4/` 另补充了主要服务在该时点的整份代码。

| 顺序 | Commit | 历史节点 | 确认的结构变化 / 核查位置 |
|---:|---|---|---|
| 01 | `b36c7b5fba` | `assignment_persistence` | 引入 `NumericAssignmentRow`、`issue_assignment()`、`submit_numeric_response()` 与对应 Repository 测试；首次建立 Pending→Completed 的数据库路径。 |
| 02 | `174f259e7a` | `completed_assignment_state` | 新增 `CompletedAssignmentStateServiceV01`；不允许仅凭用户输入 Attempt ID 跳过 Assignment 与 Attempt 的关联校验。 |
| 03 | `692b6943f4` | `persisted_numeric_loop` | 新增 `PersistedNumericTeachingLoopV01`，把内存教学会话与数据库 Assignment 连接；存在 `_requires_recovery` 防止后提交异常后继续操作陈旧内存。 |
| 04 | `cf9ab746db` | `session_recovery` | 增加持久化 Session Identity 及 `RecoverableNumericSessionServiceV01`，可在新 Service 实例中读出 Pending/Completed 和 State。 |
| 05 | `a562e6711b` | `assignment_invariants` | 引入 `pending_session_key` 唯一约束、`(session_id,decision_id)` 唯一约束及状态一致性检查；测试并发发题/提交与失败回滚。 |
| 06 | `79e250c760` | `assignment_migration` | 为旧 Assignment 表提供明确审核、显式应用、备份、事务性变更与状态一致性 Trigger 的迁移工具。 |
| 07 | `1f50e80483` | `database_readiness` | 新增只读 Readiness Check，验证表、Schema、Foreign Key 与 Session/Assignment 数据关系。 |
| 08 | `85bbb0e392` | `session_registration` | 发题路径增加注册会话匹配检查的可选阶段。 |
| 09 | `0f32231201` | `strict_session_assignment` | 添加 `registered_session_id` 及四列 Composite FK（包含 Session 和 Student/Course/Objective），并保留有明确历史语义的 NULL。 |
| 10 | `e735c0fbdf` | `registered_session_default` | 新发题默认要求已注册且 Scope 相符的 Session；测试明确覆盖缺失 Session 的拒绝路径。 |
| 11 | `cd5c7d4cde` | `foreign_key_readiness` | 引入迁移前的只读 FK 审核：区分 pre-09 / post-09-pre-12B / post-12B 以及无法匹配的历史数据。 |
| 12 | `3cbeffabe4` | `foreign_key_migration` | 对旧 Assignment 表进行有备份和校验的整表重建，迁移到带 Registered Session Composite FK 的 Schema。 |
| 13 | `0bc3250fb7` | `guarded_sqlite_engine` | 用 `mode=rw` 打开已有 SQLite DB；为 SQLAlchemy 新连接启用、连接池 checkout 时复核 FK。 |
| 14 | `fc91a60a7d` | `sqlite_startup` | FastAPI lifespan 对数据库连接做显式 opt-in，不破坏原本 health-only 启动。 |
| 15 | `f22dbf930d` | `repository_injection` | 新增 `NumericRepositoryBundleV01`，三个 Repository 绑定同一个受保护 Engine/Session factory。 |
| 16 | `c24d1dc84d` | `recoverable_session_factory` | Session Factory 从 Startup Bundle 注入依赖，不私自创建另一套 Engine 或 Repository。 |
| 17 | `f05f7e1328` | `legacy_session_registration` | 早期 Legacy Loop 补上持久化 Session Registration，仍明确注明内存进度的限制。 |
| 18 | `f86f68d7b4` | `remove_unregistered_issuance` | 正常发题实现移除无注册 Session 的发行路径；新 Assignment 设置 `registered_session_id=session_id`。 |
| 19 | `b8abf71993` | `local_numeric_cli` | Synthetic Arithmetic CLI：创建专用新 DB，真实持久化与重新估计，静态教学内容，展示 Assistance Presentation 和恢复链路。 |

**重要的先后关系**：01 的数据库发题与提交**先于**04 的跨 Service 恢复能力；05 的数据库级约束**先于**06 的旧库升级工具；07 的只读检查**先于**09/10/12 更严格的 FK Schema；13 的受保护 Engine**先于**14/15/16 的应用级实际注入。不能把最终快照中的所有保护自动写回最初的 `b36c7b5`。

---

## 03. 持久化模型：每个字段为什么存在？

### 3.1 Assignment 的身份和历史版本

`NumericAssignmentRow` 保存：`assignment_id` 主键、`decision_id`、`student_id`、`course_id`、`objective_id`、`session_id`、`assessment_item_id`、`item_revision`、`assigned_at_utc`、`status`、`pending_session_key`、`registered_session_id` 和 `completed_attempt_id`。

`assessment_item_id` 与 `item_revision` 共同构成指向历史题目的 Composite Foreign Key。**重新评分应使用发题时绑定的 Revision**，而不是 Item 的最新版本；否则 Rubric 或题面改变后，早期学生作答的含义也会被偷偷改写。`decision_id` 允许从某条已记录的教学决定追踪其实际发题，但仅有 Decision ID 并不能证明客户端真的显示了题目。

`assigned_at_utc` 是数据库保存的发题时间；`completed_attempt_id` 在 Pending 时必须为空，在 Completed 时必须指向已有 Attempt。`status` 和其余字段之间不能只靠 Python `if` 维护一致性，因为其他操作可能绕开同一个 Python Service。

### 3.2 Session 身份为什么单独存？

Session 表存 `session_id`、Student/Course/Objective Scope 与 `started_at_utc`。同一 Session ID 重复 `register()`，如果 Scope 一样，返回已有记录，不清除进度；若 Scope 不一致，拒绝。`list_assignment_ids()` 根据该 Scope 查出 Assignment，先按 `assigned_at_utc`、再按 `assignment_id` 排序，使新进程可得到确定性的输入顺序。

此处的注册 API 只校验**由调用者提供的** Student/Course/Objective；没有真实用户身份认证。记录属于某个 Student ID 是数据库内的关联事实，并非证明提交者本人是谁。

### 3.3 Pending Slot 的 SQLite 设计

核心字段：

```python
# Excerpt: final_snapshot_f86f68d7b4 / numeric_assignment_v01.py
pending_session_key: Mapped[str | None] = mapped_column(
    String(128), unique=True, nullable=True
)
```

Pending 记录填 `session_id`，Completed 记录置 `NULL`。在这里的 SQLite UNIQUE 语义下，多条记录可有 `NULL`，但**同一个非空 Session ID 最多出现一次**。因此，可以保留历史 Completed Assignment，同时保证每个 Session 至多一条 Pending Assignment。

| Assignment 状态 | `completed_attempt_id` | `pending_session_key` | 语义 |
|---|---|---|---|
| Pending | NULL | 等于 `session_id` | 占用这个会话的待答题槽位 |
| Completed | 指向唯一 Attempt | NULL | 释放槽位，允许后续新题 |
| Pending + 已有 Attempt | 非 NULL | 任意 | 状态矛盾，应拒绝 |
| Completed + 仍占 Pending 槽 | 非 NULL | 非 NULL | 槽位不释放，应拒绝 |

最新 ORM 使用 `CheckConstraint` 保证 Pending/Completed 与 Key 的一致性，`UniqueConstraint(session_id, decision_id)` 限定每个会话不可重复消费相同 Decision ID。**先前创建的旧数据库不能仅修改 SQLAlchemy Model 就自动获得这些约束**；这是历史迁移工具存在的原因。

### 3.4 Registered Session：四列约束而非只有 Session ID

最终 ORM 声明的 Registered Session Composite FK 同时核对：

```text
Assignment.registered_session_id → Session.session_id
Assignment.student_id           → Session.student_id
Assignment.course_id            → Session.course_id
Assignment.objective_id         → Session.objective_id
```

并通过 CHECK 要求非空时 `registered_session_id=session_id`。父 Session 表必须声明相应四列的 UNIQUE 键作为 FK 目标。仅有 `Assignment.session_id` 指向已存在的 Session 还不够：可能引用到其他学生、其他课程或 Objective 的 Session。四列绑定可以在数据库层阻止这类交叉关联。

**历史 NULL 并没有被模型直接禁止**：`registered_session_id` 定义为 Nullable，以表示旧版本可能存在未绑定数据。最终新发题路径会填充它，而 Startup Readiness 会拒绝带有未绑定 Assignment 的已有数据库。因此“ORM 允许历史 NULL”和“当前应用允许有 NULL 的数据库上线”是两个不同的判断，不能混淆。

**源锚点**：`a562e67`、`0f32231`、`e735c0f`、`f86f68d` 的 `numeric_assignment_v01.py`；`numeric_session_records_v01.py`。

---

## 04. 发题（Issue Assignment）：真正写入了什么？

最终 `NumericAssignmentRepositoryV01.issue_assignment(delivery, *, student_id, course_id, objective_id, session_id)` 的执行顺序如下：

1. 确认 `delivery` 类型为 `AssessmentDeliveryV01`，调用方提供的标识非空；`selected_action` 必须属于 Assessment Actions；发题时间必须是 timezone-aware。
2. 使用与 Assessment Repository 共享的 SQLAlchemy `sessionmaker`，进入 `with session.begin()`；读取 `NumericTeachingSessionRowV01`，要求 Session 已注册，且 Student/Course/Objective 完全一致。
3. 从 Session `started_at_utc` 解析时间，要求 `delivery.assigned_at >= session.started_at`。
4. 使用 `(assessment_item_id, item_revision)` 加载**原历史版本**；只接受 Numeric Item，且 Item 自身 Scope 与 Assignment Scope 一致；确认 `alignment_verified`，并要求 Delivery Prompt 与 Stored Item Prompt 完全相同。
5. 拒绝已经存在的 `assignment_id`；插入新的 Pending Assignment，设置 `pending_session_key=session_id` 和 `registered_session_id=session_id`；`session.flush()` 促使数据库约束在提交前执行。
6. 在事务成功提交后，将 `StoredNumericAssignmentV01` 返回给上游 Service。

```text
Decision selects assessment
    → Structured Delivery (item ID + immutable revision + prompt)
    → verify Registered Session & scope & time
    → load historical Item and check stored prompt
    → INSERT pending Assignment
    → flush/check DB uniqueness + FK + CHECK
    → commit
    → return stored assignment
```

**发题与“显示在屏幕上”不是一个事实**：Repository 确认的是记录已落库，并核验 Delivery 与 Stored Item 的一致性。它没有直接观察学生是否看见、理解或记住题目。`PendingNumericDeliveryViewV01` 的注释也明确声明，重建展示并不证明浏览器曾经显示过它。

**源锚点**：最终历史快照 `numeric_assignment_v01.py::issue_assignment`；`recoverable_numeric_session_v01.py::deliver_numeric_assessment`。

---

## 05. 提交（Submit）：为什么必须在同一事务内？

`submit_numeric_response(assignment_id, student_id, session_id, response_text)` 接收的业务输入是 Assignment ID、内部 Scope 与回答文本。Course/Objective/Item Revision、Attempt ID、Source Message ID、Response Group 和提交时间都由已存记录或服务器端生成。它**不会接受调用方直接覆盖这些历史关联**。

首先加载 Pending Assignment，核对 Student/Session Scope，拒绝已经 Completed 的 Assignment；通过 Repository Clock 创建 aware `submitted_at` 并校验不早于 Assignment Time。然后生成 `StudentAttemptV02`，明确填入：

```python
assistance_level=None
prior_solution_exposure=None
novelty="unknown"
```

这不是“学生没有帮助”；它是“提交 Repository 不能验证作答条件”。即便 Numeric Scoring 计算出 `correctness=1.0`，也不会因为答案正确而自动改变这三个字段。

后续关键事务：

```python
# Conceptually faithful excerpt of final repository flow
with self._session_factory() as session:
    with session.begin():
        # ① load + validate pending assignment
        # ② session.add(StudentAttemptRow(...))
        session.flush()                 # INSERT Attempt, not COMMIT
        result = session.execute(
            update(NumericAssignmentRow)
            .where(
                NumericAssignmentRow.assignment_id == assignment_id,
                NumericAssignmentRow.status == "pending",
                NumericAssignmentRow.completed_attempt_id.is_(None),
            )
            .values(
                status="completed",
                pending_session_key=None,
                completed_attempt_id=attempt.attempt_id,
            )
        )
        if result.rowcount != 1:
            raise ValueError("Assignment was completed by another submission.")
# only here: transaction may commit both writes
```

**`flush()` 和 `commit()` 不同**。`flush()` 将待执行的 INSERT 发送给 DB，并允许本事务随后用新的 Attempt ID 作为 FK 目标；在事务结束前，仍可整体 Rollback。条件 UPDATE 是对“仍 Pending”的 Assignment 争取完成权：只有 `rowcount == 1`，本次 Attempt 才会与完成记录一同成功提交。

### 为什么只在 Python 中查询 `status == pending` 不够？

两个并发调用可以先后读到同一个 Pending 状态；单靠先读后写，可能各自认为自己可以提交。数据库条件 UPDATE、唯一约束和事务收敛到可验证的最终状态。在本历史测试中的 SQLite 环境，冲突可能表现为已完成错误、`IntegrityError` 或 `database is locked`，测试允许这些失败形式，**但只允许一份 Attempt 成功落库**。这不是对 PostgreSQL、多进程部署或任意高并发工作负载的全面保证。

### 后提交异常与原子事务的边界

Scenario A：Attempt INSERT 成功 flush，但 Assignment UPDATE 失败。**同一事务被撤回**，不应出现孤立 Attempt。`test_failed_assignment_update_rolls_back_attempt` 通过人为注入 SQL 执行异常覆盖这个场景。

Scenario B：Attempt INSERT 与 Assignment UPDATE 均提交成功，之后 State Estimation 失败。**数据库不能自动撤销已提交的业务事实**；正确做法是恢复并重新读取，而不是再次提交同一答案。`test_recovery_after_database_commit_and_state_failure` 人为让完成后的 State Service 抛异常，然后创建新 Service 并恢复成功。这是受控故障注入测试，不应写成“用户一定在实际使用中遭遇过这次故障”。

**源锚点**：最终 `numeric_assignment_v01.py::submit_numeric_response`；`a562e67` 的 `test_numeric_assignment_invariants_v01.py`；`cf9ab746` 的 `test_recoverable_numeric_session_v01.py`。

---

## 06. 三条恢复路径，不能写成一种

### 6.1 Repository 重建：历史数据仍可读取

`test_submission_is_visible_after_repository_restart` 在新的 Repository 实例中读取此前已完成的 Assignment，验证数据库保存了结果。这一层证明：**记录不依赖旧 Python 对象而存在**，但没有证明整个教学会话已恢复正确 Decision Context。

### 6.2 Legacy Persisted Loop：写入持久化，但仍有内存状态

`PersistedNumericTeachingLoopV01` 同时维护 `_pending_assignment_id`、`_completed_assignment_ids` 和内存中的 `NumericTeachingSessionV01`。它先让 in-memory Coordinator 创建结构化题目，再调用 Repository 写库；保存成功才设置 `_pending_assignment_id`。提交时先调用 Repository 完成数据库提交，再读取 `CompletedAssignmentStateServiceV01` 和原来的内存 State Engine，比较两边完整的 `model_dump(mode="json")`。

为什么还要比较两个 State？因为在这个 Legacy Loop 中，同时存在持久化数据推导的 State 和内存协调器维护的 State。如果两者不一致，不应该让后续 Decision 随便使用其中一个。该类使用 `_requires_recovery`：如果已创建 Pending Turn 却写库失败，或数据库提交后 State 更新失败，就停止继续使用该内存会话。**这是一种 fail-closed 处理，但并不等于 Legacy Loop 本身已经具备可随时跨进程重启的完整恢复能力。**

后续 `f05f7e1` 又补上持久化 Session Registration，保证 Legacy Loop 发行的 Assignment 也关联已注册 Session；这没有把内存协调器自动改造成数据库权威的恢复服务。

### 6.3 Recoverable Numeric Session：数据库事实决定当前进度

`RecoverableNumericSessionServiceV01` 不从旧实例的 `pending_assignment_id` 推断恢复状态，而是：

```text
resume(as_of)
    → validate aware as_of
    → load registered session, check scope and start time
    → list stored assignment IDs in deterministic order
    → load every assignment + verify scope and assigned_at ≤ as_of
    → classify pending / completed (reject unknown status)
    → reject >1 pending
    → completed? verify assignment→attempt associations and estimate state
    → else: estimate state from empty evidence
    → pending? load original stored item revision and reconstruct prompt
    → return RecoveredNumericSessionV01(state, pending, completed_ids)
```

`start(started_at)` 会先 `register()` Session，再 `resume(as_of=started_at)`；同 ID、同 Scope 再次开始不会清空以前的 Assignment。`deliver_numeric_assessment()` 先恢复，拒绝仍有 Pending，核对 Session 内重复 Decision ID、历史 Item Scope 与 Alignment，并要求 Orchestrator 实际选中了 Assessment Action，之后才形成 `AssessmentDeliveryV01` 并调用 Repository 发题。`submit_numeric_answer()` 先恢复并核对当前 Pending ID，写入答案，最后再次 `resume()`。

**一个不可省略的限制**：`resume()` 会按顺序读取 Session、Assignment、Attempt 等数据；它不是一个自动生成跨所有 Repository 查询的“单个原子快照”。源代码也声明其没有应用层 Auth、HTTP Endpoint、跨进程并发完整保证，Session Registration 与发题为独立数据库事务。后续若加入高并发或分布式应用，应重新审查这些边界。

**源锚点**：`692b694` 的 `persisted_numeric_session_loop_v01.py`；`cf9ab746` 的 `recoverable_numeric_session_v01.py` 及恢复测试；`f05f7e1` 对 Legacy Loop 的修改。

---

## 07. 从 Completed Assignment 重建 Student State：不让调用方直接指定证据

`CompletedAssignmentStateServiceV01.estimate_from_completed_assignments(assignment_ids, *, student_id, session_id, course_id, objective_id, as_of)` 为每个 Assignment 做以下审查：

1. 不接受字符串冒充 Assignment ID 序列；拒绝空集合、重复 Assignment ID 或无效 Scope/时间。
2. 从 Assignment Repository 取实际记录；检查 Student/Session/Course/Objective 全部匹配，并且状态确实为 Completed、`completed_attempt_id` 不为空。
3. 从 Assessment Repository 加载**该 Assignment 真正引用的 Attempt**以及其历史 `item_revision`；不接受同一 Attempt 为多个 Assignment 充数。
4. 验证 Attempt 的 Scope、`assessment_item_id`、绑定 Revision、`response_group_id == 'assignment-' + assignment_id`、提交时间不早于发题时间。
5. 验证 `assignment.assigned_at <= as_of` 且 `attempt.submitted_at <= as_of`。如果估计时刻还没到实际事件发生时刻，不能把未来事实塞进过去的 State。
6. 用真实的 Attempt ID 调用 `PersistedNumericAssessmentServiceV02`；后者加载每份 Attempt 对应的原始 Item Revision，并委托 `AssessmentPipelineV02` 的评分、Eligibility 和状态推导。

```text
Caller supplies assignment IDs, not arbitrary Evidence Events
    ↓ verify assignment linkage & time & scope
Stored Attempt IDs
    ↓ load Attempt + its immutable Item Revision
Numeric Submission objects
    ↓ numeric scoring
Evidence Event(s)
    ↓ existing eligibility + student state rules
ObjectiveStateV02
```

**对 Claim 的边界**：这些验证证明数据库中 Assignment 与 Attempt 的结构化关系符合预期，不证明回答一定由对应现实中的学生亲自完成，也不提供对调用方 Student ID 的真正认证。Repo 中的内部 `student_id` 参数未来仍须由已验证的 Server Session Context 生成。

`test_completed_assignment_reaches_state_engine`、`test_tampered_attempt_assignment_link_is_rejected`、`test_tampered_attempt_revision_is_rejected`、`test_state_estimation_cannot_precede_submission` 分别覆盖链路和关键负面情境。

**源锚点**：`174f259` 的 `completed_assignment_state_v01.py` / tests；最终 `persisted_numeric_pipeline_v02.py`。

---

## 08. 为什么约束要逐渐下沉到 SQLite？

在单进程单线程 Demo 中，用 Python 层 `if pending: raise` 看上去足够；但多个 Repository 实例、数据库重开、并发写入和后续 Schema Migration 都会让“所有写入一定经过这段 if”变成无法保障的假设。

逐渐增设的数据层保护有：

| 保护条件 | 负责位置 | 具体阻止什么 |
|---|---|---|
| `assignment_id` Primary Key | Assignment 表 | 同 ID 重复插入 |
| `(assessment_item_id,item_revision)` FK | Assignment 表 | 指向不存在的题目版本 |
| `completed_attempt_id` FK + UNIQUE | Assignment 表 | 引用不存在 Attempt；单份 Attempt 被多个 Assignment 直接引用 |
| `pending_session_key` UNIQUE + 状态一致性 CHECK / Trigger | Assignment 表 | 同一 Session 同时存在两个 Pending，或 Completed 不释放槽位 |
| `(session_id,decision_id)` UNIQUE | Assignment 表 | 同一会话复用同一 Decision ID |
| Registered Session 四列 FK | Assignment + Session 表 | Assignment 关联到不存在或 Scope 不一致的 Session |
| `PRAGMA foreign_keys=ON` | 当前受保护 Engine 的数据库连接 | SQLite 在该连接上执行声明的 FK |
| Readiness + Migration Audit | 应用启动前 | 拒绝结构缺失、数据关联异常和未绑定历史行 |

**两个容易错的理解**：一，SQLite 数据库文件中存在 FK 定义，不代表所有连接都必然执行 FK：`PRAGMA foreign_keys` 是连接级设置，需要实际启用。二，ORM Model 新增 CHECK/FK，不会自动更改已有数据库表；必须审计/迁移并验证旧数据。

源码中 `test_concurrent_issuance_produces_at_most_one_pending` 以两名 Worker 同时尝试发题，允许失败侧出现唯一约束冲突或 SQLite 写锁冲突；成功侧必须只有一条 Pending。`test_concurrent_submission_creates_exactly_one_attempt` 要求最终只有一份 Attempt。它们是**设计防护验证**；这份源码包没有对应的原始“线上并发重复发题事故”日志。

---

## 09. 第一次历史 SQLite Migration：Pending Slot 与 Decision 唯一性

在 `a562e67` 中新增的 Schema 约束只适用于用新 Model 创建的表；旧数据库还没有 `pending_session_key`、对应 UNIQUE 以及新的 CHECK 语义。`79e250c::migrate_numeric_assignment_v01_sqlite.py` 提供受控升级路径。

### 9.1 两种运行模式

**默认是只读检查**：用 `mode=ro` 打开已存在的 DB，执行 `PRAGMA quick_check` 与 FK 检查，识别是已知 Legacy Schema 还是 Current Schema，检查历史行是否满足状态与唯一性要求。**显式 `apply=True`** 才会修改数据库，且要求提供一个原先不存在的备份文件路径。

### 9.2 确认旧库后才可升级

迁移拒绝缺失数据库、符号链接路径、未知 Schema、历史重复 Pending、重复 Decision、现有 FK 违规、错误 Pending/Completed 组合或已有备份路径。必须先停掉应用及其他写入者。它会用 SQLite Backup API 创建新备份，用 `PRAGMA data_version` 在获得 EXCLUSIVE 事务时检查备份期间数据库是否变化，再重验 Schema/行数后升级。

升级动作：

```text
Inspect legacy schema + row consistency
    → create NEW verified backup
    → BEGIN EXCLUSIVE / recheck
    → ALTER TABLE: add pending_session_key
    → UPDATE pending rows: pending_session_key = session_id
    → add UNIQUE indexes for pending key and session+decision
    → add INSERT/UPDATE consistency TRIGGERS
    → inspect upgraded schema/rows within transaction
    → COMMIT
    → final verification; retain backup
```

为什么旧表使用 Trigger？该工具的说明和实现指出：现有 SQLite 表不能直接通过这里采用的 `ALTER TABLE` 路径附加替换后的原生 CHECK。它因此对**迁移旧表**安装 INSERT/UPDATE Trigger，以约束 Pending Key 一致性；**新建表**继续使用 SQLAlchemy Model 中的 CHECK。两条 Schema 的外部行为目标一致，实现形式不完全相同；审计工具需同时识别两种已知形式。

若事务内失败，执行 ROLLBACK；即使 COMMIT 之后最终校验失败，也不能假称数据已经自动撤销，应停止使用并保留备份调查。

**源锚点**：`79e250c::migrate_numeric_assignment_v01_sqlite.py` 的 `inspect()`、`_install_consistency_triggers()`、`migrate()`；`test_numeric_assignment_sqlite_migration_v01.py` 的 duplicate rows、backup、trigger 和 read-only tests。

---

## 10. 第二次 SQLite Migration：将 Session Scope 变成真实的 FK

第一次迁移增强了 Pending/Decision 约束，但只靠 `assignment.session_id` 文字列和应用侧核验，不能从数据库层阻止所有交叉关联。因此出现 `registered_session_id` 和 Registered Session Composite FK。

`cd5c7d4` 的 `audit_numeric_session_fk_migration_v01.py` 会识别 Schema 阶段，检查已保存 Assignment 是否存在对应 Session、Student/Course/Objective Scope 是否匹配、时间是否合理，以及是否有 Legacy Unbound 记录。`3cbeffa` 的 `migrate_numeric_session_fk_v01_sqlite.py` 执行明确申请后的真正升级。

### 10.1 为什么第二次不是简单 ALTER TABLE？

这次需要重建 Assignment 表，装入完整的 Composite FK、CHECK 和 UNIQUE 定义。工具从当前 SQLAlchemy Table Model 编译 SQLite CREATE TABLE DDL，替换影子表名，不维护一套独立手写的新 Schema。它拒绝未知入向 FK、未知依赖结构与已有 Shadow Table，避免重建时无意破坏并不认识的第三方对象。

### 10.2 事务化重建

```text
Read-only audit (pre-09? post-09/pre-12B? post-12B?)
    → if pre-09: require first migration, never silently chain
    → for known post-09/pre-12B: require NEW backup path
    → create SQLite backup + verify known source schema
    → BEGIN EXCLUSIVE + recheck data_version and rows
    → ensure Session 4-column UNIQUE parent key
    → CREATE shadow Assignment table from current ORM DDL
    → copy all source fields + registered_session_id=session_id
    → verify copy/constraints/count
    → DROP old Assignment table / RENAME shadow table
    → verify FK + row preservation in transaction
    → COMMIT
    → run public read-only readiness and migration audit again
```

如果某条旧 Assignment 指向不存在的 Session，或者 Scope 不符，该工具不会“猜一个 Session”或者暗中修改 Student ID：它会拒绝自动升级。`test_orphan_assignment_blocks_upgrade`、`test_scope_mismatch_blocks_upgrade`、`test_inbound_foreign_key_blocks_table_rebuild`、`test_failed_transaction_restores_source_schema` 对应这类可复现的防护测试。

重要的版本界限：第一次迁移工具只解决旧 Pending Key/Decision 约束；第二次解决 Session 绑定与 FK。**不要运行第二次脚本去修复任意未知 SQLite Schema**；它明确要求已知的 post-09/pre-12B 输入，且操作前应备份并停止所有 Writer。本网站是设计档案，不是对真实用户数据库执行 Migration 的操作许可。

---

## 11. Readiness 与连接层：Schema 正确不代表运行路径已正确

`check_sqlite_numeric_database(path)` 首先拒绝缺失数据库与符号链接，使用 SQLite `mode=ro` 只读连接检查必需的 Assessment Item、Attempt、Assignment、Teaching Session 四张表；验证 Assignment Schema 状态、SQLite `quick_check` 与 `foreign_key_check`，逐行审计 Session Scope 和时间。随着 12B FK 演进，最终快照还检查 Registered Session Composite FK 的四列定义，以及 `registered_session_id IS NULL` 历史 Unbound 记录数；发现这种记录就拒绝启动当前严格数值教学服务。

**Readiness 不是数据库初始化器，也不是全部历史 Payload 的真实性验证**。它不会创建缺失表，不会让任意旧 Schema 自动升级，也不能为调用者提供身份认证。

`create_numeric_sqlite_engine(path)` 是另一个边界：先执行 Readiness 和 FK Migration Audit，要求已知 `post-12B` Schema，然后使用 `mode=rw` 只打开已存在文件。`mode=rw` 的目的不是把数据库设置成 read-only，而是**允许读写已存在的数据库，同时禁止路径消失时静默创建新文件**。

```text
Application opts in with existing DB path
    → Readiness + FK Migration Audit
    → create Engine via SQLite URI mode=rw
    → connect event: PRAGMA foreign_keys=ON + verify
    → checkout event: verify pooled connection still has FK enabled
    → give Engine to Repository Bundle
```

这里的 Pool Checkout 校验只能保障“取出连接时”的 FK 状态；不能禁止某个已获得连接的调用者随后关掉 PRAGMA，也不能控制数据库外部其他程序自己的连接。源码对此限制有明确声明。`test_pool_rejects_connection_with_foreign_keys_disabled` 和 `test_database_is_not_recreated_if_removed_before_connect` 分别覆盖两个关键失效情境。

---

## 12. Application Startup 与 Repository Injection：真正把受保护 Engine 用起来

仅创建一个 `create_numeric_sqlite_engine()` Factory 还不够。如果生产 Service 又独自创建了未经保护的 Engine，上述连接约束就无法保证该 Service 的写入。历史在 `fc91a60`、`f22dbf9`、`c24d1dc` 逐步将连接检查接入实际应用构造路径。

### 12.1 FastAPI lifespan 保持健康检查默认可用

`main.py` 使用 `URPP_NUMERIC_SQLITE_DATABASE_PATH` 环境变量作为显式 opt-in。变量**不存在**时保留 health-only 应用的启动；变量**存在但为空**时拒绝；存在非空路径时执行受保护 Engine 构建，并将 Engine/Repository Bundle 挂到 `app.state`。退出 lifespan 时 `engine.dispose()` 并清理 `app.state` 的引用。

这不是“已经上线生产学生 API”：代码没有数据库支持的学生端 HTTP Routes，也没有真实用户 Auth。默认 health-only 启动也不代表数据库服务已经激活。

### 12.2 为什么三个 Repository 共用一个 `sessionmaker`？

`create_numeric_repository_bundle(engine)` 先验证接入的是 SQLite Engine 且当前连接的 Foreign Keys 已启用，再创建单一 `sessionmaker(bind=engine, expire_on_commit=False)`，从它构造 Assessment、Assignment 和 Teaching Session Repository。Assignment Repository 直接重用 Assessment Repository 的 Session Factory，而不是自己再连接别的 DB。

这使数据库事务内的 Attempt/Assignment 可以在同一数据库范围内关联，也减少了“一边读 A.db，一边写 B.db”的应用构造错误。不过**共享 Session Factory 并不意味着所有 Service 的每个调用自动共享同一个事务**：每个 Repository 函数仍可能独立开 Session 和 Transaction。

### 12.3 Recoverable Session Factory 只做依赖注入

`create_recoverable_numeric_session_service(bundle, *, orchestrator, student_id, course_id, objective_id, session_id)` 将现有 Bundle 中的三个 Repository 注入 Recovery Service，不新建 Engine、数据库或用户身份。这里依旧依赖调用方提供可信的 Server-side Session Context。该 Factory 也不会生成 LLM Agent，或者把 Jev / NeoHorse 的模型接入 URPP。

**源锚点**：`0bc3250` Engine / tests；`fc91a60` FastAPI startup / tests；`f22dbf9` Bundle / tests；`c24d1dc` Service Factory / tests；`final_snapshot_f86f68d7b4/backend/app/main.py`。

---

## 13. 真实故障：13E-3C CLI 的两次 Timestamp Bug

**证据来源区分**：这份 Reply 6 ZIP 保存了 `b8abf71` 已修复的 CLI 代码、五个最终 CLI 测试及文档，**没有收入最初两次失败的 pytest 日志和第一次修复的中间 Commit**。以下失败信息与历史测试计数来自此前用户在聊天中提交的真实终端输出；对具体原因的描述同时可由 ZIP 中的最终 Repository、Recoverable Session 与 CLI 函数相互印证。不能把“代码包含修复逻辑”本身当成历史失败日志。

### BUG-13E-3C-TIME-01：数据库已经 Commit，但 State 的 `as_of` 较早

**用户可见症状**：CLI 似乎报告回答未被接受，然而 Assignment 已转 Completed，Attempt 已写入 SQLite。原始失败测试记录显示首次专项运行 `2 failed, 57 passed`；精确终端堆栈应在后续原始日志集中归档，本 ZIP 未包含。

**执行时间线**：

```text
t0 = CLI calls now_utc() for as_of
    ↓
submit_numeric_answer(..., as_of=t0)
    ↓
Repository clock reads t1 = submitted_at; t1 > t0
    ↓
with session.begin(): INSERT Attempt + UPDATE Assignment + COMMIT
    ↓
Recoverable Service checks: as_of < attempt.submitted_at
    ↓
ValueError: State-estimation time precedes submission.
    ↓
Caller sees an exception, but database submission is already committed
```

**根因**不是 Numeric Scorer 认为 `5` 错了，也不是事务部分失败；是 **State Snapshot Time 的时间契约与数据库实际提交时生成的提交时间不同步**。`RecoverableNumericSessionServiceV01.submit_numeric_answer()` 先调用 Repository，之后明确验证 `as_of >= attempt.submitted_at`，因此这一异常可以发生在已经成功 Commit 之后。

**为什么不能重新提交？** Assignment 已 Completed；第二次提交既不能撤销第一笔 Attempt，也不是“重试未提交的事务”。用户在 UI 中看到的“提交失败”必须和数据库实际结果区分开。正确恢复路径是读取已有 Session/Assignment/Attempt，用新且足够晚的 `as_of` 调用 `resume()`。

### BUG-13E-3C-TIME-02：第一次修复制造了未来 State 快照

历史中间修复曾使用如下形式：

```python
# historical intermediate approach, not current final code
resume(as_of=now_utc() + timedelta(seconds=1))
```

它可以让恢复时刻晚于刚保存的 Attempt，但紧接着创建下一轮教学 Decision 却再次使用普通 `now_utc()`，于是出现：

```text
Student State as_of = t_now + 1 second
Next Decision requested_at = t_now + tiny_delta
Decision requested_at < state.as_of
    ↓
ValueError: Decision cannot precede its Student State snapshot.
```

这是典型的**局部修复满足 A 的时间条件，却破坏了 B 的时间条件**。原始中间测试记录为 `3 failed, 2 passed`，但本资料包没有中间代码版本，具体失败堆栈仍需独立保存。

**最终 CLI 的实现**：匹配特定 `State-estimation time precedes submission.` 后，不重复提交；改用新的 `now_utc()` 调用 `resume()`，随后创建下一轮 Decision 时使用 `requested_at=completed.state.as_of`。因此下一轮 Decision 不会早于用于决策的 State 快照。最终 CLI 的五项测试、历史专项回归 59 项和完整 Backend 468 项通过（这三个**测试计数取自此前用户提供的执行日志**；ZIP 中没有这 59/468 次完整运行的原始输出）。

**关键恢复规则**：有明确证据表明 Commit 已成功之后，应恢复已保存的记录；若 Commit 结果未知，不能仅靠异常字符串假设一定已成功，正式应用应读取数据库确认 Assignment/Attempt 的最终状态再采取操作。当前 CLI 是一个受控本地合成 Demo，不等于已经实现通用的幂等 HTTP 提交协议。

**源锚点**：`b8abf71/scripts/run_local_numeric_lesson_v01.py` 的 `run_lesson()` 异常处理、`completed.state.as_of` 的下一轮 Decision；最终 `recoverable_numeric_session_v01.py::submit_numeric_answer()`；此前用户提供的两次原始失败输出。

---

## 14. Guard Casebook：测试覆盖的潜在失效，不冒充真实事故

以下均可在这份 ZIP 对应历史测试中定位。测试名称说明它**试图验证什么**；除非附有用户原始失败日志，否则不能声称这些问题曾经发生在真实教学或已部署环境。

| Guard ID | 可复现失效情境 | 核心防线 | 相关测试 |
|---|---|---|---|
| `GUARD-P06-01` | 向相同 Session 发出第二条 Pending | Unique Pending Session Key；Repository `flush()` 检查 | `test_second_pending_assignment_is_rejected_by_database` |
| `GUARD-P06-02` | 已完成 Assignment 仍占 Pending 槽 | 同事务将 Key 置 NULL；状态一致性 CHECK/Trigger | `test_completed_assignment_releases_pending_slot` |
| `GUARD-P06-03` | 同会话重复使用 Decision ID | `(session_id,decision_id)` UNIQUE | `test_completed_decision_id_cannot_be_reused` |
| `GUARD-P06-04` | 两个线程同时发题 | DB 约束 + 事务；允许失败侧是唯一性或 SQLite Lock | `test_concurrent_issuance_produces_at_most_one_pending` |
| `GUARD-P06-05` | 两个线程同时提交同一题 | 条件 UPDATE + 事务；最终仅 1 Attempt | `test_concurrent_submission_creates_exactly_one_attempt` |
| `GUARD-P06-06` | Attempt INSERT flush 成功但 Assignment UPDATE 失败 | `session.begin()` Rollback | `test_failed_assignment_update_rolls_back_attempt` |
| `GUARD-P06-07` | 数据库已经 Commit，状态重建人工注入失败 | 新 Service 从持久化事实恢复 | `test_recovery_after_database_commit_and_state_failure` |
| `GUARD-P06-08` | 恢复后仍有 Pending 却再次发题 | `resume()` 恢复 Pending；发题入口拒绝 | `test_pending_assignment_cannot_be_replaced_after_restart` |
| `GUARD-P06-09` | 错误学生或 Session 试图提交/恢复 | 全字段 Scope 核查（非身份认证） | `test_another_student_cannot_complete_assignment`；`test_other_student_cannot_resume_session` |
| `GUARD-P06-10` | 用户提交记录被换到另一个 Assignment 或 Item Revision | Completion Service 严格校验 ID/Revision/Response Group | `test_tampered_attempt_assignment_link_is_rejected`；`test_tampered_attempt_revision_is_rejected` |
| `GUARD-P06-11` | 迁移遇到重复 Pending/Decision 历史行 | 只读数据审计阻止应用升级 | `test_duplicate_pending_legacy_rows_stop_migration`；`test_duplicate_decision_legacy_rows_stop_migration` |
| `GUARD-P06-12` | 不存在 Session 或历史 Scope 矛盾 | Migration Audit / Readiness fail closed | `test_orphan_assignment_blocks_upgrade`；`test_scope_mismatch_blocks_upgrade` |
| `GUARD-P06-13` | 重建 Assignment 表时存在依赖它的外部表 FK | 拒绝自动重建未知依赖 | `test_inbound_foreign_key_blocks_table_rebuild` |
| `GUARD-P06-14` | 连接池中 FK 被关闭 | 每次 checkout 再检查 `PRAGMA foreign_keys` | `test_pool_rejects_connection_with_foreign_keys_disabled` |
| `GUARD-P06-15` | Readiness 后数据库路径丢失 | `mode=rw` 禁止静默创建替代 DB | `test_database_is_not_recreated_if_removed_before_connect` |
| `GUARD-P06-16` | 未配置数据库时误使健康检查失效 | FastAPI lifespan 数据库 opt-in | `test_health_only_startup_needs_no_database` |
| `GUARD-P06-17` | Session Factory 偷建另一套 Repository 或 Engine | 强制注入 Startup Bundle 的具体对象 | `test_factory_uses_exact_startup_repository_instances` |
| `GUARD-P06-18` | CLI 意外覆盖已有真实数据库 | `O_EXCL` 新建专用 Demo DB；已有文件拒绝 | `test_cli_refuses_existing_database_without_modifying_it` |
| `GUARD-P06-19` | 无 app-help 日志错误地当成独立作答 | Attempt 的帮助字段保留 UNKNOWN | `test_real_cli_no_help_does_not_imply_independence` |
| `GUARD-P06-20` | 学生退出 CLI，Pending 丢失 | 退出不完成 Assignment | `test_cli_quit_keeps_assignment_pending` |

特别说明：`test_failed_transaction_restores_source_schema` 是**故障注入迁移测试**；它验证在 COMMIT 前出错时旧 Schema 仍在，不意味着曾真实对用户数据库进行失败迁移。`test_real_cli_hint_answer_and_sqlite_recovery` 是本地受控演示的整合测试；它证明此场景可运行，但不是教学效果或独立掌握的验证。

---

## 15. Code Walkthrough：一次完整的本地教学示范（不扩大其能力声明）

`b8abf71` 的 `scripts/run_local_numeric_lesson_v01.py` 实际使用一项合成 Arithmetic Objective 和 Numeric Item：`What is 2 + 3?`，Rubric 预期 5，Tolerance 0。CLI 只接受**不存在**的新 Demo SQLite 文件，并使用本地 `Base.metadata.create_all(engine)` 初始化**这一份明确的新数据库**；它不把 `create_all()` 当成已有数据库的 Schema Migration。

```text
CLI start with NEW synthetic DB
  → initialize schema and enable SQLite FK for demo engine
  → build Assessment / Assignment / Session / Assistance repositories
  → create static Demo Agents and Presentation Service
  → register synthetic teaching session
  → issue version-bound Numeric Assignment
  → terminal prints stored question
  → optional `hint` / `solution`: presenter prints content, then logs app report
  → student submits numeric response
  → atomic Assignment + Attempt completion
  → recover State from stored records
  → display included/excluded Evidence and assistance-event count
  → Decision Engine selects next action from recovered State
  → static Professor Agent prints teaching content
```

本地输出 Flush 说明程序将文本交给终端输出流，**不证明学生已经阅读或理解了内容**。无帮助日志也不能证明学生没有外部帮助。CLI 的 Agent 返回固定字符串，没有接入真实 LLM，未提供生产学生身份认证或 HTTP 教学 API。它的测试记录是本地功能和数据一致性证据，而不是“真正证明学生学会了数学”的实验结论。

---

## 16. 容易再次引入的架构错误：维护检查清单

1. **不要为一次课程建立一个跨整个教学过程的超大数据库事务**：Assignment/Attempt Atomic Submission 与教学显示/State Reconstruction 属于不同边界。需要清晰报告“数据库提交成功、后续处理失败”这一可恢复状态。
2. **不要在提交失败提示出现时盲目重新提交**：先读取真实 Assignment 状态；若 Completed，恢复已有 Attempt；若 Pending，才可讨论重新提交。
3. **不要使用未来时间来快速绕过 Snapshot 时序验证**：`decision.requested_at >= state.as_of` 和 `state.as_of >= attempt.submitted_at` 都需满足。一次局部修复必须检查全链路时间关系。
4. **不要把不存在的 Assistance Event 翻译成 `assistance_level=0`**：持久化提交的作答条件仍可能未知；后续 Learning Observation 与 Mastery Evidence 要分别维护。
5. **不要默认 ORM Model 的变更已经作用于历史数据库**：用已知的 Schema Audit、独立备份、显式 Migration 和部署前 Readiness；失败应停止而不是尝试“自动修好”。
6. **不要通过另一套未经检查的 Engine 绕过 Startup Bundle**：当前的 FK 保护仅对实际使用该 Engine 的连接有效。
7. **不要把 Scope Equality 当成认证**：当前 Internal Services 只比较字符串 ID；未来正式 API 必须从可信身份/会话上下文导出 Scope。
8. **不要把用户已经看过题目或 Hint 作为数据库事实**：Assignment 已发、Presenter 已 Flush、应用已记录帮助，分别属于不同观察层次。
9. **不要在多个查询步骤之间默认存在原子 Read Snapshot**：当前 Recovery 的 Repository 读取并不自动绑定为一个跨表的相同时间视图；更高并发需求应单独设计。
10. **不要从 Test Function 名字反推出真实历史 Bug**：应提供原始失败日志、当时假设、修复 Diff 和测试验证，才可在 Casebook 中标 `HISTORICAL BUG`。

---

## 17. 历史来源和证据级别

**直接源自 ZIP 的已核查事实**：19 个历史 Commit 下列出的文件；源码对约束、Repository 方法、Migration、Readiness、Engine、Lifespan、CLI 的实际实现；各测试文件包含的验证用例。ZIP 的 `SOURCE_MANIFEST.json` 记录每份文件的 Commit、相对路径及 SHA-256。SHA-256 用于检测提取文件是否改变，不是代码来源的签名认证，也不证明作者或运行环境可信。

**来自此前用户提供的真实运行日志（不在当前 ZIP 内）**：13E-3C 的两次 CLI 时间戳异常、对应中间失败计数、最终 `5/59/468 passed` 和 Commit `b8abf71`。当前 ZIP 可以交叉核对最终错误处理代码和五项 CLI 测试，但若要在网站中逐行展示最初 Traceback 与原始 Repair Diff，仍需另存对应完整终端输出。

**本章事后工程解释**：例如“为什么先读 Pending 无法替代条件 UPDATE”“为什么 Scope FK 要四列”“为什么未来可能需要一致性 Read Snapshot”是从历史实现及数据库语义推导出的教学解读，不应被反写为当时开发者在每一次 Commit 中留下的逐字动机。

**不能由本包证明的事**：历史上每项 Guard 是否由真实事故触发；任何正式生产部署、跨进程完整并发认证、学生现实身份认证、真实 LLM 接入、独立作答证明、广泛教学有效性、其他数据库方言可用性。

### 文件级定位索引（读原始档案时按该路径查找）

| 主题 | 历史来源 |
|---|---|
| Assignment 首次持久化与初始测试 | `history/assignment_persistence_b36c7b5fba/backend/app/repositories/numeric_assignment_v01.py`；`.../test_numeric_assignment_v01.py` |
| Completed Assignment→State | `history/completed_assignment_state_174f259e7a/backend/app/services/decision/completed_assignment_state_v01.py`；对应测试 |
| Legacy Loop 的 `_requires_recovery` | `history/persisted_numeric_loop_692b6943f4/backend/app/services/decision/persisted_numeric_session_loop_v01.py` |
| Session Identity 和真正的新实例恢复 | `history/session_recovery_cf9ab746db/backend/app/repositories/numeric_session_records_v01.py`；`.../recoverable_numeric_session_v01.py`；对应测试 |
| Pending/Decision 约束及并发/回滚 | `history/assignment_invariants_a562e6711b/backend/app/repositories/numeric_assignment_v01.py`；`.../test_numeric_assignment_invariants_v01.py` |
| 第一代 Migration | `history/assignment_migration_79e250c760/backend/app/repositories/migrate_numeric_assignment_v01_sqlite.py`；对应测试 |
| Readiness + Session FK Audit | `history/database_readiness_1f50e80483/...`；`history/foreign_key_readiness_cd5c7d4cde/...` |
| Registered Session FK 与更严格的默认发题 | `history/strict_session_assignment_0f32231201/...`；`history/registered_session_default_e735c0fbdf/...`；`history/remove_unregistered_issuance_f86f68d7b4/...` |
| 第二代 Migration | `history/foreign_key_migration_3cbeffabe4/backend/app/repositories/migrate_numeric_session_fk_v01_sqlite.py`；对应测试 |
| Engine → Startup → Bundle → Factory | `history/guarded_sqlite_engine_0bc3250fb7/...`；`history/sqlite_startup_fc91a60a7d/...`；`history/repository_injection_f22dbf930d/...`；`history/recoverable_session_factory_c24d1dc84d/...` |
| 最终 CLI | `history/local_numeric_cli_b8abf71993/scripts/run_local_numeric_lesson_v01.py`；其五个 CLI Tests 与 `docs/24_local_numeric_teaching_cli_v0.1.md` |

**完整索引**见本次 Release 包内的 `evidence/reply6_source_index.json`，保存了 71 份文件的历史 Commit、Archive Path、Size、SHA-256 和逐阶段对象信息。下一阶段将继续研究后续教学链路，并将本章链接进网站的统一导航与全站检索。
