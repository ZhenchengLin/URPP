# URPP Engineering Archive · Reply 4 / 10
## Design 01C：从 Student Response 到有条件的 Learning Evidence

**档案类型：** 历史源码解读 + 测试合同分析 + 明确标注的事后工程推论。  
**来源范围：** 用户上传的 `assessment_history_source_pack.zip`，包含八个 Git 节点的 16 份历史源码/测试/设计文件及 `SOURCE_MANIFEST.json`。  
**重要限制：** 本包只有各节点选定的新增/修改文件，不包含每个节点所有依赖的历史版本，也没有原始失败的 pytest 输出、讨论记录或部署日志。因此本章不得声称“某个 Bug 曾经真实触发”，除非另有原始失败记录。  
**编号说明：** 文件中使用 `Design 01C` / `V0.2`；它们不等于尚未恢复的完整 Implementation 0–13 Roadmap 编号。

> **一条主线：** Assessment Item 预先定义题目与 Rubric → Student Attempt 保存原始作答和已知条件 → Scoring 生成 EvidenceEvent → Eligibility / State Estimator 决定如何使用该 Evidence。开放题中间还必须经过 Structured Review → Preview → 经外部授权后签发 Approval → 验签 Finalization。引入 Repository 后，Attempt 必须绑定其原始 Item Revision，不能拿新 Rubric 重算旧答案。

---

## 1. 证据目录：八个真实历史节点

| 节点前缀 | 本包可见的文件 | 能从源码直接确认的工作 | 不应据此推断的事 |
|---|---|---|---|
| `4edec7f` | `models_v02.py`, `numeric_scoring_v02.py`, `test_numeric_scoring_v02.py` | 建立数值 Assessment Contract、确定性评分和与 State Engine 的测试连接 | 客户端认证、真实学生的独立作答证明 |
| `0bfa364` | `open_response_models_v02.py`, 对应测试 | 建立开放题 Rubric、CriterionReview、Review 结构 | 开放题已经自动评分或 Review 已可信 |
| `e6ac6e7` | `open_response_scoring_v02.py`, 对应测试 | Review 一致性验证与分数 Preview | Preview 可以直接写入掌握证据 |
| `55bd26b` | `review_approval_v02.py`, 对应测试 | 将 Review 和来源绑定到 HMAC-SHA256 Approval；验签后生成 Evidence | HMAC 自己能认证人、能证明 Review 的数学判断正确 |
| `1374ed1` | `assessment_pipeline_v02.py`, 对应测试 | 内部入口将 Numeric / 已批准开放题转为 Evidence，再交给 State Estimator | 这是 HTTP API 或完整生产信任边界 |
| `3424920` | `docs/03c_assessment_records_and_authorization.md` | 记录权威题目、身份授权、数据库和评分版本计划 | PostgreSQL、Alembic、API 授权已经部署 |
| `1b8dfdb` | `assessment_records_v02.py`, 对应测试 | SQLAlchemy 持久化 Item Revision 与 Attempt 的版本绑定 | 数据库内容具有防篡改签名或已完成身份授权 |
| `aadd8e3` | `persisted_numeric_pipeline_v02.py`, 对应测试 | 从 Repository 加载原始题目版本并走现有评分/状态链路 | 这个服务支持开放题持久化评分或验证独立性 |

**如何核对：** 打开本地 `engineering-archive/evidence/assessment_history_source_pack.zip`；ZIP 内的路径由 `commit-prefix/backend/...` 或 `commit-prefix/docs/...` 组成。本文在段落末使用 `〔commit / file:行号〕` 标注原始版本位置。测试函数名可以在同一节点的 `backend/tests/test_*.py` 中查到。当前网页不需要联网。

### 1.1 为什么这个发展顺序重要？

最初的 Student State 设计要求“有证据才更新状态”，但还必须回答证据究竟来自哪里。这个阶段将“用户说自己答了 5”拆成四种不同对象：题目及既定标准（Item/Rubric）、学生提交的文本与作答条件（Attempt）、评分后的观测记录（EvidenceEvent）、针对一组证据估计的 Objective State。**四者数据关联，并不互相替代。**

一个 `EvidenceEvent` 可以报告 `correctness=1.0`，但并不意味着独立完成、充分练习或已掌握。一次有效评分只回答“该回答在所用 Rubric 下如何得分”；能否进入掌握估计、能否满足 Independent Success Gate，是后续规则的责任。

---

## 2. Numeric Assessment Contract：如何定义题目与原始作答

### 2.1 `NumericRubricV02`

