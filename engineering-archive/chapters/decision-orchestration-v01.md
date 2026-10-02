# URPP Engineering Archive · Reply 5 / 10
## Logical Decision Engine、Teaching Orchestration 与 Personalized Session Adapter

> **档案性质：历史源码复原与事后技术分析。** 本章依据 `decision_orchestration_history_source_pack.zip` 内八个 Git 节点的代码、测试和设计文档，辅以此前保存的 13C-2B 原始测试失败与修复日志。函数名称与字段按当时的历史版本记录。**本章不是当前 HEAD 的完整代码审计，也不把防御性测试写成已经发生的生产事故。**
>
> **历史定位：** Design 01D，以及明确标记为 Implementation 13B-1、13B-2、13C-1、13C-2A 的后续实现。原始 Implementation 0–13 总 Roadmap 的整体阶段对应关系仍待查证。**这里的八个 Commit 是历史检查点，不是八个完整 Implementation。**

## 导读：为什么这一章必须从“选择”和“执行”的区别讲起？

上一章关注 `Student Response → Scoring → Evidence → ObjectiveStateV02`。本章接上另外半圈：`ObjectiveStateV02 → DecisionContext → TeachingAction → Agent → Content`。这两半圈不是同一个函数：一个答案被评分，不会自动使 Agent 的一段解释成为新学习证据；一个模型选择了 `TRANSFER_ASSESSMENT`，也不会自动证明学生已完成 Transfer。

本章将严格区分六个时刻：**State 已生成、动作被允许、动作被选择、Agent 被调用、Assessment 被发放、Attempt 被接受并重新估计 State**。历史实现逐次增加这些能力；早期版本不能被描述成后期完整的恢复式教学会话。

**一条主线：**

```text
已计算的 ObjectiveStateV02
   → DecisionContextV01（时间、decision_id）
   → PedagogicalPolicyV01.allowed_actions()（状态依赖候选集）
   → RuleBasedControllerV01.propose() / 可替换 Controller
   → DecisionEngineV01.decide()（检查提议，必要时 fallback）
   → DecisionResultV01（选择结果，不是已执行事件）
   → TeachingTurnOrchestratorV01.run_turn()
   → 根据 selected_action 路由到 Professor 或 Assessment Agent
   → TeachingTurnResultV01（返回内容，不是学习证据）
   → [后续版本：存储题目绑定、待答题、Attempt 和状态重新计算]
```

## 1. 八个 Git 历史检查点：组件是什么时候出现的？

| Commit 前缀 | 资料包中的历史对象 | 能确认的改变 | 此时仍不能声称的能力 |
|---|---|---|---|
| `1b26d215` | `models_v01.py`、`policy_v01.py`、`engine_v01.py`、对应测试、`docs/03d_logical_decision_engine.md` | 建立规则式 Controller、允许动作列表、Proposal/Result 和受限的 fallback | 没有真实 LLM、Agent 执行、作答提交或 Session 持久化 |
| `9151b227` | `turn_orchestrator_v01.py`、测试 | 将已选择动作分发到 Professor/Assessment 两类 Agent Port；禁止把返回内容当证据 | 无法保证学生实际看见内容；不提交 Attempt |
| `98f08802` | `numeric_teaching_session_v01.py`、测试 | 在内存中记录 Pending Numeric Assessment；绑定已存题目、Revision、Student/Session 和已有 Attempt ID | Pending 不是数据库持久化；进程重启后不可据此恢复 |
| `99c983b8` | 同名 Session 文件的后续版本和新增测试 | 增加 `AssessmentDeliveryV01`、服务端 Assignment ID、结构化返回，沿用旧版交互入口 | Assignment ID 不是登录凭证；该版本 Pending 仍在内存中 |
| `0e9b77b1` | `student_request_v01.py`、测试、`docs/07_*` | 13B-1：显式结构化学习请求与独立的 `PersonalizedDecisionContextV01` | 只定义请求，不选择或执行个性化动作 |
| `5aec0609` | `personalized_engine_v01.py`、测试、`docs/08_*` | 13B-2：无请求时沿用基线，有请求时映射动作、记录来源，必要时扩展原基线动作集 | 不代表题目存在、不发放题目、不授予掌握 |
| `ad0f9a51` | `personalized_turn_orchestrator_v01.py`、测试、`docs/09_*` | 13C-1：一次个性化决策，仅调用对应的一个 Agent；原始请求传递到 Agent | 无持久化 Assignment、真实 LLM、学习证据或完整会话 |
| `9ea307b7` | `personalized_numeric_session_adapter_v01.py`、测试、`docs/10_*` | 13C-2A：通过 Adapter 将个性化教学 Turn 接入既有 Recoverable Numeric Session 接口 | Adapter 本身不保存个性化决策来源，且其单元测试不等于重启集成测试 |

