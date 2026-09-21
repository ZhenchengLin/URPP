# URPP Engineering Archive · Reply 8 / 10
## Transfer Assessment、Reviewer Authorization 与 Evidence Integrity

> **历史定位**：Implementation 13D-1A → 13D-1B → 13D-1C1 → 13D-1C2 → 13D-1C3 → 13D-1C4 → 13D-1C5。上述编号取自历史源码和设计文档，不把 `docs/12` 或 `docs/18` 误读为独立的 Implementation 编号。  
> **材料范围**：你上传的 `transfer_review_history_source_pack.zip` 中的 7 个 Git checkpoint、60 条源码/测试/Diff/快照条目以及 `SOURCE_MANIFEST.json`；文件通过 ZIP 完整性检查。  
> **证据性质**：Git 对象可以确认历史代码如何变动；自动测试可以确认设计了哪些防护情境；本资料包没有对应七个阶段的原始失败 pytest 日志，不能杜撰曾经出现过的生产事故。  
> **重要的当前边界**：截至包内最后一个 snapshot（`4e165f2`），本章展示的 `RecoverableNumericSessionServiceV01` 对 `TRANSFER_ASSESSMENT` **仍然无条件拒绝持久化发题**。新增 Review Application 能记录 Review Claim，不意味着 Transfer Delivery 已解锁。

---

## 1. 一条线看懂整个故事

**学生请求 Transfer** → **个性化决策可能选中 TRANSFER_ASSESSMENT** → **原始普通题可能被错误附上 Transfer Action** → **13D-1A 新增 Action–Item 结构校验** → **发现“题目被标成 Transfer”仍不等于设计有效** → **13D-1B 加入与题目内容绑定的 Review Draft** → **Draft 未获可信授权，13D-1C1 将 Transfer 发题关闭** → **13D-1C2 定义 Reviewer 身份/权限接口** → **13D-1C3 保存版本绑定的 Review Decision** → **13D-1C4 解释 Review History** → **13D-1C5 串起内部 Review 写入流程** → **仍不打开发题闸门**。

这串事件有两个互相独立的结果：一方面，教学系统不再能够仅凭学生的请求把普通题作为 Transfer Assessment 发放；另一方面，开发出一条可记录内部 Review 的原型流程。**两个成果之间尚缺可信审批来源、审批有效性判定和发题时授权验证的连接。** [S01–S07, D12–D18]

### 1.1 五种“看起来像批准”的东西，实际各是什么？

| 现象 | 能说明什么 | 不能说明什么 |
|---|---|---|
| `selected_action == TRANSFER_ASSESSMENT` | 选中了一个教学动作 | 题目真的测 Transfer；题目已获批准；学生会独立完成 |
| `item.evidence_type == TRANSFER_ATTEMPT` | 题目具有结构标签 | 其设计经真实专家审阅、具备新的应用情境 |
| 成功创建 `TransferDesignReviewDraftV01` | 填写了一份绑定该题内容的待审设计说明 | 有人已经审核、审核者真实存在、已有发题授权 |
| 保存 `TransferReviewDecisionV01(outcome=APPROVE)` | 数据库里有一条声称批准的历史记录 | 写入者有权批准、该记录当前有效、能够发题 |
| `APPROVE_RECORDED` | 该序列在所选时刻最新的记录声称批准 | 真实 Reviewer 身份或审批来源已获验证；可绕过 Delivery Gate |

如果以后浏览这章只记住一句话：**Action、Tag、Draft、Recorded Decision、Trusted Delivery Authorization 属于五个不同的事实层次，不能用一个 `approved=True` 把它们合并。** [S01–S07]

---

## 2. 历史时间线与实际变更（严格按 Git checkpoint）

| 阶段 / Commit | 当时可确认的实际变更 | 本阶段没有完成的事 |
|---|---|---|
| **13D-1A · `e2ef14dd3e`** | 新增 `require_eligible_assessment_action_v01()`；在 Recoverable Session 发题前检查 Action–Item 对应关系；增加结构校验测试及 `docs/12` | Transfer 设计实质审核、受助/独立证明 |
| **13D-1B · `1e6ca9802a`** | 新增 `TransferDesignReviewDraftV01`、完整 Item Fingerprint、Draft–Item Binding、设计问题字段及 `docs/13` | 真实 Reviewer、批准记录、数据库中获取权威 Revision |
| **13D-1C1 · `bbddaf38ed`** | 新增始终拒绝 Transfer 的 `require_trusted_transfer_delivery_v01()`；接入 Session；补充拒绝未获批准发题的测试及 `docs/14` | 任何“有 Approval 就放行”的路径 |
| **13D-1C2 · `d8aac30f08`** | 新增 Identity/Permission Provider Protocol、时间/Issuer/Scope 校验、Fail-Closed 的 Authorization Service 和 `docs/15` | 真实已部署的认证系统、生产权限管理 |
| **13D-1C3 · `8c83c51ae6`** | 新增 Review Decision Contract、完整 Draft Hash、关联 Item Revision 的 Repository 与 SQLite 测试及 `docs/16` | `is_approved()`、可信签发来源、生产 Migration |
| **13D-1C4 · `bc79363d17`** | 增加 REVOKE 记录类型与 Lifecycle 状态解释；对同时间戳、重复 ID、未来时间与不同 Item 历史作出显式处理；`docs/17` | 有权撤销的身份审计、真实顺序保证、审批令牌 |
| **13D-1C5 · `4e165f2b35`** | 新增 `TransferReviewApplicationServiceV01`：加载存储题目→获取时间→调用授权接口→生成 Decision ID→保存；`docs/18` | 将身份与写入做成不可绕过的生产边界，或将记录结果接到 Delivery Gate |