Rubric 是评分依据，包含 `expected_value: float`、非负 `absolute_tolerance` 和非空 `rubric_version`。`expected_value` 与 `absolute_tolerance` 必须是有限值，拒绝 `NaN` 和正负无穷。模型被冻结，且 `extra="forbid"`，减少在创建 Rubric 时偷偷附加未知字段的可能。Rubric 这里是**绝对误差**条件，不是相对误差或有效数字判断。〔`4edec7f / models_v02.py:24–55`〕

```python
is_correct = (
    abs(answer - item.rubric.expected_value)
    <= item.rubric.absolute_tolerance
)
```

例如 `expected_value=1.0`、`absolute_tolerance=0.02`、回答 `1.01` 将通过。`0.02` 是题目自身的容差；不是 Student Mastery 的不确定性。关于极端有限浮点值的减法溢出、不同学科对有效数字的要求，属于**后续工程边界**，本包不证明历史上发生了相关故障。

### 2.2 `AssessmentItemV02`

Item 包含 `assessment_item_id`、`course_id`、`objective_id`、题干 `prompt`、`evidence_type`、`rubric` 与 `alignment_verified`。只支持三种 Performance Evidence 类型作为 Item 合法枚举：`PROBLEM_ATTEMPT`、`TRANSFER_ATTEMPT`、`RETRIEVAL_ATTEMPT`。然而**本节点的 Numeric Scoring 函数只允许 `PROBLEM_ATTEMPT`**；数据结构允许声明一种类型，不表示对应的评分与评估政策已实现。〔`4edec7f / models_v02.py:58–102`；`numeric_scoring_v02.py:73–82`〕

`alignment_verified` 默认 `False`。代码注释指出，匹配 `objective_id` 本身不足以证明题目真的测到了该 Learning Objective；评分前必须有外部机制确认这一关系。这个字段的存在不等于认证机制已实现。本阶段 `score_numeric_attempt` 只检查它是否为真，不核验谁设置了它。

### 2.3 `StudentAttemptV02`

Attempt 原样保存 `response_text`，还保存 `attempt_id`、学生/课程/会话/目标/题目作用域、`source_message_id`、`response_group_id` 和带时区的 `submitted_at`。作答条件单独保留为 `assistance_level: int | None`（允许 0–6 或未知）、`prior_solution_exposure: bool | None` 和 `novelty: repeated | similar | novel | unknown`。**不能从答对推导为 `assistance_level=0`，也不能从没有 App Hint 日志推断未用外部帮助。** 〔`4edec7f / models_v02.py:104–158`〕

测试 `make_attempt()` 会明确人工构造 `assistance_level=0`、`prior_solution_exposure=False`、`novelty="novel"`。这只是**受控测试 Fixture 的输入**，不是生产系统已经验证独立性。若未来把 Fixture 中的这些字段拿来证明真实学生活动，便混淆了测试假设与观察事实。〔`4edec7f / test_numeric_scoring_v02.py:49–73`〕

### 2.4 三种不同的“不知道”

| 层级 | 例子 | 正确处理 |
|---|---|---|
| 格式未知 | `response_text="I need another explanation"` | Numeric Parser 返回 `None`，本次自动数值评分记为中立/无效；不能改写成数学回答错误 |
| 作答条件未知 | 回答 `5`，`assistance_level=None` | 数值评分可以算出 1.0，但仍原样保留 `None`，后续 Eligibility 独立判断 |
| 掌握证据不足 | 一道满足条件的新题答对 | State Estimator 仍可能返回 `UNKNOWN`，表示证据量/门槛不足，而非判断学生不会 |

这三个层次发生在不同的函数。**不要为消除一个 `UNKNOWN`，就在上游随意补出“没有帮助”或“已掌握”。**

---

## 3. Numeric Scoring：确定性、解析规则与证据生成

### 3.1 `parse_numeric_answer()` 是受限 Parser，不是计算器

源码先 `strip()`，拒绝空串和长度超过 64 的字符串，再用 `NUMERIC_PATTERN.fullmatch(text)` 要求**整个答案**必须是一枚十进制数，可选符号、小数部分和 `e/E` 科学计数法。`float()` 转换后，还必须 `math.isfinite(value)`。整个过程不执行用户输入，不使用 `eval()`。〔`4edec7f / numeric_scoring_v02.py:23–50`〕

被测试接受的格式：`5`、`5.0`、`.5`、`-2.5`、`+5`、`5e0`、`1.25E+2`。被测试拒绝的格式：空串、自然语言、`2+3`、`5 meters`、`5,000`、`nan`、`inf`、`1e309`、`5 5`。这意味着 `2+3` 虽然在数学上能得到 5，却不符合**此题的单个数值输入协议**；它不是“3 分”或“答错了”，而是自动评分不可用。〔`4edec7f / test_numeric_scoring_v02.py:77–112`〕