**关于历史范围：** 这些都是 `git show <commit>:<file>` 恢复的历史版本。`9ea307b7` 引用的 `RecoverableNumericSessionServiceV01` 并不包含在本轮源码包中，因此本章只分析 Adapter 直接可见的调用契约，不杜撰该 Service 的内部事务实现。上一轮已经保存的 13C-2B 日志可证明另一次 SQLite 集成测试曾经出现错误测试断言；它不能替代本轮八个 Commit 的全部开发日志。

## 2. Decision Engine V0.1：模型“建议动作”和策略“允许动作”分开

### 2.1 六种动作如何划分

历史 `TeachingActionV01` 枚举定义了六种名称：

| `TeachingActionV01` | 原始值 | 早期路由 |
|---|---|---|
| `DIAGNOSTIC_ASSESSMENT` | `diagnostic_assessment` | Assessment Agent |
| `CONCEPTUAL_REVIEW` | `conceptual_review` | Professor Agent |
| `CONCEPTUAL_HINT` | `conceptual_hint` | Professor Agent |
| `INDEPENDENT_PRACTICE` | `independent_practice` | Assessment Agent |
| `SELF_EXPLANATION` | `self_explanation` | Professor Agent |
| `TRANSFER_ASSESSMENT` | `transfer_assessment` | Assessment Agent |

动作的**名称不是执行保证**。例如 `INDEPENDENT_PRACTICE` 是一种教学活动类型，并不能证明学生没有额外使用工具；`TRANSFER_ASSESSMENT` 是拟执行的动作，并不能证明发生了成功的知识迁移。早期 Orchestrator 只分发这六种动作，不生成可直接用于 Mastery 的 Evidence。

### 2.2 DecisionContextV01：谁对学生状态负责？

`DecisionContextV01` 内含 `decision_id`、已有的 `ObjectiveStateV02` 和 `requested_at`。文件注释明说：Context 由应用层构造，Decision Model **不得自行构造 Student State**。`requested_at` 必须带时区，并满足：

```python
if self.requested_at < self.objective_state.as_of:
    raise ValueError(
        "Decision cannot precede its Student State snapshot."
    )
```

这不是为了让时间戳看起来整齐，而是确定一项因果顺序约束：**一次教学选择不应被标注为发生在其所依据的状态快照之前。** 在后期 CLI 的实际错误中，错误的恢复时间和下一轮 Decision 时间违反了这个约束；根因不是应该删除这个检查，而是调用链使用了相互矛盾的时间。

`model_config = ConfigDict(frozen=True, extra="forbid")` 使这些 Pydantic Contract 对普通赋值和未声明字段保持约束；但这本身不是身份验证或面对恶意进程的隔离边界。引用 `ObjectiveStateV02` 也不自动证明调用方有权读取某个真实学生的数据。

### 2.3 PedagogicalPolicyV01：早期允许动作集合

原始 `allowed_actions()` 的**精确映射**如下：

| `state.state` | 原始 `allowed_actions()` 返回值（保留顺序） |
|---|---|
| `UNKNOWN` | `DIAGNOSTIC_ASSESSMENT`, `CONCEPTUAL_REVIEW`, `INDEPENDENT_PRACTICE` |
| `EMERGING` 或 `DEVELOPING` | `CONCEPTUAL_REVIEW`, `CONCEPTUAL_HINT`, `INDEPENDENT_PRACTICE`, `SELF_EXPLANATION` |
| `COMPETENT` | `INDEPENDENT_PRACTICE`, `SELF_EXPLANATION`, `TRANSFER_ASSESSMENT` |
| `STRONG` | `SELF_EXPLANATION`, `TRANSFER_ASSESSMENT`, `INDEPENDENT_PRACTICE` |
| 其他标签 | `ValueError("Unsupported Student State. No teaching action allowed.")` |

这个列表是**教学策略基线**，不是经过随机实验验证的最优教学顺序。原始 `policy_v01.py` 注释明确说明这些规则是 engineering baselines。`allowed_actions` 的顺序也很重要：在 Controller 无法给出被允许的动作时，fallback 会采用自己的偏好，必要时选集合中的第一个动作。

### 2.4 RuleBasedControllerV01：同为 UNKNOWN，为什么可能选不同动作？

核心源码的条件分支为：