**如何复核**：每个节点在资料包中同时有 `history/<label>_<hash>/...` 的该次 Git 文件快照和 `diffs/<label>_<hash>.patch` 的原始变更。`final_snapshot/` 是最后一个节点的版本，**不应倒写成所有早期节点都具备该能力**。 [M01]

---

## 3. 13D-1A：普通 Numeric Item 不能靠 Request 被重新命名为 Transfer

### 3.1 问题产生的调用边界

`PersonalizedDecisionEngine` 可以因为明确的学生请求选中 `TRANSFER_ASSESSMENT`。历史 `docs/12` 明确记载：原先 Recoverable Session 曾允许将一个普通 `PROBLEM_ATTEMPT` Item 连同 Transfer Action 持久化。**文档明确把它描述为原先的设计缺口；资料包没有提供真实学生被错误评分的事故记录。** [D12]

先区分三类对象：

```text
StudentLearningRequestV01: REQUEST_TRANSFER
      → 只是学生想开展的活动
TeachingActionV01: TRANSFER_ASSESSMENT
      → 只是当前教学轮次选中的动作
AssessmentItemV02.evidence_type: PROBLEM_ATTEMPT / TRANSFER_ATTEMPT
      → 是具体题目自身保存的结构标签
```

错误关联路径在概念上相当于：**请求 Transfer → 动作 Transfer → 不检查题目 → 普通题按 Transfer 动作被 Issue**。修复的着力点不是修改 Student State 或 Numeric Rubric，而是在执行发题前增加 Action–Item 一致性检查。 [S01, D12]

### 3.2 真实实现：`require_eligible_assessment_action_v01()`

输入为已选择的 `TeachingActionV01` 和实际加载的 `AssessmentItemV02`；返回 `None` 表示结构检查通过，失败抛出异常：

```python
if selected_action not in ASSESSMENT_ACTIONS:
    raise ValueError("Numeric Assignment requires an assessment action.")

if not item.alignment_verified:
    raise ValueError("Assessment objective alignment is not verified.")

if (
    selected_action == TeachingActionV01.TRANSFER_ASSESSMENT
    and item.evidence_type != EvidenceType.TRANSFER_ATTEMPT
):
    raise ValueError(
        "Transfer assessment requires a transfer-tagged Assessment Item; "
        "an ordinary problem cannot be relabelled by a student request."
    )
```

真实代码另有两个类型检查：必须传 `TeachingActionV01` 和 `AssessmentItemV02`，不能把任意字符串或任意对象传入。对于 `DIAGNOSTIC_ASSESSMENT`、`INDEPENDENT_PRACTICE` 等普通 Assessment Action，结构守卫不会要求必须具有 Transfer Tag。**这是一项必要结构条件，不是认定题目具有知识迁移效度的充分条件。** [S01, T01]

### 3.3 这一检查在 Session 的哪一步？

最后节点的 `RecoverableNumericSessionServiceV01.deliver_numeric_assessment()` 顺序是：恢复 Session → 确认没有 Pending Assignment → 校验 Decision ID 尚未使用 → 加载原始 Item Revision → 检查 Course/Objective 与 Alignment → **调用 `_turn_orchestrator.run_turn()`** → 验证返回的是 Assessment Action → **检查 Action–Item** → **检查 Transfer Delivery Gate** → 生成 `AssessmentDeliveryV01` → `issue_assignment()`。 [S08]

特别留意粗体位置：**教学 Agent 已在两个 Gate 之前被 Orchestrator 调用。** 这些 Gate 能阻止不合法的 Assignment 被持久化；它们**不保证 Agent 完全没有执行，也不保证前端从未见过 Agent 生成的内容**。这不是推测，`docs/12` 和 `docs/14` 明确写出了这一限制。后续若要实现“所有无效动作在调用 Agent 前就拒绝”，需要拆分 Decision、Validate 和 Execute 三个步骤，而不能只改变当前 Gate 的返回值。 [D12, D14, S08]

### 3.4 重要的交叉限制：当前 Numeric Scorer 不能自动产生 Transfer Success

最后 snapshot 的 `score_numeric_attempt()` 明确要求 `item.evidence_type == EvidenceType.PROBLEM_ATTEMPT`，并且输出 `transfer_distance="none"`；它复制 Attempt 的 `assistance_level` 和 `prior_solution_exposure`，不从答案正确推断独立性。因此即便某个 Transfer-Tagged Item 最终能被发放，**这个 Numeric Scorer 仍不能因此自动产生经验证的 Transfer Performance Evidence**。新的 Transfer Scorer、评估设计验证以及受助条件规则属于另外的工作范围。 [S09]

---

## 4. 13D-1B：为什么 Review Draft 必须同时描述“新情境”与“非迁移路径”？