**教学上的后果：** 用户输入 `2+3` 可能是表达式，输入 `5 meters` 可能涉及单位题；未来若要支持表达式与单位，需要单独的 Parser/Score Policy，不应悄悄扩大当前 `numeric-scoring-v0.2` 的含义。

### 3.2 `score_numeric_attempt()` 的真实调用顺序

```text
AssessmentItemV02 + StudentAttemptV02
  → 核对 course_id / objective_id / assessment_item_id
  → 检查 alignment_verified=True
  → 只接收 ordinary PROBLEM_ATTEMPT
  → 调用 parse_numeric_answer(response_text)
  ├─ 不能解析：neutral + correctness=None + assessment_validity=invalid + confidence=0
  └─ 可以解析：比较绝对误差 → success/1.0 或 failure/0.0
  → 构造 EvidenceEventV02，继承 Attempt 的帮助/先前看答案/新颖性字段
```

**为什么先比对三个 ID？** 如果题目是课程 A 的加法，而 Attempt 声称属于课程 B 或另一个 Learning Objective，就不能仅凭数值恰好为 5 而产生该目标的 Evidence。源码在范围不符时抛出 `ValueError`，不是自动修正目标。〔`4edec7f / numeric_scoring_v02.py:53–82`〕

**为什么 `model_confidence=1.0`？** 在这个受限 Numeric Parser 中，该值说明提交文本可以被明确解析为一个有限数字，**不是学生已经掌握该技能的概率**。原始代码注释明确提醒了这一点。对于无法解析的文本，则为 0.0。〔`4edec7f / numeric_scoring_v02.py:84–115`〕

**哪些字段没有被评分函数“升级”？** `assistance_level`、`prior_solution_exposure`、`novelty` 直接复制 Attempt；`created_at` 使用 Attempt 的 `submitted_at`；`scoring_policy_version` 固定为 `numeric-scoring-v0.2`。`evidence_id` 采用 `numeric-v02:{attempt_id}`，用于建立稳定关联，不意味着此处已经进行了持久化唯一性或调用权限验证。〔`4edec7f / numeric_scoring_v02.py:116–138`〕

### 3.3 从一条正确答案到 Objective State

历史测试使用受控 Fixture 构造一条正确数值 Evidence，调用 `estimate_objective_state()` 后断言：该 Evidence 被纳入，`performance_estimate=1.0`，但 `state="unknown"`。第二个测试构造**两个不同 Item 的独立正确回答**，断言 `distinct_assessment_count=2`、`independent_success_count=2`、`state="competent"`。这是测试条件下的规则表现；不代表真实学生无需更多检查就能被认证为掌握。〔`4edec7f / test_numeric_scoring_v02.py:194–237`〕

完整资格规则属于 State Estimator/Eligibility 的历史版本，本资料包没有把那些依赖源码再次完整收录。本章不会从一组测试倒推出未提供的全部 State Gate 常数。

---

## 4. Open Response：为什么“评分 Preview”不能直接成为 Evidence

### 4.1 结构化 Rubric 与 Review

Numeric Scoring 有有限数字和可执行容差；开放题的数学证明、概念解释却没有天然的单值比较。该节点因此采用 Criterion-Based Rubric：每项 Criterion 有唯一 ID、可观察的描述、Full-Credit Guidance 与权重，所有权重总和必须接近 1（源码 `isclose(..., abs_tol=1e-9)`；`rel_tol` 未被设置为零，见源码与后续边界）。Rubric 版本非空，Criterion 权重为 `(0,1]` 且有限。〔`0bfa364 / open_response_models_v02.py:24–67`〕

开放题 Item 默认 `SELF_EXPLANATION`，还允许 `DEFINITION_RECALL`、`PROBLEM_ATTEMPT`。若 `alignment_verified=True`，要求非空 `alignment_reviewer_id`；**这只是字段一致性验证，并非认证 reviewer 身份**。〔`0bfa364 / open_response_models_v02.py:69–107`〕

`CriterionReviewV02` 对每条 Criterion 使用 `met`、`partial`、`not_met`、`unscorable` 四种判断。当给予 `met` 或 `partial` 时，结构校验要求提供 `supporting_quote`；`not_met` 无需引用。`OpenResponseReviewV02` 记录 Review/Attempt/Item/Rubric/Reviewer 的 ID、Criterion 列表与带时区的 Reviewed Time。来源文件直接说明：此模型**不自动评分**，Quote 此阶段也尚未对照学生原文验证。〔`0bfa364 / open_response_models_v02.py:110–177`〕

### 4.2 Preview 的逐项验证