```python
if (
    state.state == ObjectiveStateLabel.UNKNOWN
    and state.distinct_assessment_count == 0
):
    preferred = TeachingActionV01.DIAGNOSTIC_ASSESSMENT
elif state.state == ObjectiveStateLabel.UNKNOWN:
    preferred = TeachingActionV01.INDEPENDENT_PRACTICE
elif state.state in {
    ObjectiveStateLabel.EMERGING,
    ObjectiveStateLabel.DEVELOPING,
}:
    preferred = TeachingActionV01.CONCEPTUAL_HINT
elif state.state in {
    ObjectiveStateLabel.COMPETENT,
    ObjectiveStateLabel.STRONG,
}:
    preferred = TeachingActionV01.TRANSFER_ASSESSMENT
else:
    preferred = allowed_actions[0]
```

所以 `UNKNOWN + distinct_assessment_count == 0` 选 `DIAGNOSTIC_ASSESSMENT`；`UNKNOWN + distinct_assessment_count > 0` 选 `INDEPENDENT_PRACTICE`。这只基于代码可见的字段，**不代表系统已判定学生需要多少帮助**。例如一条 Attempt 因 Assistance Unknown 被排除后，计数究竟如何变化取决于 State Estimator 的证据统计语义，不能仅凭这段分支推断。

### 2.5 DecisionEngineV01 的故障处理流程

```text
已有 DecisionContext
  → policy.allowed_actions(context)
  → controller.propose(context, allowed)
       ├─ 提议对象不是 DecisionProposalV01 → fallback
       ├─ 提议动作不在 allowed 中          → fallback
       ├─ controller 抛出 TimeoutError     → fallback
       └─ 提议合法                          → 保留提议
  → 再次检查 fallback 结果是否 allowed
  → DecisionResultV01
       [decision_id, selected_action, allowed_actions,
        controller_version, fallback_used, policy_version]
```

原始代码**只捕获 `TimeoutError`**。Controller 抛出其他异常时不会自动使用 fallback，而是继续向上抛出；这有利于避免把所有实现错误都伪装成“模型暂时不可用”。它没有实现真实的定时器：所谓“timeout fallback”指 Controller 已经抛出 `TimeoutError` 时的处理，不表示 Engine 本身能强制中断耗时调用。

历史测试为这一设计提供了具体回归点：`test_disallowed_proposal_triggers_fallback`、`test_controller_timeout_triggers_fallback`、`test_unstructured_output_triggers_fallback`、`test_decision_cannot_precede_state_snapshot` 和 `test_decision_does_not_modify_student_state`。这些是**防御性测试**；源码包没有显示它们曾在提交前真实失败过。

### 2.6 Controller 以后可以替换，但不能偷偷改变证据系统

`LogicalDecisionController(Protocol)` 的最小入口是：

```python
def propose(
    self,
    context: DecisionContextV01,
    allowed_actions: tuple[TeachingActionV01, ...],
) -> DecisionProposalV01:
    ...
```

原始 `docs/03d_logical_decision_engine.md` 明确提出未来可以换成 NanoJev Controller，但该历史节点**并没有训练或接入 NanoJev/Jev**。这是为可替换 Controller 设计的接口，不是模型已上线的证据。即使以后替换，模型也只能返回候选教学动作，不能直接制造 Evidence、修改 State 或绕过评估条件。

## 3. Orchestrator V0.1：一次选择只分发给一个 Agent

### 3.1 三个对象的职责

`DecisionContextBuilderV01.build()` 将已经存在的 State、`decision_id`、`requested_at` 组合成 Contract。它检查传入对象类型与非空 ID；**它没有从 Repository 认证或取得 State**，依赖上游调用方提供可信数据。

`TeachingTurnOrchestratorV01.run_turn()` 调用 `DecisionEngineV01.decide()`，检查返回结果的 ID 和 selected action，然后根据集合分发：

```python
ASSESSMENT_ACTIONS = frozenset({
    TeachingActionV01.DIAGNOSTIC_ASSESSMENT,
    TeachingActionV01.INDEPENDENT_PRACTICE,
    TeachingActionV01.TRANSFER_ASSESSMENT,
})

PROFESSOR_ACTIONS = frozenset({
    TeachingActionV01.CONCEPTUAL_REVIEW,
    TeachingActionV01.CONCEPTUAL_HINT,
    TeachingActionV01.SELF_EXPLANATION,
})
```

`TeachingAgentPortV01.produce(context=..., decision=...) -> str` 是 **Port / Protocol**。当时的测试使用 `RecordingAgent` 等 Test Double，不存在已接入生产 LLM 的证据。返回的 `TeachingTurnResultV01` 包含 `decision`、`agent_kind`、`content`，并在内容为空、非字符串或 Agent 异常时拒绝成功结果。

### 3.2 原始测试怎样证明路由没有串线？

`test_unknown_state_routes_diagnostic_to_assessment_agent`：构造无证据的 UNKNOWN State，期望 `DIAGNOSTIC_ASSESSMENT`，检查 Assessment Agent 调用一次、Professor Agent 调用零次。