### 4.1 题目标签无法证明它真的需要迁移

把 `evidence_type` 写成 `TRANSFER_ATTEMPT` 是一个结构声明。真正的 Transfer 问题要求学生把曾经学过的知识应用到新的情境中。历史 Draft 收集的内容是具体的设计理由，而不是一个无说明的 `is_transfer=True`。 [D13]

| Draft 字段 | 它回答的问题 |
|---|---|
| `source_learning_context` | 学生先前在什么情境里学习了这项知识？ |
| `target_application_context` | 现在打算在哪个新情境下考查？ |
| `changed_context_factors` | 哪些背景、呈现方式或应用条件具体改变了？至少一项 |
| `invariant_knowledge` | 跨越情境保持适用的原理是什么？ |
| `required_transfer_reasoning` | 学生必须做哪种识别、推导或应用才能完成任务？ |
| `plausible_non_transfer_path` | 学生能否不理解迁移、只靠记忆或机械套题就碰巧答对？ |
| `review_questions` | 审阅者还要确认哪些疑点？至少一项 |

最后两个字段尤其重要：即使题面改了故事背景，学生也可能依靠记忆中的模式机械答对。Draft 应当把这种可能路径写出来，以便未来 Reviewer 判断这道题是否真的能够区分迁移与重复练习。**字段非空不等于审阅通过，Draft 也不能自动验证学生是否具备 Transfer 能力。** [S02, D13]

### 4.2 完整 Item Fingerprint 的推导

`fingerprint_assessment_item_v01(item)` 对 `AssessmentItemV02.model_dump(mode="json")` 使用稳定排序的 JSON 序列化，再计算 SHA-256：

```python
serialized = json.dumps(
    item.model_dump(mode="json"),
    sort_keys=True,
    separators=(",", ":"),
    ensure_ascii=False,
    allow_nan=False,
)
item_content_sha256 = sha256(serialized.encode("utf-8")).hexdigest()
```

这会将 Draft 绑定到 Item 的**当时完整模型内容**。相比仅比较 `assessment_item_id`，Prompt、Rubric、Evidence Tag 等字段变化都会改变序列化数据的摘要。但还需要额外保存并比较 `item_revision`、Course、Objective 和 Item ID，因为 Revision 在此阶段由调用者传入，**函数本身不会查数据库证明该 Revision 对应权威题目**。 [S02, D13]

`require_current_transfer_review_binding_v01()` 依次要求：Draft/Item 类型正确 → ID/Revision/Course/Objective 一致 → 内容 Fingerprint 一致 → 当前 Item 仍有 Transfer Tag 和 Verified Alignment。通过表示“这份 Draft 仍绑定当前提供的 Item 快照”，**不表示审批、签名或来源真实**。 [S02]

### 4.3 Hash 到底能证明什么？

- **可以**：在采用同一序列化协议的前提下，检测 Draft 与当前 Item 模型内容不一致。
- **不能**：证明某个 Item 确实源自可信 Repository；证明 Reviewer 的真实身份；阻止能够任意更改 Draft 和 Item 的同一调用者重新计算匹配 Hash；证明一题具有教育测量效度。

这是内容一致性校验（change detection），不是授权机制（authorization），也不是数字签名（digital signature）。 [S02, D13]

### 4.4 历史测试证明了什么？

`test_transfer_design_review_v01.py` 检查同一内容给出相同摘要、修改题目内容后旧 Draft 失效、更改 Revision/Item ID 后拒绝、普通题和未确认 Alignment 不能创建 Draft、必填文本和时区时间不可缺失，以及 Draft 中没有 Approval/Reviewer 权限字段。**这些是设计的防御性测试，包中没有“修改题目后系统曾错误重用旧 Draft”的真实生产日志。** [T02]

---

## 5. 13D-1C1：为什么一开始选择“全部拒绝 Transfer 发题”

13D-1A 已经能拒绝普通题冒充 Transfer，但一条真实的 Transfer Tag 仍不足以证明题目审核完成。13D-1B 虽能产生 Draft，却没有可依赖的真实 Reviewer Authorization，也没有可信 Approval Source。这里引入的 `require_trusted_transfer_delivery_v01()` 非常小，但边界非常明确：

```python
def require_trusted_transfer_delivery_v01(*, selected_action):
    if not isinstance(selected_action, TeachingActionV01):
        raise TypeError(...)
    if selected_action == TeachingActionV01.TRANSFER_ASSESSMENT:
        raise ValueError(
            "Transfer Assessment delivery requires a trusted "
            "Transfer Design Approval. No trusted approval source is configured."
        )
```

普通 Assessment Action 可以继续走原流程。Transfer Action **不查 Review Table，也不接受 `approved=True` 参数，始终拒绝**。这个版本并不存在“只要数据库 APPROVE 一条就通过”的代码路径。 [S03, D14, T03]

### 5.1 两道 Gate 分别干什么？

```text
Item 与 Action 不匹配
    ↓ require_eligible_assessment_action_v01
    REJECT：普通题不能被贴上 Transfer 标签

Item 与 Action 在结构上匹配，且 Action 是 Transfer
    ↓ require_trusted_transfer_delivery_v01
    REJECT：不存在可信 Approval Source
```