`preview_open_response_review(item, attempt, review)` 依次检查：Item 与 Attempt 的 Course/Objective/Item ID 相符；Review 指向同一 Attempt 与 Item；Rubric Version 相符；`reviewed_at >= submitted_at`；题目已标为 Alignment Verified；Review 不存在重复 Criterion ID 且恰好覆盖 Rubric 中每一项。给予正分的 Quote 必须**以字面子串形式**出现在 `attempt.response_text` 中。〔`e6ac6e7 / open_response_scoring_v02.py:42–116`〕

这项 Quote 检查证明的是**文本出现过**，不证明引用能支持 Review 的数学判断。例如引用包含一个正确术语，Reviewer 仍可能给出错误的 `met`；该函数不能代替语义判断或独立复核。源码开头明确写明：它不认证 Reviewer 的身份与语义判断，输出不应视为 Mastery Evidence。〔`e6ac6e7 / open_response_scoring_v02.py:1–9, 42–52`〕

### 4.3 分数的精确算法

```python
scores = {"met": 1.0, "partial": 0.5, "not_met": 0.0}
total += rubric_criteria[result.criterion_id].weight * scores[result.judgment]
```

测试的 Dot Product 题包含 `definition`（权重 0.6，`met`）和 `geometry`（权重 0.4，`partial`）。Preview 得分：`0.6×1 + 0.4×0.5 = 0.8`，因此 `outcome="partial"`、`status="requires_reviewer_confirmation"`。该分数仍不等于已批准 Evidence；`partial` 也不是“学生掌握 80% 的知识”的统计结论。〔`e6ac6e7 / open_response_scoring_v02.py:102–159`；`test_open_response_scoring_v02.py:117–127`〕

如果**任意一项** `unscorable`，函数返回 `outcome="neutral"`、`correctness=None`、`status="requires_additional_review"`，而不是把那一项当 0 分，也不会擅自对剩余 Criterion 重新归一化。这保存了**缺少评分依据**与**明确未满足标准**之间的区别。〔`e6ac6e7 / open_response_scoring_v02.py:108–140`〕

### 4.4 状态不是一串可以省略的“批准”字眼

```text
学生回答
  → Structured Review（内容可能有误，身份可能未认证）
  → Preview（检查记录一致性/字面引用/计算加权分）
  → requires_reviewer_confirmation
  → 外部可信服务认证并授权 Reviewer【本模块不实现】
  → issue_review_approval()（绑定来源并签名）
  → finalize_approved_review()（完整来源验签）
  → EvidenceEventV02
  → 下游 Eligibility / Student State
```

任何将 `Preview` 直接送入 State Estimator 的捷径，都绕过了此历史设计中的 Review Approval 边界。不能通过“让 LLM 在文本里写 approved”来替代签名与权限检查。

---

## 5. HMAC Approval：保证什么，不能保证什么？

### 5.1 Approval 消息绑定的确切内容

`_approval_message()` 将 Item、Attempt、Review 的完整 `model_dump(mode="json")`，连同 `approved_by`、`approved_at`、`scoring_confidence` 和 `approval_policy_version` 整合成排序、紧凑 JSON 字节。`_sign()` 使用 `hmac.new(key, message, hashlib.sha256).hexdigest()`；Key 必须是至少 32 字节。Approval Model 要求 64 字符小写十六进制签名以及带时区的审批时间。〔`55bd26b / review_approval_v02.py:44–126`〕

**工程含义：** 事后改动答案、Criterion Review、Rubric/Prompt 或审批字段，将改变签名消息；在相同 Key 下通常无法通过验签。测试确实覆盖伪造签名、改变学生答案、改变 Review 和改变 Item Prompt。〔`55bd26b / test_review_approval_v02.py:172–236, 282–302`〕

### 5.2 颁发审批前的检查

`issue_review_approval()` 首先重新计算 Preview；若 `requires_additional_review`，拒绝签发。随后检查调用者**传入的** `authenticated_reviewer_id` 与 `review.reviewer_id` 相同、审批时间不能早于 Review、字段合法，再对消息签名。〔`55bd26b / review_approval_v02.py:128–194`〕

**不能误读：** 参数叫 `authenticated_reviewer_id` 并不使它自动可信。函数没有 Login、Role Check 或 Course Authorization。源码注明调用该函数的后端服务**必须先认证和授权** Reviewer。没有这一上游边界，任意具有 Signing Key 的调用方仍可能为自己构造的 Review 签名。签名证明的是“持有 Key 的实体对这些字节作了认证”，不是“真实的授权教师认可了此数学判断”。

### 5.3 Finalization 的独立验证