`test_conceptual_review_routes_to_professor_agent`：注入专门提出 `CONCEPTUAL_REVIEW` 的 Controller，检查 Professor Agent 调用一次、Assessment Agent 调用零次。

`test_disallowed_controller_uses_policy_fallback`：非法 Transfer 提议回落为未知状态下允许的 Diagnostic，仍由 Assessment Agent 执行。

`test_agent_failure_is_not_silently_replaced`：Assessment Agent 明确抛异常时，Orchestrator 不伪造另一段教学内容来宣称本轮成功。

`test_teaching_turn_does_not_update_student_state`：比较前后的 `model_dump(mode="json")`，验证正常路径没有改变传入 State。

### 3.3 不应夸大“无法修改 State”

原始实现会在 Controller 和 Agent 调用前后保存并比较 State 的 JSON 快照，发现修改则抛错；这是一项**进程内意外修改检查**。它不是认证、不可抵赖证明、数据库权限控制，也不能阻止已经发生的其他外部副作用。`content` 返回代表 Port 已生成内容，并不保证浏览器已呈现、学生已阅读或学习已发生。

## 4. 从单轮教学变成“已选题目—待答题—已存 Attempt”绑定

### 4.1 `98f08802` 的初始 NumericTeachingSessionV01

这个历史版本在内存中维护：

```python
self._state = estimate_objective_state([], ...)
self._accepted_attempt_ids: list[str] = []
self._used_decision_ids: set[str] = set()
self._pending: PendingNumericAssessmentV01 | None = None
```

`start_numeric_turn()` 接收服务端所选 `assessment_item_id`、`item_revision`、`decision_id`、`requested_at`，从 Repository 加载指定 Revision，检查 Course/Objective、Objective Alignment 和时间，然后执行一次 Orchestrator。只有当动作属于 Assessment、路由到 Assessment Agent，且 `turn.content == item.prompt`，才记录 Pending。

**为什么要比较 exact prompt？** 这是该历史版本将自由文本 Agent 输出与已经保存的题目对应起来的临时工程约束。如果允许 Agent 临时生成另一道题，但仍把 Attempt 记入既有 Item 的 Rubric，评分对象就会错位。exact prompt 是一个很窄的兼容办法，不是完整交付验证；它既不能证明用户实际看到了问题，也不适合具有渲染格式差异的未来 UI。

`accept_stored_attempt(attempt_id, as_of)` 的验证次序包括：必须有 Pending、Attempt 未重复接受、从 Repository 加载 Attempt、Student/Course/Objective/Session 一致、Item ID 与 Revision 等于 Pending、`submitted_at >= pending.requested_at`、`as_of` 不早于本次提交和当前 State。随后它使用已有 PersistedNumericAssessmentService 从 accepted attempt IDs 重新估计 State；**只有重新估计成功后**，才更新内存中的 accepted IDs、State，并清空 Pending。

这说明 Repository 存储 Attempt 与 Session 维护 Pending 是不同层次：这个历史版本的“Persisted Numeric Assessment”不等于 Session 自身已具备重启恢复能力。原始模块 docstring 直接声明它是 `in-memory session coordination`。

### 4.2 `99c983b8` 为什么增加结构化 AssessmentDelivery？

历史 Diff 清楚显示新增：

```python
class AssessmentDeliveryV01(BaseModel):
    assignment_id: str
    decision_id: str
    assessment_item_id: str
    item_revision: int
    prompt: str
    selected_action: TeachingActionV01
    assigned_at: datetime
```

新的 `start_structured_numeric_turn()` 依旧调用 Agent，但结构化结果的 `prompt` 来自已经保存的 `item.prompt`，**不使用 Agent 自由文本替换题目**。它生成 `token_urlsafe(24)` 作为本次内存 Pending 的 Assignment ID。`accept_stored_attempt(..., assignment_id=...)` 在结构化路径核对该 ID；旧路径仍保持不传 ID 的兼容行为。

```text
旧路径：Agent text == stored prompt → Pending（无 Assignment ID）
新路径：Agent 被调用 → Delivery.prompt = stored prompt
        → Pending（带 Assignment ID）
        → 提交时要求匹配 Assignment ID
```

这个版本的 Assignment ID 是**关联本次 Pending 的随机标识**，不是用户身份认证、服务端持久化保证或端到端防作弊证明。历史测试覆盖 `test_structured_delivery_uses_stored_prompt`、`test_structured_submission_requires_assignment_id`、`test_wrong_assignment_does_not_consume_pending_turn`、`test_previous_assignment_cannot_complete_new_turn` 和旧路径兼容。