通过第一道 Gate 的 Transfer Item 仍在第二道被拒绝。**结构有效与发题授权不能合并判断。** [S01, S03, S08]

### 5.2 这道 Gate 的范围不是“整个 URPP 所有可能入口”

`docs/14` 清楚说明，Gate 接入了 `RecoverableNumericSessionServiceV01`，**但不声称已覆盖所有历史 Legacy Delivery Path**。另外，Agent 先于 Gate 调用。本章所说“不能发 Transfer”特指源码已连接的这条 Recoverable Session Assignment 路径，并不对未审查的其他路径做全局安全承诺。 [D14, S08]

---

## 6. 13D-1C2：Identity Assertion、Permission Provider 与真实认证不是同一件事

### 6.1 分工：身份和权限是两个独立的查询

`ReviewerIdentityProviderV01.current_reviewer()` 的接口返回一个 `ReviewerIdentityAssertionV01 | None`，其中含 `reviewer_id`、`issuer`、`verified_at`。`TransferReviewPermissionProviderV01.may_approve_transfer()` 则以 Reviewer、Issuer、Course、Objective 为输入返回布尔值。**“知道是谁”不等于“有权审核这一课程的这一知识点”。** [S04]

`ReviewerIdentityAssertionV01` 是普通 Python dataclass；任何能构造这个对象的代码都可以写 `reviewer_id="reviewer-001"`。`Protocol` 同样只是规定调用接口，**不会自动创建可信身份来源**。因此此模块被准确命名为 Authorization Contract / Policy Prototype，而不是 Production Authentication。 [S04, D15]

### 6.2 `require_reviewer_for_draft()` 的完整检查链

1. `as_of` 必须是带时区的时间。
2. `require_current_transfer_review_binding_v01()` 必须通过，**先拒绝过期 Draft，再查询身份/权限 Provider**。
3. 两个 Provider 都必须已配置，否则 Fail Closed。
4. 调用 Identity Provider；异常、`None`、错误返回类型均被拒绝。
5. Identity 的 Issuer 必须与应用配置一致。
6. `identity_age = as_of - identity.verified_at` 必须位于 `[0, 15 min]`；未来时间或过期时间均拒绝。15 分钟是原型的暂定参数，不是经过验证的生产 Session Policy。
7. 调用 Permission Provider，传入 Reviewer ID、Issuer、Course、Objective；异常与拒绝均 Fail Closed。
8. 返回值必须**恰好是 `True`**，字符串 `"true"` 或整数 `1` 不算授权结果。
9. 返回 `ReviewerAccessCheckV01`，包含本次绑定的 Item ID、Revision、Content Hash、Issuer、Reviewer 和检查时间。 [S04, T04]

### 6.3 这条边界最容易被误解的地方

`ReviewerAccessCheckV01` 不是 HMAC 签名或可转移的授权令牌；它只是一次由**已配置 Provider**得出的检查结果。若学生面对的 API 允许调用者注入任意 `FakeIdentityProvider` 和 `FakePermissionProvider`，那 API 本身就没有建立真实认证边界。真实系统必须由可信应用层独占 Provider 配置、限制构造 Service 的权力、绑定登录用户，并限制 Repository 的直接写入权限。 [S04, D15]

**历史实测范围**：测试文件使用的是 `TestIdentityProvider` / `TestPermissionProvider` 等替身。它测试缺少 Provider、Issuer 错配、身份过期或来自未来、权限拒绝、Provider 抛错、Draft 失效和错误类型；**没有验证真实身份系统已经上线**。 [T04]

---

## 7. 13D-1C3：Decision Contract 和 SQLite Repository 保存的是 Claim，不是 Delivery Token

### 7.1 Decision 对象包含哪些字段

`TransferReviewDecisionV01` 的实际字段：

```text
decision_id
assessment_item_id, item_revision
course_id, objective_id
item_content_sha256, draft_content_sha256
reviewer_id, reviewer_identity_issuer
outcome: approve / reject / revoke（REVOKE 于后续 13D-1C4 加入）
rationale, decided_at
```

其中 `draft_content_sha256` 对**完整的 Review Draft**做稳定 JSON + SHA-256，而 `item_content_sha256` 指向完整 Assessment Item。这样以后修改 Review 的实质理由不会默默被当成原先 Decision 的相同 Draft。Reviewer ID 和 Issuer 在对象中只是**被记录的声明**，不能自证其来源可信。 [S05, S06]

注意历史时间：最初 `8c83c51` 版本的 `TransferReviewOutcomeV01` 只有 APPROVE/REJECT；随后 `bc79363` 才增加 REVOKE。网站使用最后 snapshot 讲解最终字段时，仍单独记录了这次增量，不将新状态倒写回旧 Commit。 [P06]

### 7.2 Repository 的实际数据库设计

`TransferReviewDecisionRow` 的主键是 `decision_id`，还有 `assessment_item_id`、`item_revision` 和 JSON `payload`。数据库表声明了 `(assessment_item_id, item_revision)` → `assessment_items_v02` 同一对列的 Composite Foreign Key（`ON DELETE RESTRICT`）。Repository 的 `save_decision()` 会在同一个数据库 Session 内检查：Decision ID 未使用 → 目标 Item Revision 存在 → Item 类型为 Numeric → Course/Objective 一致 → 重算 Item Fingerprint 一致 → 添加 Row → Commit。失败时不应把存储成功与 Review 通过混淆。 [S07]