`finalize_approved_review()` 再次生成 Preview，校验 Review/Approval ID 与审批时间，重新构造签名消息，然后使用 `hmac.compare_digest()` 比较签名；验证失败抛错，成功才构造 Evidence。Evidence 复制 Attempt 的 assistance/exposure/novelty，不会自行提升独立性。`created_at=approval.approved_at`，**不是原始提交时间**；源码明确留言：以后的 Schema 应区分原始作答时间与 Approval/Recording 时间。〔`55bd26b / review_approval_v02.py:197–280`〕

Reviewer 指定的 `scoring_confidence` 被带入 Evidence 的 `model_confidence`，该数值不是经过标定的 Mastery Probability。测试中较低的 Review Confidence 不会自动建立 Student State。〔`55bd26b / review_approval_v02.py:59–65, 273–279`；`test_review_approval_v02.py:304–...`〕

### 5.4 四种不同的 Trust Claim

| Claim | 本阶段能否支持 | 理由 |
|---|---|---|
| Item/Attempt/Review 的签名绑定完整 | **条件性支持**：需可信 Key 和正确调用链 | `HMAC-SHA256` 覆盖完整序列化来源 |
| Reviewer 是已授权课程教师 | **不能由此模块证明** | 认证与权限由外部服务提供，本包未给出实现 |
| Review 数学判断正确 | **不能证明** | Quote 子串与签名都不验证数学语义 |
| 学生作答真正独立 | **不能证明** | `assistance_level` 原样复制，不是签名自动推得 |

---

## 6. Assessment Pipeline：为什么只接收 Assessment Submission？

`AssessmentPipelineV02` 是**内部应用服务**，不是 HTTP Endpoint。其输入是 `NumericSubmissionV02(item, attempt)` 或 `ApprovedOpenResponseSubmissionV02(item, attempt, review, approval)`；构造时可提供至少 32 字节的 `verification_key`。〔`1374ed1 / assessment_pipeline_v02.py:1–68`〕

执行时：Numeric 分支调用 `score_numeric_attempt`；开放题分支要求 Verification Key 后调用 `finalize_approved_review`；其他类型抛出 `TypeError`；收集生成的 Evidence 后调用 `estimate_objective_state()`，返回 `ObjectiveStateV02`。〔`1374ed1 / assessment_pipeline_v02.py:69–140`〕

```text
NumericSubmission ──── score_numeric_attempt ───────┐
                                                     ├─ EvidenceEvent[] → estimate_objective_state → ObjectiveState
ApprovedOpenResponse ── HMAC verification + finalize ┘
```

此入口**不接受调用者预先构造的 `EvidenceEventV02`**。这是为了避免在这个入口把任意伪造 Evidence 当成评分结果；不过源码同时坦承：底层 State Update Engine 可以被其他代码独立调用，这一限制只覆盖 `AssessmentPipelineV02` 的入口，不能把它误说成全局权限机制。〔`1374ed1 / assessment_pipeline_v02.py:46–55`〕

更重要的是：这个 Pipeline 对它收到的 Numeric Item 和 Attempt 假设调用方提供的是权威记录；**它本身不负责认证调用者，也不负责从可信存储读取这些对象**。因此从“内部原型”到“生产应用”之间仍存在权限、数据来源和持久化边界。测试覆盖缺少 Verification Key、错误 Key、预构造 Evidence 被拒、跨学生范围被拒等合同；它们是**预防性测试**，本包无原始现场入侵或失败事故记录。〔`1374ed1 / test_assessment_pipeline_v02.py:172–238`〕

---

## 7. Design 01C 文档：哪些只是计划？

`3424920/docs/03c_assessment_records_and_authorization.md` 明确提出：未来生产数据库 PostgreSQL，SQLAlchemy 操作、Alembic Migration、psycopg Driver；本地 Repository Test 可以采用 SQLite。它还规定学生身份来自已认证的后端上下文、Rubric Revision 不得覆盖、Reviewer 的签名 Key 留在服务器、审批及撤销应当可审计，并要求处理 Numeric 与 Open-Response 不同的 `scoring_policy_version` 混合问题。〔`3424920 / docs/03c_assessment_records_and_authorization.md:1–89`〕

**历史准确性：** 文档的 “Technical direction” / “Implementation order” 不等于已经部署 PostgreSQL、完成迁移、注册真实 Reviewer、完成 Audit/Revocation 或公开 Assessment HTTP API。本包的后续 Repository 是 SQLAlchemy 内部 Prototype，测试 Fixture 使用 SQLite 内存库。此差别在网站必须持续保留。

### 7.1 不同 Scoring Policy 不可默默混算