### 4.3 三种不同的绑定，不要混为一谈

1. **Item 绑定**：提交的 Attempt 必须对应指定 Assessment Item 和原始 Revision。
2. **Session 绑定**：Student、Course、Objective、Session 必须匹配正在等待的本次任务。
3. **Assignment 绑定**：在结构化路径中，还要提交正确的当前 Assignment ID。

三者缺一会降低对错误记录关联的防护强度，但它们都不等于现实世界的身份验证；Pending 内存变量也不具备自动事务持久化。

## 5. 13B-1：学生的“请求”不是学习状态

`0e9b77b1` 中出现六种 `StudentLearningRequestKindV01`：

```text
request_explanation / try_independently / request_hint
request_diagnostic / request_self_explanation / request_transfer
```

`StudentLearningRequestV01` 保存 `objective_id`、枚举式 `request_kind`、带时区的 `requested_at`。它不是把自由文本交给模型任意解释，而是一个有限的结构化 Contract。

`PersonalizedDecisionContextV01` **组合**一个原有 `DecisionContextV01` 和可选请求，而不是继承旧 Context：这样旧引擎就不会被“看起来是旧 Context 的新对象”静默传入并忽略学生请求。它拒绝 Objective 不一致、请求时间早于 State 或晚于 Decision 的情况。

这一历史阶段只加入 Contracts；没有改变原来的 Action Selection。原始 `docs/07_*` 明确写明学生请求不得解释为掌握证据，且研究引用不验证该项目的具体阈值和策略效果。

## 6. 13B-2：个性化引擎为什么允许扩展基线动作集？

### 6.1 无请求分支

`PersonalizedDecisionEngineV01` 在 `student_request is None` 时，把 `DecisionContextV01` 交给原来的 `DecisionEngineV01(RuleBasedControllerV01())`，并记录 `selection_source=baseline`、`selected_for_request=False`、`request_expanded_allowed_actions=False`。测试 `test_no_request_uses_existing_baseline` 比较两个完整 DecisionResult 是否一致。

### 6.2 有请求分支：这里确实改变了早期 Policy 的使用方式

请求映射为：

| 请求 | 对应动作 |
|---|---|
| `REQUEST_EXPLANATION` | `CONCEPTUAL_REVIEW` |
| `TRY_INDEPENDENTLY` | `INDEPENDENT_PRACTICE` |
| `REQUEST_HINT` | `CONCEPTUAL_HINT` |
| `REQUEST_DIAGNOSTIC` | `DIAGNOSTIC_ASSESSMENT` |
| `REQUEST_SELF_EXPLANATION` | `SELF_EXPLANATION` |
| `REQUEST_TRANSFER` | `TRANSFER_ASSESSMENT` |

如果指定动作不在基线 `PedagogicalPolicyV01.allowed_actions` 中，个性化引擎会把该动作**追加到个性化结果的 `allowed_actions`**，同时标记 `request_expanded_allowed_actions=True`，并使用自己的 `policy_version=personalized-request-policy-v0.1`。

这是一个真实且重要的架构演变：**不能再说“任何 Controller 在任何情形下都绝对无法扩展允许动作集”。** 严格说，原始 `DecisionEngineV01` 内部的 Controller 不能扩展其 Policy 候选集；`PersonalizedDecisionEngineV01` 是另一条明确设计过的策略路径，它为了响应学生明确请求，可以扩展**状态依赖的教学活动列表**。它没有能力由此修改证据准入、评分、已有 State、题目对齐、Session 登记或数据库完整性。绝不可把“允许学生请求 Transfer Assessment”写成“学生已证明可以独立迁移”。

**源码例子：** 一个合成的 `STRONG` State 请求 `REQUEST_EXPLANATION`，原基线 `STRONG` 动作集中没有 `CONCEPTUAL_REVIEW`；个性化结果追加并选中该动作。历史测试 `test_strong_student_can_request_conceptual_review` 精确验证了这一例子。这个 State 是测试构造的合成对象，绝非真实学生的掌握记录。

### 6.3 为什么要记录来源？

结果包含 `selection_source`、`selected_for_request`、`request_expanded_allowed_actions`、`selection_reason`。这些字段只说明**为什么选中动作**，并且 `selection_reason` 明确指出 `Action execution has not yet occurred`。它们不是教学内容已经成功送达的证明，也没有被这个组件自动写入持久化数据库。

## 7. 13C-1：个性化 Orchestrator 不能调用旧 Orchestrator 再决定一次