`load_decision()` 按 ID 取回并验证为 `TransferReviewDecisionV01`。`list_decisions_for_item()` 按具体 Item Revision 列出历史记录，最后按 `(decided_at, decision_id)` 排序**只是返回的历史浏览顺序，不是取得当前授权的逻辑**。 [S07]

### 7.3 Append-only 的真实保证范围

Repository 不提供 Update/Delete 方法，并禁止重复 Decision ID 覆盖原记录；这防止正常调用该 Repository API 时“直接改写历史审批”。但能够使用底层数据库写权限的管理员或其他代码仍可能改 Row，因此不能把它描述为具备不可篡改审计（tamper-proof audit）。另外，这是 SQLAlchemy ORM 定义加 SQLite 单元/集成测试；**该阶段没有对现有生产库应用新表的 Migration，不能因有 `Base.metadata.create_all()` 测试就推断生产 Schema 已升级。** [S07, D16, T05]

### 7.4 一个贯穿全章的反例

```text
数据库存在记录：outcome = approve
          ↓
Repository.load_decision() 成功
          ↓
Lifecycle 解释：APPROVE_RECORDED
          ↓
require_trusted_transfer_delivery_v01(TRANSFER_ASSESSMENT)
          ↓
仍然抛出 ValueError
```

上面的最后一步不是未来猜想，而是历史测试明确检查的行为。原因是 Repository 根本不提供 `is_approved()`，而 Delivery Gate 也根本没有读取这张 Table。**保存决策和授权发题之间并不存在自动连接。** [S03, S07, T05]

---

## 8. 13D-1C4：Review Lifecycle 如何处理撤销、同时间戳与脏历史？

`evaluate_transfer_review_lifecycle_v01(item, item_revision, decisions, as_of)` 接收指定题目和一组历史 Decision，返回 `TransferReviewLifecycleResultV01(status, reason, current_decision_id, considered_decision_ids)`。**它不负责查数据库，也不验证 Reviewer 真伪，更不会打开 Delivery Gate。** [S10]

### 8.1 六种返回状态

| Status | 确切语义 |
|---|---|
| `NO_DECISION` | 输入历史为空 |
| `APPROVE_RECORDED` | 在有效、无冲突的输入历史中，最新唯一时间戳记录的 Outcome 为 APPROVE；只是一条 Claim |
| `REJECT_RECORDED` | 最新唯一时间戳的记录为 REJECT |
| `REVOKE_RECORDED` | 最新唯一时间戳的记录为 REVOKE |
| `AMBIGUOUS` | 至少两个不同 Decision 分享最新时间戳，即使两条都 APPROVE 也视为歧义 |
| `INVALID_HISTORY` | 重复 Decision ID、不同 Item/Revision/Scope/内容，或记录时间晚于 `as_of` 等 |

### 8.2 实际执行规则

1. 验证 `item`、正整数 Revision、带时区 `as_of`、Decision 序列及成员类型。
2. 输入为空返回 `NO_DECISION`。
3. 任意 Decision ID 重复 → `INVALID_HISTORY`，即使两条数据字段完全一致。
4. 逐条与本次 Item ID、Revision、Course、Objective、完整 Fingerprint 比较，任意不一致 → `INVALID_HISTORY`。
5. `decision.decided_at > as_of` → `INVALID_HISTORY`。
6. 按 `(decided_at, decision_id)` 排序找到最新记录，但**不允许使用 Decision ID 打破最新时间戳并列**；如果有两个最新时间戳相同 → `AMBIGUOUS`。
7. 在只有一条最新记录时，将 Outcome 解释为 APPROVE/REJECT/REVOKE 对应的 `*_RECORDED` 状态。 [S10, D17]

为何“两个相同时间的 APPROVE”仍不认定批准？因为它们可能是两个独立并发审核事件；Decision ID 是标识符，不是审阅先后发生的可信时间序列。随意用字符串大小决定审批结果会把数据库排序偶然性误认为真实审核顺序。 [S10]

### 8.3 REVOKE 只是历史记录，不是删除，也不是自动撤销已发出的所有题

`REVOKE` 在 `bc79363` 时增加到 Outcome Enum。记录 REVOKE 后最新 Lifecycle 可以显示 `REVOKE_RECORDED`。如果之后又出现更晚的 APPROVE，Lifecycle 可以变成 `APPROVE_RECORDED`；**但这既不证明撤销者有权撤销，也不证明后来的批准有权恢复授权**。源码明确拒绝把它当作 Delivery Permission。 [S06, S10, D17]

### 8.4 需要认真记录的剩余问题

- 时间由应用/调用链提供；Lifecycle 只检查时间是否相对 `as_of` 合法，不会证明时间来自不可伪造的服务器时钟。
- 它不会验证审批记录的真实写入来源、批准者/撤销者权限，或多 Reviewer 法定人数。
- 输入 Sequence 自身由调用方提供；若缺失真实历史记录，函数无法自行察觉“这里少了一条 REVOKE”。
- 当前 Review Repository 不会在每次写入时自动执行 Lifecycle Policy；这是读取历史后执行的描述性解释。 [D17, S07, S10]