Numeric Evidence 的 `scoring_policy_version="numeric-scoring-v0.2"`；签名开放题的 Version 是 `open-response-approval-v0.2`。Design 01C 文档明确要求混合版本聚合在部署前有显式兼容政策。仅因为两者都把 `correctness` 放进 0–1 区间，就假设可直接比较，不符合该阶段记录的边界。〔`4edec7f / numeric_scoring_v02.py:23`；`55bd26b / review_approval_v02.py:44, 273–279`；`3424920 / docs/03c_assessment_records_and_authorization.md:59–72`〕

---

## 8. Versioned Repository：为什么旧答案必须用旧 Rubric？

### 8.1 数据表结构

```text
assessment_items_v02
  primary key = (assessment_item_id, revision)
  item_type = numeric | open_response
  payload = versioned Item JSON

student_attempts_v02
  primary key = attempt_id
  foreign key = (assessment_item_id, item_revision)
                → assessment_items_v02 同一复合键
  payload = original Attempt JSON
```

`AssessmentRecordRepositoryV02` 接收外部 `session_factory`，使用 SQLAlchemy。`save_item()` 要求 Revision 是**真正的正整数**，拒绝布尔值；已存在的 `(item_id, revision)` 不允许覆盖。`load_item()` 根据行内 `item_type` 恢复正确的 Pydantic Model。〔`1b8dfdb / assessment_records_v02.py:1–200`〕

`save_attempt(attempt, item_revision)` 先加载该 Revision，检查课程/目标/题目身份，拒绝重复 `attempt_id`，再把 Attempt JSON 与 `item_revision` 存入同一行；`load_attempt(attempt_id)` 返回 `(StudentAttemptV02, int)`。注意 `item_revision` 是单独的可信关联字段，并不依赖学生随意提交“最新版本”。〔`1b8dfdb / assessment_records_v02.py:202–271`〕

### 8.2 原始 Rubric 版本的精确示例

```text
T0: Item A / revision 1 / expected_value=5
T1: Attempt X / answer="5" / item_revision=1 → 保存
T2: Item A / revision 2 / expected_value=7 → 新增，不覆盖 rev1
T3: 恢复 Attempt X → 从数据库读到 revision=1 → 用 expected=5 评分 → 正确
```

如果 T3 错误地读取最新 rev2，同一份历史回答 `5` 会被重新评价为错误，属于**历史评分标准漂移**。历史测试分别断言旧 Attempt 继续使用旧 Rubric、新 Attempt 按 rev2 得分；还检查重复 Item Revision 与重复 Attempt ID 被拒。这里是**测试防范的错误情境**，不是本包有证据证明曾发生的真实生产 Bug。〔`1b8dfdb / test_assessment_records_v02.py:93–201`；`aadd8e3 / test_persisted_numeric_pipeline_v02.py:138–184`〕

### 8.3 “不可覆盖”的准确范围

这些 Repository 方法拒绝 API 层重复写入原有 Revision / Attempt ID；底层 JSON 表并没有在本包中被证明拥有数据库级不可篡改存储、完整的迁移链、角色授权或审计日志。**API 的一次写入限制不等于整个存储永久不可更改。** Foreign Key 也需在目标数据库连接配置下正确启用才能依赖数据库层强制检查。

---

## 9. Persisted Numeric Pipeline：将真实历史记录接到现有评分链

`PersistedNumericAssessmentServiceV02(repository)` 的入口是 `estimate_from_attempt_ids(attempt_ids, student_id, course_id, objective_id, as_of)`。它拒绝单个字符串误当 ID 序列、空列表、空白 ID 与重复 Attempt ID。对每个 ID 先调用 `load_attempt()`，检查 Student/Course/Objective Scope，然后使用该 Attempt 存储的 `item_revision` 精确加载 Item；只有 Numeric Item 可以构造 `NumericSubmissionV02`。最终复用 `AssessmentPipelineV02` 进行评分与状态估计。〔`aadd8e3 / persisted_numeric_pipeline_v02.py:31–130`〕

```text
Attempt ID 列表
  → Repository.load_attempt(id) → (Attempt, item_revision)
  → 检查 requested student/course/objective
  → Repository.load_item(assessment_item_id, revision=item_revision)
  → 要求 Numeric AssessmentItem
  → NumericSubmission(item, attempt)
  → AssessmentPipeline.score_numeric_attempt
  → Evidence Eligibility / estimate_objective_state
```

这里的 `student_id` 来自函数参数。函数注释明确声明：未来 API 必须从已认证和授权的服务端上下文确定学生身份和读取权限。当前的 Scope Equality Check 防止把一个 Attempt **误用于另一个请求的 Student State**，但**不是认证**。〔`aadd8e3 / persisted_numeric_pipeline_v02.py:8–12, 47–61, 92–104`〕