`PersonalizedTeachingTurnOrchestratorV01` 使用原有的 `DecisionContextBuilderV01` 构造基础 Context，再用 `PersonalizedDecisionContextV01` 合并请求，**仅调用一次** `PersonalizedDecisionEngineV01.decide()`，随后选择相应 Agent。Agent 收到的是完整的个性化 Context 和带来源的决策结果，而不是只收到 `selected_action`。

为什么不调用旧 `TeachingTurnOrchestratorV01`？因为旧 Orchestrator 内部会再调用一次原始 DecisionEngine，可能把学生请求在第二次决策中丢掉，导致选中动作和执行动作不一致。这个设计理由在 `docs/09_personalized_teaching_turn_v0.1.md` 和源码注释中都有明确说明。

新版与旧版 Port 不是自动兼容的：新版 `PersonalizedTeachingAgentPortV01.produce()` 接收 `PersonalizedDecisionContextV01` 和 `PersonalizedDecisionResultV01`；旧版 Port 接收原始 Context/DecisionResult。

历史测试包括：无请求时保留基线 Assessment 路由、`STRONG` 状态请求解释时路由到 Professor、独立练习请求路由到 Assessment、错 Objective 在 Agent 调用前被拒绝、空内容和 Agent 异常不被替换、State 不应被改写。

**边界：** 这里仍是单次内容调用，不产生新的 Numeric Assignment、Attempt 或 Evidence。执行 `REQUEST_HINT` 不自动创建可信 Assistance Log；那是后续阶段另行实现的功能。

## 8. 13C-2A：Adapter 如何复用已有 Recoverable Numeric Session？

后期系统已经拥有 `RecoverableNumericSessionServiceV01`。与其复制一套持久化发题、提交和状态估计逻辑，新 Adapter 实现旧会话期待的接口：

```python
def run_turn(
    self,
    objective_state: ObjectiveStateV02,
    *,
    decision_id: str,
    requested_at: datetime,
) -> TeachingTurnResultV01:
    ...
```

Adapter 的实例绑定一个可选的 `StudentLearningRequestV01`。如果存在显式请求，初始化阶段就从 `REQUEST_ACTION_MAP` 求得动作；若不属于 `ASSESSMENT_ACTIONS`（例如请求概念解释或 Hint），立即拒绝用于**Numeric Assignment Delivery**。这不代表整个教授系统不能提供 Hint，而是说**不能把 Hint 路径误包装成需要提交数字答案的 Assignment 路径**。

合法请求进入时，Adapter 继续检查 Objective 和请求时间是否与当前决策时间完全相等，调用个性化 Orchestrator 一次，要求最终动作属于 Assessment 且实际路由是 Assessment Agent。然后把新结果收窄为旧版 `TeachingTurnResultV01`，交回 Recoverable Session 的既有流程。

```text
绑定的 Student Request（可选）
  → PersonalizedNumericSessionTurnAdapterV01
  → PersonalizedTeachingTurnOrchestratorV01（一次 Decision + 一次 Agent）
  → PersonalizedTeachingTurnResultV01
  → Adapter 验证 Assessment-only
  → TeachingTurnResultV01（旧接口形状）
  → RecoverableNumericSessionServiceV01（后续发题、存储、答题职责）
```

**真实能力与限制：** Adapter 不另外发题、不自行持久化 Session、不自己修改 Student State，也不认证学生；转换成旧版结果时，会丢失 `selection_source`、`request_expanded_allowed_actions` 等个性化来源字段，源码直接声明此来源只保存在个性化 Turn 的内存结果中，旧版 Assignment Schema 不因此获得持久化溯源能力。

显式请求只能由同一个 Adapter 使用一次；尝试重复使用会抛 `RuntimeError`。这里使用 `self._explicit_request_used=True` 的时机在调用 Orchestrator **之前**，意味着一次调用如果在下游失败，原 Adapter 仍可能把请求视为已使用；源码文档建议新请求构造新 Adapter/Service，并由上层复用已有持久化 Repository 和 Session Identity。这是代码可见的约束，不代表我们已经观察到某个真实用户因它丢失请求。

## 9. Debugging Casebook：一个真实失败 + 多个不能冒充事故的 Guard

### BUG-13C-2B-001：错误的测试断言，将对象存在误当成 Agent 实际执行

**来源类型：先前保存的 13C-2B 用户 Terminal 原始测试日志，而不是本轮 ZIP 中的测试文件。** 原始输出：`1 failed, 25 passed`。失败测试名为 `test_explanation_request_cannot_issue_numeric_assignment`；测试在预期拒绝解释请求之后执行：

```python
assert not stack.last_assessment_agent
```