---

## 9. 13D-1C5：Application Service 如何组装前面的组件？

**这是有实际代码调用顺序的一次内部 Review 写入操作，不是已经部署好的认证系统。** [S11, D18]

```text
submit_review(draft, outcome, rationale)
    ↓ 检查输入类型和理由非空
AssessmentRecordRepositoryV02.load_item(id, revision)
    ↓ 取数据库已存的精确 Item 版本，不信任外部临时 Item
Application clock() → decided_at
    ↓ 检查时区与 draft.created_at <= decided_at
TransferReviewerAuthorizationServiceV01.require_reviewer_for_draft(...)
    ↓ 检查 Draft–Item、Provider、Issuer、Freshness、Course/Objective Permission
验证 ReviewerAccessCheck 的 Item/Revision/Hash/Time 与本次操作一致
    ↓
token_urlsafe(24) 生成本次 decision_id
    ↓
create_transfer_review_decision_v01(...)
    ↓
TransferReviewDecisionRepositoryV01.save_decision(decision)
    ↓
return decision（历史 Claim，不是 Delivery Token）
```

### 9.1 方法签名刻意不暴露什么？

真实 `submit_review()` **只接收** `draft`、`outcome`、`rationale`，不接受调用者指定的 `reviewer_id`、`issuer`、`decided_at` 或之前构造的 `ReviewerAccessCheck`。该设计缩小了**经由这一方法**伪造审批信息的入口；但能控制构造函数里的 Provider/Clock，或绕过 Service 直接调用 Repository 的代码，仍可以产生未经真实授权的 Claim。 [S11, T07]

### 9.2 为什么先查存储题目，再核对 Draft？

13D-1B 的 Draft 创建器仅使用传入的 `AssessmentItemV02` 对象，不查 SQLite。Application Service 改为通过 `AssessmentRecordRepositoryV02.load_item(..., revision=...)` 加载历史保存的 Item，再把它交给 Authorization Service 做绑定检查。这样可以拒绝 Draft 指向不存在的 Item Revision，或与已保存 Item 内容不一致。但**从 Repository 取回与 Fingerprint 相符的 Item，不代表这道题已经被专业 Reviewer 确认为真正的 Transfer**。 [S02, S11, T07]

### 9.3 为什么 Authorization 和保存还不是一个原子动作？

源码明确注释：先调用授权 Service，再由另一个 Repository Session `save_decision()`；两步并非同一事务。若检查后写入前权限被撤销，或并发产生另一条 Review Decision，现有代码没有交易级别的当前审批有效性裁决。因为 Delivery Gate 仍关着，这个原型不会仅因这样的历史 Claim 直接开放 Transfer Assignment；但如果未来准备打开 Gate，必须先设计可验证的审批来源、撤销顺序和发题时重查。 [S11, D18]

### 9.4 测试范围：Fake Provider 的正面路径不等于真实授权

`test_transfer_review_application_v01.py` 使用 FakeIdentityProvider / FakePermissionProvider、临时 SQLite 和可注入 Clock，检验了正常写入和重新打开数据库恢复、Provider 缺失和权限拒绝时**不写入决策**、Issuer 错配、过期 Draft、Item Revision 不存在、Draft 产生于 Decision 之后、Clock 无效、接口不允许请求者伪造身份/时间、APPROVE 仍打不开 Delivery Gate。测试确实存在，**本包未包含当时实际运行它们的 pytest 总通过数或真实生产认证端到端演示**。 [T07]

---

## 10. Bug Casebook：哪些是真实开发史，哪些只是 Guard Test？

### CASE 13D-A · 早期允许普通题跟随 Transfer Action（有设计文档和代码 Diff 支持的已修复缺口）

**历史依据**：`docs/12` 明确陈述 “Previously ... could persist an ordinary PROBLEM_ATTEMPT item under that Transfer Assessment action”；`e2ef14d` 的 Diff 显示新增 Action–Item Guard，并将其接入 `RecoverableNumericSessionServiceV01`；相应测试验证普通题会被拒绝。 [D12, P01, T01]

**问题→修复→测试**：Student Request 可使 Personalized Decision 选择 Transfer → 发题端未核对真正题目标签 → `require_eligible_assessment_action_v01()` 校验选中动作和保存题目之间的相容性 → 单元测试拒绝普通题、容许结构上符合要求的 Transfer-Tagged Item。**不能因此进一步声称“某位真实学生曾被误判 Transfer Mastery”，因为该资料包没有这样的 Incident Log。**

**后续发现的不足**：Transfer Tag 只是文字/枚举标签，不是 Review Approval。因此 `1e6ca98` 增加 Review Draft，`bbddaf38` 进一步增加 Fail-Closed Gate。这是从“结构检查”走向“可信发题前置条件”的连续工程调整，而不是同一个 Bug 被一行修好的故事。 [D12–D14, P01–P03]

### CASE 13D-B · 初版结构校验仍允许“仅带 Transfer Tag”的题目通过（通过测试确认的设计边界）