### 9.1 回归合同：从 SQLite 中恢复原始评分上下文

在历史测试中，每项测试使用隔离的内存 SQLite，先 `Base.metadata.create_all(engine)`，再建立 Repository，保存 Item/Attempt 后调用该 Service。该节点测试覆盖：一条正确历史 Attempt 进入状态估计、Rubric 更新不改变旧作答成绩、新 Attempt 使用新 Revision、两个符合 Fixture 条件的新题正确作答支持 `competent`、未知 ID/空/重复 ID 被拒、跨学生 Scope 被拒、Open-Response Item 不会被 Numeric Pipeline 悄悄评分。〔`aadd8e3 / test_persisted_numeric_pipeline_v02.py:1–...`，各函数见测试文件〕

**为什么重复 ID 要拒绝，而非默默去重？** 如果输入是一张本应包含两个不同证据的列表，却重复同一 Attempt，静默去重会掩盖调用端的数据错误；按该服务的合同，输入本身应被纠正。要区分这与 State Estimator 可能有的 Evidence Deduplication：两者发生在不同层级，不应相互代替。

---

## 10. Engineering Casebook：真实问题、受控失败与防范合同

**证据状态声明：** 本次 ZIP 内没有原始失败的 pytest 控制台输出，也没有逐轮 Debugging 聊天，因此下面不是“当时真实发生过的八个 Bug”。这些是由代码和测试直接证实的**失效情境、防护逻辑及验证合同**。网站单列为 `GUARD-01C-*`，将来若找到当时真实失败日志，再添加具有时间线的 `BUG-*` 案例。

| ID / 类型 | 若缺少该保护，可能发生什么 | 源码中实际防护 | 对应可见测试 |
|---|---|---|---|
| `GUARD-01C-01` 输入解析 | `eval('2+3')` 执行表达式、单位/无穷值被错误当作数字 | Regex Fullmatch、最长 64、Finite Float、无 eval；不能解析→neutral/invalid | `test_valid_numeric_formats`, `test_invalid_numeric_formats`, `test_unparseable_response_is_not_automatically_incorrect` |
| `GUARD-01C-02` 错目标/错类型 | 课程或题目不相符仍记入某目标；Transfer 被普通题评分 | 检查 Course/Objective/Item、Alignment、仅普通 Problem | `test_mismatched_assessment_identity_is_rejected`, `test_unverified_alignment_is_rejected`, `test_transfer_assessment_is_not_silently_supported` |
| `GUARD-01C-03` Rubric 失真 | Review 漏项、重复项、错误版本或虚构引用仍计入分数 | Version/ID/全集校验，正分 Quote 必须出现在原文 | `test_review_must_cover_every_criterion`, `test_duplicate_criterion_reviews_are_rejected`, `test_quote_must_occur_in_student_response` |
| `GUARD-01C-04` 无法评分≠零分 | 某 Criterion 未能判分，被算作 `not_met` | 任意 `unscorable`→requires_additional_review，不加权继续结算 | `test_unscorable_criterion_requires_additional_review`, `test_unscorable_review_cannot_be_approved` |
| `GUARD-01C-05` Approval 篡改 | 审核后有人改变答案、Rubric 或 Review，却复用旧批准 | 全来源 HMAC 绑定与重验签 | `test_forged_signature_is_rejected`, `test_modifying_student_response_invalidates_approval`, `test_approval_is_bound_to_rubric` |
| `GUARD-01C-06` Evidence 注入 | 调用方绕过 Scoring/Approval 直接塞入预构造 Evidence | Pipeline 入口只识别两种 Submission Contract | `test_preconstructed_evidence_cannot_enter_pipeline`（只保护这一入口） |
| `GUARD-01C-07` 历史改卷 | 修改题目 Rubric 后用新标准重算旧 Attempt | `(assessment_item_id, revision)` 复合版本键 + Attempt 绑定 | `test_new_revision_preserves_old_rubric`, `test_historical_attempt_uses_original_rubric` |
| `GUARD-01C-08` 错人/重复/错题型 | 跨学生取证、重复 ID、开放题进入数值评分 | Scope Check、拒重复、Numeric Type Check | `test_attempt_cannot_be_used_for_another_student`, `test_duplicate_attempt_ids_are_rejected`, `test_open_response_item_is_not_silently_scored` |

### 10.1 这类调查应该怎样记录为真正 Debugging？

只有拿到对应的原始失败现场后，才填写：① 运行命令与 Commit；② 精确异常及发生位置；③ 最初假设与反例；④ 被检查的对象与时间；⑤ 修改前后的源码 Diff；⑥ 失败的中间方案；⑦ 新增 Regression Test；⑧ 测试实际输出与最终 Commit。**测试名只能证明代码中规定了某个期望，不能证明历史上曾发生相应事故，也不能证明本次聊天重新执行过所有测试。**