实际 `stack.last_assessment_agent` 已经引用一个 `RecordingAgent`，于是断言失败。**对象被构造并不等于该 Agent 被调用，更不等于 Numeric Assignment 被发放。** 原始后续修复记录显示只调整新测试文件里的两个错误断言，没有修改生产代码；重新运行专项测试 `26 passed`，全 Backend `324 passed`，并提交 `e52095f`。因此归类为 **test-oracle bug（测试断言选择错误）**，不能写成“生产系统错误地发出了 Numeric Assignment”。

经验：测试要检查 `agent.calls`、真实 Assignment 存在性及实际执行路径，不能仅靠 `last_assessment_agent` 是否为 `None` 来证明业务行为。精确的两条新断言前后 Diff 没在本轮 ZIP 中，后续找到原始 Commit 历史代码后再补齐。

### GUARD-01D-001：非法的 Transfer 提议

`test_disallowed_proposal_triggers_fallback` 构造 UNKNOWN State，让 Controller 提出 `TRANSFER_ASSESSMENT`。原 Engine 会使用规则式 fallback，返回允许的 Diagnostic。**这是一项防御性测试，不是实际教学误判事故。**

### GUARD-01D-002：模型输出不是 Contract、调用超时

`test_unstructured_output_triggers_fallback`、`test_controller_timeout_triggers_fallback` 验证输入是普通字典或 Controller 抛出 `TimeoutError` 时，不把非法提议送到 Agent。源码没有实际外部模型调用，也未测量真实超时。

### GUARD-01D-003：自由文本替代存储题目

早期 `test_unmatched_agent_prompt_is_rejected` 拒绝 Agent 文本与存储 Prompt 不同的交付；后期 `test_structured_delivery_uses_stored_prompt` 验证结构化 Delivery 直接采用 `item.prompt`。这两条测试记录了设计升级，却不能证明曾真实发生“学生答了一道题，数据库却批改另一道题”的事故。

### GUARD-13B-001：请求先于 State / 晚于 Decision / 错 Objective

相关验证位于 `test_student_request_v01.py`。这里既保护时间语义，也防止把其他 Objective 的学习偏好关联到当前决策；不构成真实账户授权校验。

### GUARD-13C-001：双重决策造成请求丢失

`docs/09_*` 明确解释为什么新 Orchestrator 不调用旧 Orchestrator 再决策。此为记录在设计文档中的**预防性架构理由**，而非已观测两次决策引发的真实事故。

### GUARD-13C-002：Professor 请求误入 Numeric Assignment

`test_explanation_request_cannot_become_numeric_assignment`、`test_hint_request_cannot_become_numeric_assignment` 由 13C-2A Adapter 测试直接覆盖。历史 13C-2B 的真实断言 Bug 另按 BUG-13C-2B-001 记录；不要把两者合并为“生产路由错误”。

## 10. 接口与字段的边界表：未来改代码前先看这里

| 对象 / 边界 | 可以做什么 | 不应该宣称它能做什么 |
|---|---|---|
| `ObjectiveStateV02` | 保存状态估计与已知证据统计 | 不由 Decision Model 自行创建真实学生掌握结论 |
| `DecisionContextV01` | 组合 State、decision_id、时点 | 不认证 State 或学生身份 |
| `PedagogicalPolicyV01` | 给原始 Controller 返回基线候选集 | 不是全系统永久不可扩展的动作权限体系 |
| `DecisionProposalV01` | 提出一个教学动作 | 不证明动作已执行 |
| `DecisionResultV01` | 记录最终动作、候选集、fallback、策略版本 | 不生成 Evidence，不保证 Assignment 已存在 |
| `TeachingTurnResultV01` | 说明一次 Port 返回了内容 | 不证明用户看见、理解或掌握内容 |
| `PendingNumericAssessmentV01` | 绑定内存中的当前待答题 | 不是永久持久化 Assignment 或登录凭据 |
| `AssessmentDeliveryV01` | 用存储题目和随机 ID 结构化表示本次发题 | 不证明浏览器已经呈现或学生本人答题 |
| `StudentLearningRequestV01` | 表达结构化的学生学习偏好 | 不构成正确性、独立性或 Mastery 证据 |
| `PersonalizedDecisionResultV01` | 标注是否根据请求选择、是否扩展基线集合 | 不承诺 Agent 已成功执行、教学有效 |
| `PersonalizedNumericSessionTurnAdapterV01` | 将一次个性化 Assessment Turn 适配到旧会话接口 | 不持久化完整请求溯源或取代现有 Session 逻辑 |

## 11. 新旧设计的矛盾如何解释，而不是“强行调和”？

**表面矛盾 A：** `1b26d215` 写着 Controller 不得扩大 allowed set；`5aec0609` 却把学生指定动作加入了 allowed set。**解释：** 前者描述的是**旧 DecisionEngine 内的可替换 Controller**，后者是一条独立定义的**个性化策略路径**。需要清楚标记两个 Policy Version；未来如果整合为统一 Policy Gateway，应把“学生请求可扩展哪些教学活动”和“哪些安全、评估、授权条件绝不能扩展”写成不同规则，而不是假装从来没有改变。