`test_transfer_tag_satisfies_only_structural_requirement()` 显式证明结构校验通过并不包含 Design Approval；`docs/13` 也承认 Draft 引入时还没有真正发题审批。随后 `bbddaf38` 的 Diff 新增 Gate 接入和“未获批准不得 Issue”的测试。这属于**可复核的历史设计缺口与增强**，不是资料包能证明的生产数据损坏。 [T01, D13, P03]

### GUARD 13D-01 · 错误 Alignment / 普通题 / 非 Assessment Action

对 `alignment_verified=False`、普通题要求 Transfer、Professor Action 误入 Numeric Assignment、非法 Item 类型分别触发 ValueError/TypeError。测试确保不把用户请求直接当成题目的性质。 [T01]

### GUARD 13D-02 · Review Draft 内容/版本失效

修改 Prompt 或 Rubric、修改 Revision/ID，`require_current_transfer_review_binding_v01()` 拒绝已不匹配的 Draft。测试还检查时区时间和必填文本；仅 Hash 相等不构成审批。 [T02]

### GUARD 13D-03 · 调用者试图传 `approved=True` 绕过 Gate

Gate 无该参数；测试预期 `TypeError`。这不是一次真实攻防事件，而是禁止“调用方声称已批准就可发题”的接口设计。 [T03]

### GUARD 13D-04 · 模拟认证/授权异常

不存在 Provider、Provider 返回 `None` 或错误类型、Issuer 错、身份过期/来自未来、Permission 返回字符串/整数、Provider 抛异常、Draft 已过期，均应拒绝。测试用 Fake Provider，不证明存在真实身份系统。 [T04]

### GUARD 13D-05 · 持久化伪造或错误版本的 Decision

Decision ID 重复、Item Revision 不存在、保存 Item 变更后 Hash 不一致、Draft 不匹配、空理由或无效时间会被测试拒绝；SQLite reopen 会恢复保存的 Claim。Repository 无权授予 Delivery。 [T05]

### GUARD 13D-06 · 历史 Review 顺序冲突

同一最新时间戳有两条 Decision → `AMBIGUOUS`；重复 ID、内容不匹配或未来记录 → `INVALID_HISTORY`；REVOKE 可以成为最新记录，但不会代表有权撤销。 [T06]

### GUARD 13D-07 · Application Writing Path 被伪造或失效

缺身份、权限不允许、Issuer 错、Item Revision 不存在、Draft 失效、Clock 无效或试图直接传 Reviewer ID → 不保存决策；合法的测试替身路径可保存 Claim，并在 reopen 后恢复，但仍打不开 Transfer Gate。 [T07]

### 10.1 本轮绝不能编造的内容

- 没有与这七个 Commit 对应的原始失败 pytest 输出，因此不能声称出现过多少次失败、具体哪个 Fix 是第一次失败、也不能编写不存在的 Traceback。
- 原始 Diff 显示代码和测试如何改变，不等于当时的完整讨论或排障顺序；发生原因的“当时动机”只能引用设计文档陈述，其余标为事后技术解释。
- 不存在实际授权 Reviewer 的真实账户登录、审批签章、可信审批令牌或已启用的 Transfer Delivery 证据；源码反而明确说这些尚未实现。 [M01, D15–D18]

---

## 11. 跨模块执行演算：一条真正能核对的 Transfer Request

以下是**根据所引源码构造的解释性场景**，不是某位真实学生的原始历史日志。

**输入**：学生请求 `REQUEST_TRANSFER`，Decision Engine 返回 `TRANSFER_ASSESSMENT`；当前 Item 是 `PROBLEM_ATTEMPT`。

```text
run_turn() → selected_action = TRANSFER_ASSESSMENT
      ↓ require_eligible_assessment_action_v01
item.evidence_type = PROBLEM_ATTEMPT
      ↓ ValueError
没有 AssessmentDeliveryV01
没有调用 issue_assignment()
```

把题目标签改成 `TRANSFER_ATTEMPT`，并不解决问题：

```text
Action–Item Guard：通过（仅结构意义）
      ↓ require_trusted_transfer_delivery_v01
      ↓ ValueError：No trusted approval source
仍不会创建并持久化这道 Transfer Assignment
```

再构造一份绑定 Item Revision 的 Draft，使用**测试专用** Identity/Permission Provider 产生 APPROVE Decision：

```text
Review Application → saved APPROVE Claim
Review Lifecycle → APPROVE_RECORDED
Recoverable Session → Transfer Delivery Gate
      ↓ 仍 ValueError
```

即使今后新增可信批准和发题链路，还必须另行处理：Numeric Scorer 对 Transfer Tag 的当前限制、题目测量迁移的实质审查、Attempt Assistance/先前答案暴露的真实来源，以及 State Estimator 对 Transfer Evidence 的资格判断。**这四项都不能通过简单打开发题 Gate 自动获得。** [S01, S03, S08–S11]

---

## 12. 架构决策记录（ADR）

### ADR-13D-01 · 决策与内容资格独立

- **Context**：学生可以请求 Transfer，但请求不会改变存储题目的 Rubric/Evidence Type。
- **Decision**：增加独立的 Action–Item Eligibility Guard，并放在 Assignment Issue 前。
- **收益**：防止普通题因教学动作被错误重新归类。
- **代价/限制**：Gate 只做结构检查，不能断言测量效度；教学 Agent 可能早于 Gate 执行。
- **历史依据**：[S01, S08, D12, P01]。