### 10.2 源码包里可以直接观察的设计债

以下均为**事后分析/待核实风险**，不是历史 Bug 记录：

1. **真实 Authorization 缺失：** Review 签名函数相信上游输入的 Reviewer ID；Persisted Service 的 Student ID 同样是函数参数。需后端可信入口保证身份与数据权限。
2. **Alignment 权威来源尚未统一：** `alignment_verified` 是 Item 字段，需来自可追溯的权威审核，而不是客户端任意填写。
3. **Quote 检查只有文本一致性：** 不能代替数学判定和 Rubric 判断质量检查。
4. **评分版本差异：** Numeric / Open Response 的 Policy Version 不同，混合聚合需显式兼容决策。
5. **时间轴含义不同：** Numeric Evidence 用 Submit Time；批准开放题 Evidence 用 Approval Time。未来做时间衰减、延迟检索或审计，必须分别保存作答时间与审核/入库时间。
6. **仓库级版本不可覆盖≠防恶意数据库篡改：** 审计、授权、迁移、数据库约束配置和密钥治理不在本包已实现范围。
7. **测试 Fixture 与现实观察不同：** `assistance_level=0`、`prior_solution_exposure=False` 是单元测试手动提供的条件，不是 URPP 真实作答下自动取得的证明。

---

## 11. 从 Design 01C 到后续 Implementation 的边界

本阶段的主要结果是建立**可测试的 Assessment → Evidence → Student State 内部管线**，并为开放题提供“Review Preview 不得直接转为 Evidence”的结构性限制，为数值题提供与历史 Rubric 绑定的 Repository 恢复路径。

它不应与后来 Implementation 13E 的应用程序 Assistance Log、可恢复教学 CLI、Numeric Attempt Provenance Snapshot、Architecture V2 的 Learning Observation Proposal 混写为同一时间点。这些后续能力必须分别从各自的历史 Commit/原始日志恢复。

与 Architecture V2 的真正连接在于：旧系统的 Numeric Scorer **本来就不推断作答独立性**；它只复制 Attempt 的作答条件。未来 Teaching Harness 如果增加一层 Learning Observation，可以记录“在应用程序报告提供帮助后完成当前任务”的事实，但不能绕过既有 Mastery Eligibility 或把没有 Help Log 当作 `assistance_level=0`。

---

## 12. 下一批资料：如何恢复真实的错误调查历史？

本章完成了八个节点的**源码与测试合同层面**的初步重建。若要满足“0–13 遇到的错误如何分析/如何解决全部写下来”，还需要以下原始证据：失败的测试输出与对应临时 Commit/Working Tree、发生错误前后真实的 Code Diff、当时的调查对话及已经保存的修复日志。Repository Git 只能保留已提交的状态，不能自动还原所有未提交的失败试验。

接下来的网站章节应沿 Git 时间线检查：这八个节点之间是否有补丁/回滚/架构切换；并把这些模块与后来的 Assignment、Session Recovery、Decision Engine 中的真实调用链对齐。**不能把 01C 的内部 Pipeline 描述为后来完整本地教学 CLI 已经接通的同一个用户界面。**

### 本章的来源文件总表

- `4edec7f/backend/app/services/assessment/models_v02.py` 与 `numeric_scoring_v02.py`；`backend/tests/test_numeric_scoring_v02.py`
- `0bfa364/backend/app/services/assessment/open_response_models_v02.py`；`backend/tests/test_open_response_models_v02.py`
- `e6ac6e7/backend/app/services/assessment/open_response_scoring_v02.py`；`backend/tests/test_open_response_scoring_v02.py`
- `55bd26b/backend/app/services/assessment/review_approval_v02.py`；`backend/tests/test_review_approval_v02.py`
- `1374ed1/backend/app/services/assessment/assessment_pipeline_v02.py`；`backend/tests/test_assessment_pipeline_v02.py`
- `3424920/docs/03c_assessment_records_and_authorization.md`
- `1b8dfdb/backend/app/repositories/assessment_records_v02.py`；`backend/tests/test_assessment_records_v02.py`
- `aadd8e3/backend/app/services/assessment/persisted_numeric_pipeline_v02.py`；`backend/tests/test_persisted_numeric_pipeline_v02.py`

**Source Scope：** 以上文件是用户提供的八个历史节点的选定文件，不是一个可独立执行的完整历史仓库。`assessment_history_source_pack.zip` 内保存各版本的原文；本章是附有版本定位符的解释，所有尚无事故日志的失效情境均标为 Guard/Test，而非真实事故。