**表面矛盾 B：** `INDEPENDENT_PRACTICE` 可以被选中，但 Assistance Level 仍可能 Unknown。**解释：** TeachingAction 只是所选择的教学活动，不会自动生成已验证的独立条件。具体作答来源由后续 Attempt、Assistance 记录和 Evidence Eligibility 决定。

**表面矛盾 C：** Session 名为 Numeric *Teaching*，但早期仅支持 Assessment Turn。**解释：** 这个历史版本的 `start_numeric_turn()` 要求选中 Assessment Action；Professor-only Turn 明确在范围外。以后出现 Professor Agent 路径，并不意味着它在早期 Numeric Session 已经贯通。

**表面矛盾 D：** 13C-2A 接入“Recoverable Session”，本轮 ZIP 内却没有该 Service 的代码。**解释：** Adapter 源码仅可证实调用了所引用的 Service 接口；持久化、恢复和事务的具体实现属于其他 Commit 的历史源文件，需要在后续资料包中单独核查。

## 12. 资料索引、可复现检查与未恢复事实

本章的**一手源码**来自上传资料包中的精确路径：

```text
1b26d215/backend/app/services/decision/{models_v01,policy_v01,engine_v01}.py
1b26d215/backend/tests/test_decision_engine_v01.py
1b26d215/docs/03d_logical_decision_engine.md
9151b227/backend/app/services/decision/turn_orchestrator_v01.py
9151b227/backend/tests/test_turn_orchestrator_v01.py
98f08802/backend/app/services/decision/numeric_teaching_session_v01.py
98f08802/backend/tests/test_numeric_teaching_session_v01.py
99c983b8/backend/app/services/decision/numeric_teaching_session_v01.py
99c983b8/backend/tests/test_numeric_teaching_session_v01.py
0e9b77b1/backend/app/services/decision/student_request_v01.py
0e9b77b1/docs/07_personalized_decision_policy_v0.1.md
5aec0609/backend/app/services/decision/personalized_engine_v01.py
5aec0609/docs/08_personalized_decision_selection_v0.1.md
ad0f9a51/backend/app/services/decision/personalized_turn_orchestrator_v01.py
ad0f9a51/docs/09_personalized_teaching_turn_v0.1.md
9ea307b7/backend/app/services/decision/personalized_numeric_session_adapter_v01.py
9ea307b7/docs/10_personalized_numeric_session_adapter_v0.1.md
```

还原代码建议使用 `git show <full-hash>:<file>`，核对历史版本时不要把目前 HEAD 的同名模块直接代替过去的实现。Commit 前缀可在本地仓库用 `git rev-parse --verify <prefix>^{commit}` 解析为完整哈希。

**尚缺失且必须如实标记：** 八个节点在实际开发中是否出现过更多失败测试、原始失败命令及完整修复步骤；13C-2B 两条断言修改的精确前后 Diff；`RecoverableNumericSessionServiceV01`、SQLite Assignment Repository 的历史实现全文；原始 Implementation 0–13 总 Roadmap 中这些阶段的上级对应关系；真实外部 Jev/NanoJev 的使用与效果实验。以上缺口不应被自动填补成“当时发生的历史”。

## 13. 进入后续章节之前，应当记住的五个结论

1. **State Estimator 决定已有证据支持什么；Decision Engine 决定下一步教学动作。** 两者不能相互代替。
2. **“动作被选中”不是“动作被执行”，更不是“学生已经学会”。** 必须沿着 Agent、Delivery、Attempt、Scoring 逐层区分。
3. **早期基线限制的是 Controller 的动作提议；13B 的显式学生请求引入了可审计的个性化扩展。** 这一变化没有授权修改 Mastery 证据。
4. **13C 的 Adapter 复用了旧会话的持久化边界，没有偷偷复制另一套数据库逻辑。** 但它收窄结果时不保存完整个性化来源，这是源码明确承认的限制。
5. **归档必须忠实区分历史故障和预防性 Guard。** 唯一在本章辅以先前原始终端日志重建的真实失败是 13C-2B 的错误测试断言；其余列出的防御项不应写成已经发生的系统事故。

---

**本章交付状态：** 已完成八个历史节点的 Decision/Orchestration 技术章节和版本差异分析；历史 Bug 覆盖率受原始失败日志可获得性限制。下一章节将继续恢复持久化 Session、Assignment 及端到端恢复机制，不预先将其归入尚未核准的 Implementation 编号。