### ADR-13D-02 · Draft 与 Item 内容和 Revision 绑定

- **Context**：审核的对象可能在审核过程中或审核后变化。
- **Decision**：保存完整 Item 的序列化 Fingerprint、Item ID/Revision/Course/Objective，并在 Review 流程中重新核对。
- **收益**：可以发现当前 Item 内容和 Draft 快照不一致。
- **代价/限制**：SHA-256 不验证来源或审核者权限；Draft 创建阶段的 Revision 本身由调用者提供。
- **历史依据**：[S02, D13]。

### ADR-13D-03 · 在没有可信审批源时保持 Fail Closed

- **Context**：结构标签和 Draft 仍可能由调用者生成。
- **Decision**：`TRANSFER_ASSESSMENT` 一律拒绝，且无 `approved=True` 绕过入口。
- **收益**：阻止这条 Session Path 在审批机制缺失时误发 Transfer Assignment。
- **代价/限制**：有合法教学需要的 Transfer 请求也暂时不能通过该路径完成；不是全系统 Legacy Path 审计。
- **历史依据**：[S03, D14, T03]。

### ADR-13D-04 · Review History 与当前发题授权解耦

- **Context**：数据库可以保存历史 Claim，但其来源、撤销和当前有效性尚无可信证明。
- **Decision**：Repository 只提供 Save/Load/List；Lifecycle 只提供 `*_RECORDED` 描述状态；Application 只写入历史 Claim；Delivery Gate 不接这些输出。
- **收益**：避免把新开发的原型审核功能错误提升为生产安全控制。
- **代价/限制**：真实授权、时钟/事务一致性、生产 Migration 和独立的 Transfer Scoring 仍是后续工作。
- **历史依据**：[S03–S11, D15–D18]。

---

## 13. 如何以后复核、扩展与维护这章

本章的所有源码引用都给出完整模块路径；`evidence/reply8_chapter_source_index.json` 包含七个完整 Commit Hash、ZIP 内部源文件位置、文件 SHA-256 以及下表别名。先看 History Snapshot，确定功能在何时出现；再看对应 Diff，确定新增/修改了哪几行；最后看当时测试，确认被检查的是哪个行为。**不要先读最新版本再把它的行为倒写成早期版本。**

| 来源编号 | 位置（历史包内部） | 可支持的陈述 |
|---|---|---|
| M01 | `SOURCE_MANIFEST.json` | 七个历史节点、文件来源、Hash 和版本边界 |
| P01–P07 | `diffs/*.patch`，按历史节点标号 | 某次 Commit 的真实增量 |
| S01 | `final_snapshot/backend/app/services/decision/assessment_action_eligibility_v01.py` | 结构校验与错误文本 |
| S02 | `final_snapshot/backend/app/services/assessment/transfer_design_review_v01.py` | Draft 字段、Item Hash、绑定校验 |
| S03 | `final_snapshot/backend/app/services/decision/transfer_delivery_gate_v01.py` | 无条件拒绝 Transfer |
| S04 | `final_snapshot/backend/app/services/assessment/transfer_reviewer_authorization_v01.py` | Provider 接口、身份有效期、权限检查 |
| S05 | `final_snapshot/backend/app/services/assessment/transfer_review_decision_v01.py` | Decision 合同、Draft Hash、REVOKE 后加 |
| S06 | `history/review_decision_persistence_8c83c51ae6/.../transfer_review_decision_v01.py` | 初版 Decision Enum（不含 REVOKE） |
| S07 | `final_snapshot/backend/app/repositories/transfer_review_decisions_v01.py` | 数据库存储与来源限制 |
| S08 | `final_snapshot/backend/app/services/decision/recoverable_numeric_session_v01.py` | Agent、两道 Gate、Issue Assignment 的先后顺序 |
| S09 | `final_snapshot/backend/app/services/assessment/numeric_scoring_v02.py` | Numeric Scorer 对 Transfer Tag 的现有限制 |
| S10 | `final_snapshot/backend/app/services/assessment/transfer_review_lifecycle_v01.py` | `*_RECORDED`、冲突和无效历史 |
| S11 | `final_snapshot/backend/app/services/assessment/transfer_review_application_v01.py` | Review 写入调用链及非原子性 |
| D12–D18 | `history/` 对应各阶段的 `docs/12...` 至 `docs/18...` | 每个阶段当时明示的目的、Non-Goals 与限制 |
| T01–T07 | `history/` 与 `final_snapshot/backend/tests/` 中相应测试 | 防护场景（不自动证明真实故障） |

### 13.1 本章没有改变任何生产行为

本章是根据上传的历史资料制作的工程文档。生成 HTML / Markdown 和安装到 `engineering-archive/` 都不修改 URPP 的 Backend、SQLite、Git Branch、Evidence Eligibility 或 Transfer Delivery Gate。

**结尾判断（严格限定当前历史节点）**：13D 系列完成了“普通题不能冒充 Transfer、未配置可信审批源时拒绝该 Session Path 发题、内部 Review Claim 可被记录与检查”的原型边界；**没有完成“真实授权 Reviewer 批准后可发放 Transfer Assessment”，也没有据此证明学生发生 Transfer Learning。**
