# URPP Engineering Archive · Reply 7 / 10

## Personalized Teaching：Student Request、Decision、Agent Routing 与持久化 Assessment 的真实连接

> **文档版本**：Reply 7 / V0.1；**历史范围**：2026-09-19，`0e9b77b1` → `5aec0609` → `ad0f9a51` → `9ea307b7` → `e52095f`。本章的前四个节点以已经上传的历史 Git 源码、对应测试和设计文档为依据；`e52095f` 的真实失败／修复记录以此前用户提供的 Terminal 输出为依据。**本章并未运行用户 Mac 上的测试，也不声称其内部系统现在已部署生产级 LLM、学生身份认证或正式教学成效评价。**

[返回网站主页](../index.html) · [Reply 5：Decision / Orchestration](decision-orchestration-v01.html) · [Reply 6：Persistence / Recovery](persistence-recovery-v01.html)

## 1．为什么需要新增 Personalized Teaching，而不是直接修改旧 Decision Engine？

在 Reply 5 中，我们已经介绍过原始的 `DecisionEngineV01`：它从权威 `ObjectiveStateV02` 构造 `DecisionContextV01`，由 `PedagogicalPolicyV01` 给出与状态有关的可选动作，Controller 提出建议，最后执行 Policy Check。如果建议不在允许集合中，则采用确定性 Fallback。

原始的单轮 Orchestrator 使用这份结果在 `ProfessorAgent` 和 `AssessmentAgent` 之间路由。**该版本无法表达学生此次明确要求什么。**如果只把一个字符串 `"Please explain"` 塞进旧 `DecisionContextV01` 的边角，旧逻辑可能照常依据状态选定 Diagnostic，而用户请求从未进入真正决策。

后来产品目标增加了一条要求：一个学生即使处于 `STRONG` 状态，也可以要求教授重新解释基础概念；即使还没有充分的 Mastery Evidence，也可以要求进一步练习。这不是要求系统相信学生已经掌握知识，而是要求**尊重可执行的学习活动选择，同时维持 Assessment、Evidence Eligibility 和 Session Integrity 的既有边界**。

由此产生两个彼此不同的问题：

1. **Action Selection**：学生这次想做什么？在当前系统支持的活动中，哪些可以选择？
2. **Assessment Admission / Mastery**：某次发放的题是否真正符合目标、Revision 与授权条件？答题记录是否足以更新 Student State？

前者可以根据明确请求调整；后者不能因为请求而降低要求。这是 13B 和 13C 的共同设计动机。

### 本章的时间线：新增什么、不代表什么

| 历史 Commit | 对应代码中的阶段 | 确认引入的能力 | 当时没有完成的能力 |
|---|---|---|---|
| `0e9b77b1` | Implementation 13B-1 | 结构化请求枚举、请求契约、独立 Personalized Context | 不执行动作，不更新掌握状态，不改变旧 Decision Engine |
| `5aec0609` | Implementation 13B-2 | 请求到动作的确定性映射、决策来源与动作集合扩展记录 | 不调用 Agent，不持久化决定，不认证学生 |
| `ad0f9a51` | Implementation 13C-1 | 用一次 Personalized Decision 调用一个匹配的 Agent Port | 不发持久化 Assignment，不收答案，不恢复 Session |
| `9ea307b7` | Implementation 13C-2A | 将个性化 Assessment Turn 适配给既有 Recoverable Numeric Session | 适配器本身不存 Assignment，也不保存完整个性化来源 |
| `e52095f` | Implementation 13C-2B | SQLite 端到端集成测试，验证持久化、恢复和学生请求交互 | 测试使用虚拟 Agent 和隔离数据库，不等于生产学生身份系统 |

**编号注意**：这些是相关源码的 docstring／设计文档实际标注的 13B／13C 子阶段。它们与 `docs/07_...` 等文件序号、Reply 7 编号不是一回事。完整 Implementation 0–13 的原始 Roadmap 仍需单独核对，不用这里的五个节点推定其他阶段。

---

## 2．13B-1：把学生请求变成明确、可校验的对象

### 2.1 `StudentLearningRequestKindV01` 不等于自由文本理解

历史文件：`0e9b77b1/backend/app/services/decision/student_request_v01.py`，源码第 24–30 行。六种请求为：

| 枚举 | 值 | 表达的学习意图 |
|---|---|---|
| `REQUEST_EXPLANATION` | `request_explanation` | 请求概念解释 |
| `TRY_INDEPENDENTLY` | `try_independently` | 请求尝试自主练习 |
| `REQUEST_HINT` | `request_hint` | 请求提示 |
| `REQUEST_DIAGNOSTIC` | `request_diagnostic` | 请求诊断式 Assessment |
| `REQUEST_SELF_EXPLANATION` | `request_self_explanation` | 请求让学生自己解释 |
| `REQUEST_TRANSFER` | `request_transfer` | 请求更广泛的应用/迁移评估 |

这里的「请求」是**来自上层应用的结构化输入**，不是本阶段已经把学生任意自然语言转成枚举。源码并未实现真实的语言理解或用户身份认证。如果未来加入 LLM 意图识别，它不能绕过这些明确的 Value/Scope/Time 校验。

`StudentLearningRequestV01`（第 33–60 行）包含 `objective_id`、`request_kind`、`requested_at`。配置 `frozen=True, extra="forbid"`，时间必须有时区。

```python
class StudentLearningRequestV01(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    objective_id: str = Field(min_length=1)
    request_kind: StudentLearningRequestKindV01
    requested_at: datetime
```

**为什么有 `objective_id`？** 如果当前教学目标是 Matrix Conditioning，却接收到上一轮 Dot Product 的请求，即使请求时间有效，也不该静默归到当前目标。**为什么必须有时区？** 没有时区的本地时间不能稳定比较不同持久化记录的发生顺序。

### 2.2 组合 Context，防止旧决策接口忽略请求

`PersonalizedDecisionContextV01` 使用 `decision_context: DecisionContextV01` 与 `student_request: StudentLearningRequestV01 | None` 的组合，而不继承旧 `DecisionContextV01`。对应历史源码第 63–104 行；设计文档 `docs/07_personalized_decision_policy_v0.1.md` 明确说明了这一动机。

```text
ObjectiveStateV02 ──> DecisionContextV01 ──┐
                                           ├──> PersonalizedDecisionContextV01
StudentLearningRequestV01 / None ─────────┘
```

具体验证顺序：`request is None` → 允许基线执行；请求不为空 → 目标 ID 必须与 State 相同；`request.requested_at >= state.as_of`；`request.requested_at <= decision_context.requested_at`。因此成立的时间关系为：

```text
Student State as_of <= Student Request requested_at <= Decision requested_at
```

这不是在声称应用程序已经验证真正的学生身份，而是在规定**三份结构化记录之间的时间一致性**。如果状态快照比请求更新，旧请求就不能被当成当前状态下的用户意图。

### 2.3 本阶段测试实际覆盖的内容

`backend/tests/test_student_request_v01.py` 至少包含八个命名测试：无请求基线、保留原始 State、错误 Objective、请求早于 State、请求晚于 Decision、缺失时区、额外字段拒绝、组合 Context 不继承旧 Context。它们证实了这组契约的预期行为，**并不表示历史上真实用户曾经提交错误 Objective 或时间戳**。

**阶段验收结论**：13B-1 引入了明确的请求语言和 Scope/Time 契约，没有在这一阶段改变学生 State 或原有 Teaching Action 的选择。

---

## 3．13B-2：何时遵循基线，何时允许明确学生请求？

历史文件：`5aec0609/backend/app/services/decision/personalized_engine_v01.py`，配套 `docs/08_personalized_decision_selection_v0.1.md`、`backend/tests/test_personalized_engine_v01.py`。

### 3.1 六种请求和动作的精确映射

源码第 36–54 行记录：

| Request Kind | Selected Teaching Action |
|---|---|
| `REQUEST_EXPLANATION` | `CONCEPTUAL_REVIEW` |
| `TRY_INDEPENDENTLY` | `INDEPENDENT_PRACTICE` |
| `REQUEST_HINT` | `CONCEPTUAL_HINT` |
| `REQUEST_DIAGNOSTIC` | `DIAGNOSTIC_ASSESSMENT` |
| `REQUEST_SELF_EXPLANATION` | `SELF_EXPLANATION` |
| `REQUEST_TRANSFER` | `TRANSFER_ASSESSMENT` |

这是 URPP V0.1 的确定性工程规则，**不是教育研究已经证明的全局最优教学动作序列**。例如，`REQUEST_TRANSFER` 选中 `TRANSFER_ASSESSMENT`，仅表示计划进行该教学活动，绝不能直接得出学生拥有 Transfer 能力的结论。

### 3.2 没有请求：直接委托旧版 Rule-Based Baseline

关键调用位于源码第 131–147 行：

```python
if student_request is None:
    decision = self._baseline.decide(decision_context)
    # selection_source = BASELINE
    # selected_for_request = False
    # request_expanded_allowed_actions = False
```

不要把「引入 Personalized Engine」误写成「替换旧 Decision Engine」。**没有明确请求时，它复用现有 `DecisionEngineV01(RuleBasedControllerV01())`。** 这样新的能力不会悄悄改变所有普通教学轮次；后续还可以把该基线当作对照实验条件。

### 3.3 有明确请求：扩展的是状态依赖教学列表，不是数据库或 Evidence 许可

源码第 159–184 行先调用旧 Policy 获取 `baseline_allowed`。如果请求映射的动作不在其中，构造：

```python
allowed = (*baseline_allowed, requested_action)
```

再产生 `DecisionResultV01`，将 `selected_action=requested_action`。结果用 `request_expanded_allowed_actions` 明确记录是否发生扩展。

**举例：** State 为 `STRONG`，学生要求概念解释。旧状态依赖列表可能不包含 `CONCEPTUAL_REVIEW`，而新的个性化结果可以增加这个原本受支持的动作，使请求被选中。这个例子对应 `test_strong_student_can_request_conceptual_review`，不是把强掌握变成未知，也不是让用户凭请求编辑 Mastery。

**边界：** 只能选已经在 `TeachingActionV01` 定义的动作；请求不能使不匹配的 Assessment Item 获准发放，不能使未知 `assistance_level` 被改成独立，也不能跳过已存在的 Session Registration 和 SQLite Integrity 检查。

### 3.4 Decision Provenance 是什么？它又不是什么？

`PersonalizedDecisionResultV01` 中的字段包括：

```text
DecisionResultV01 decision
DecisionSelectionSourceV01 selection_source
bool selected_for_request
bool request_expanded_allowed_actions
str selection_reason
```

`selection_source=explicit_student_request` 表示**此次选择来自结构化请求**，而不是「系统已经确认学生身份」或「学生已经完成所请求的动作」。`selection_reason` 是可检查的人类可读解释，不是评分证据。此时数据只是内存中的函数返回值，不能据此断言已经写入 SQLite。

源码中通过前后 `objective_state.model_dump(mode="json")` 检查，避免决策函数在程序内意外修改传入 State。该检查不是进程沙箱，也不具备认证含义。

### 3.5 测试对照

原始测试涵盖：无请求时使用基线、六种请求映射、强状态请求解释、已在允许集合的动作不重复扩展、State 不变、旧 Context 不能被错用、Decision Result 不虚报 Agent 执行。它们证明的是**动作选择层的合同**，尚未说明 Agent 确实执行或 Assessment 确实发放。

---

## 4．13C-1：从「选中了动作」到「调用一次 Agent」

历史文件：`ad0f9a51/backend/app/services/decision/personalized_turn_orchestrator_v01.py`；设计文档：`docs/09_personalized_teaching_turn_v0.1.md`。

### 4.1 为什么不能先调用 Personalized Engine，再调用旧 Orchestrator？

旧 `TeachingTurnOrchestratorV01` 会在 `run_turn()` 内部重新调用原始 `DecisionEngineV01`。如果我们先在 Personalized Engine 中选好了用户请求的动作，然后再把 Context 交给旧 Orchestrator，**很可能得到第二次、不包含学生请求的决定**。

这将造成 `request_explanation → CONCEPTUAL_REVIEW` 与最终 Agent 实际收到的动作不一致。因而新的 `PersonalizedTeachingTurnOrchestratorV01` **自己只调用一次个性化决策，再路由到一次 Agent 调用**，而不是在已做出的个性化决定后再次使用旧 Orchestrator。这个限制直接写在源码第 98–105 行和原始设计文档中。

```text
ObjectiveStateV02 + optional StudentLearningRequestV01
                          ↓
             DecisionContextBuilderV01
                          ↓
            PersonalizedDecisionContextV01
                          ↓
           PersonalizedDecisionEngineV01
                    一次决定
                          ↓
                 _route_action()
                    ↙         ↘
             Professor      Assessment
               Agent          Agent
                    ↘         ↙
         PersonalizedTeachingTurnResultV01
```

### 4.2 Agent Port 是接口，不等于真实 LLM

这里使用 `PersonalizedTeachingAgentPortV01(Protocol)`：

```python
def produce(
    self,
    *,
    context: PersonalizedDecisionContextV01,
    decision: PersonalizedDecisionResultV01,
) -> str: ...
```

Port 同时接收原始结构化 Student Request 和已选择的 Decision。这样 Agent 能知道学生请求的具体活动，以及决策为什么满足该请求。

**但是：** 这个 Interface 没有提供真实模型推理、HTTP 身份鉴别或 Learning Evidence 更新。13C-1 的测试使用 Recording Agent Doubles；即使内容字符串成功返回，也不能推出学生已阅读、已理解或已掌握。

### 4.3 Agent Routing 如何工作？

路由重用旧模块中的 `ASSESSMENT_ACTIONS` 与 `PROFESSOR_ACTIONS` 两组常量；`_route_action` 只在其中一组包含选中动作时返回相应 Agent 类型，否则抛出异常。然后仅调用被选中的 Agent 的 `produce()`。

传给 Agent 的是完整 `PersonalizedDecisionContextV01` 和 `PersonalizedDecisionResultV01`，不是丢掉请求再要求 Agent 自己推断。

调用前检查 `decision_id` 和所选动作必须包含在该 Decision 的允许列表中；决策调用前后、Agent 调用前后检查原始 State 的 JSON 序列化值是否发生变化；`content` 必须是字符串且非空白。Agent 抛出的异常不会被静默替换成伪成功的教学输出。

### 4.4 「完成一次 Turn」的真实语义

`PersonalizedTeachingTurnResultV01` 包含 `decision`、`agent_kind`、`content`。它只表示**内部教学内容生成调用返回了符合形状的内容**，并非 Assessment Attempt、持久化 Assignment、学生已看到的信息或实际学习成效。

本阶段原始测试包括：无请求的基线 Assessment 路由、强状态的解释请求交给 Professor、独立尝试请求交给 Assessment、支持请求的正确路由、错误 Objective 拒绝、无效 Agent Output 拒绝、Agent 异常不被隐藏、Agent 不能偷偷修改 State、教学文字不是 Assessment Evidence。

---

## 5．13C-2A：让 Personalized Turn 接入已有 Recoverable Numeric Session

历史文件：`9ea307b7/backend/app/services/decision/personalized_numeric_session_adapter_v01.py`，设计文档 `docs/10_personalized_numeric_session_adapter_v0.1.md`。

### 5.1 为什么需要 Adapter，而不是复制一个新的 Numeric Session？

已有 `RecoverableNumericSessionServiceV01` 期待内部 Orchestrator 提供旧式接口：

```python
run_turn(objective_state, *, decision_id, requested_at)
```

新 Personalized Orchestrator 则需要额外参数 `student_request`，而且返回结构包含 `PersonalizedDecisionResultV01`，不等于旧 `TeachingTurnResultV01`。

如果直接复制整个 Recoverable Session 来支持请求，容易出现两份 Assignment 发放逻辑、两份 Assessment Item Scope/Revision 校验、两份 Atomic Submission 与恢复逻辑。以后修复一个版本的 SQLite Bug，另一个版本可能落后。

因此这次采用适配器：**将一次 Student Request 绑定到适配器实例，调用个性化 Orchestrator 一次，再把结果转换成旧 Session 可识别的返回合同。** Assignment 真正发放的权威边界，仍然在已有 Recoverable Session 和 Repository 中。

### 5.2 精确的适配流程

```text
Structured Student Request
           ↓  构造新 Adapter
PersonalizedNumericSessionTurnAdapterV01
           ↓  交给 RecoverableNumericSessionServiceV01
Recoverable Service 获取 State 和待发放 Assessment Item
           ↓  调用 adapter.run_turn(...)
Adapter 校验 Objective / Time / Request One-shot
           ↓  Personalized Orchestrator 做一次决定+调用 Agent
Adapter 校验结果确实指向 assessment 类型动作
           ↓  转换为旧 TeachingTurnResultV01
Recoverable Service 校验存储的 Item 与 Scope / Revision
           ↓  按原逻辑创建 persisted Assignment
```

注意：`RecoverableNumericSessionServiceV01` 具体在某条函数路径上检查 Item、是否允许发放和创建 Assignment，应以对应历史版本源码为准；这张图表示职责边界，不宣称所有检查必须按图中一模一样的细粒度顺序执行。

### 5.3 为什么 Explanation / Hint 不能进入 Numeric Assignment Path？

适配器构造时先把请求映射为动作，要求映射结果属于 `ASSESSMENT_ACTIONS`。`REQUEST_EXPLANATION` 与 `REQUEST_HINT` 不符合要求，因此被拒绝；它们应通过不发持久化 Numeric Assignment 的教学路径执行。

即使上游交给适配器的是一个看似合法的请求，适配器在运行后仍检查：`agent_kind == "assessment"` 且 `selected_action in ASSESSMENT_ACTIONS`，避免意外地将 Professor Agent 的解释文字作为数值题目发放。

**教学解释与可持久化的 Assessment Item 不是同一类数据。** 这并不表示系统禁止学生请求解释，而是拒绝将该请求错用到「发放 Numeric Assignment」这条 API 路径。

### 5.4 一次性请求、时间约束与持久化边界

`_explicit_request_used` 防止同一个 Adapter 实例重复用于多个教学决定。这个一次性标志是**内存中的对象状态**，不是经 SQLite 认证的全局防重凭据，也不是同一真实用户只能请求一次。

为匹配 Recoverable Service V0.1 的 State Snapshot 时间契约，适配器要求：

```python
request.requested_at == requested_at
```

这比 13B-1 普通 Personalized Context 的时间区间关系更严格。它是**该兼容适配路径的版本约束**，不应该外推成所有教学请求都必须与 Decision 精确同秒。

适配器返回旧 `TeachingTurnResultV01` 时，只有 Decision、Agent Kind、Content。原 Personalized Decision 的 `selection_source`、`request_expanded_allowed_actions` 等仍只留在中间对象；**本阶段并没有将完整个性化来源写进 Assignment Schema**。

### 5.5 何以判定「13C-2A 做到了什么」？

`test_personalized_numeric_session_adapter_v01.py` 的测试覆盖：请求独立尝试交给 Assessment Agent、请求 Transfer 不等于 Transfer Success、无请求基线、Explanation/Hint 不能误变成 Numeric Assignment、Objective 不匹配、时间不一致、同一 Adapter 请求复用、错误路由至 Professor 的拒绝。

这些是使用 Recording Agent 的接口测试。本阶段**没有凭这些测试就声称已完成跨进程 SQLite 的个性化教学恢复**。那属于后续 13C-2B 的集成工作。

---

## 6．13C-2B：真正的 SQLite Integration 与一次真实的 Test Oracle Bug

13C-2B 的历史集成测试文件是 `backend/tests/test_personalized_numeric_session_sqlite_v01.py`。此前用户上传的 Terminal 日志记录：初次专项执行 `1 failed, 25 passed`；调整两个新测试断言后为 `26 passed`；完整 Backend 回归为 `324 passed`；最终提交 `e52095f`，提交消息为 `test: verify personalized numeric sessions across SQLite recovery`。

### 6.1 为什么这次失败不应归咎于 Assignment Repository？

失败测试名：

```python
test_explanation_request_cannot_issue_numeric_assignment
```

测试预期：对于请求概念解释的学生，Numeric Assessment Delivery Path 不能发放 Assignment。

原始失败断言：

```python
assert not stack.last_assessment_agent
```

但 `stack.last_assessment_agent` 存放的是一个 `RecordingAgent` 对象。对象在测试夹具中被创建，**与这个 Agent 是否真的调用过 `produce()` 并发放 Assessment 不是同一件事**。

所以观察到：

```text
AssertionError: assert not <RecordingAgent object ...>
```

只能说明「对象存在导致该断言为假」，不能证明系统已经错误发放了 Numeric Assignment。

### 6.2 如何分析：测试的观察对象错了

```text
业务要求：不能发 Numeric Assignment
            ↓
测试试图证明：Assessment Agent 不存在
            ↓
RecordingAgent 在准备测试对象时已被创建
            ↓
即便没有发题，该断言仍失败
            ↓
根因：Test Oracle 验证了错误对象的存在性
```

这个问题属于 **Test Oracle Bug**：测试真正关心的是「是否有实际调用、是否产生数据库副作用」，而不是「依赖对象是否提前构造」。

日志显示修复时修改了新测试文件中两个错误断言，并明确没有修改生产代码。由于本轮 Decision Source Pack 没有包含 `e52095f` 的提交前后测试正文，**这里不虚构那两个断言修复后的准确源码**；后续可以用 `git show e52095f:backend/tests/test_personalized_numeric_session_sqlite_v01.py` 将最终测试断言补到网站。

### 6.3 回归证据能证明什么？

| 证据 | 历史观察 | 适当结论 |
|---|---|---|
| 第一次 13C-2B 专项运行 | `1 failed, 25 passed` | 有一个测试断言失败；不等于生产发题错误 |
| 修改两个新测试断言 | 记录显示仅改变测试，无生产文件修改 | 修复范围是测试 Oracle |
| 重新运行专项测试 | `26 passed` | 这组 SQLite 集成测试通过 |
| 完整 Backend 回归 | `324 passed` | 当时该分支的 324 项 Backend 测试通过 |
| Git Commit | `e52095f` | 本次集成验证结果被提交 |

**不要写成**「所有外部服务与真正的用户环境经过验证」，也不要将 324 项历史测试结果冒充最新 479 项测试下的生产运行结果。

---

## 7．端到端执行示例：不要把一次请求变成一条“独立掌握”证据

下面是**根据上述组件合同构造的教学工作流示例，不是某个真实学生的历史记录**。

### 示例 A：强状态学生主动要求重新解释

```text
ObjectiveState = STRONG
Request = request_explanation
            ↓
Personalized Context 校验 Objective 和时间
            ↓
Personalized Engine 映射 CONCEPTUAL_REVIEW
            ↓
必要时扩展状态依赖允许动作
            ↓
Personalized Orchestrator 路由 Professor Agent
            ↓
返回一段概念解释文字
```

能报告的事实是「选择了 `CONCEPTUAL_REVIEW` 并执行了 Agent 的内容生成」。不能因此改变 State，也不能认定生成文字已被学生看到或理解。由于 Request 是 Professor 类行为，不应接入 Numeric Assignment 发放适配器。

### 示例 B：学生要求独立做题

```text
Request = try_independently
            ↓
Selected Action = INDEPENDENT_PRACTICE
            ↓
Assessment 路由
            ↓
Recoverable Session 验证 Assessment Item / Scope / Revision
            ↓
保存 Pending Assignment
            ↓
学生后来提交 Attempt
            ↓
Numeric Scorer 判断答案正确与否
            ↓
现有 Eligibility 判断可否用于 Mastery State
```

「请求独立做题」只是一条意图记录，不是对外部帮助不存在的验证。即使数值回答正确，也必须保留 `assistance_level` / `prior_solution_exposure` 等字段的真实来源和未知状态。

### 示例 C：学生要求 Transfer Assessment

`REQUEST_TRANSFER → TRANSFER_ASSESSMENT` 的选中结果**不等于**当前 Numeric Scorer 已经获得了可靠的 Transfer Item，也不等于满足 Transfer Gate。后续发题仍需执行与 Item 类型、对齐关系、批准和题目修订相匹配的验证。不能拿一题普通数值题改标签就称其为 Transfer Evidence。这一问题的后续修复属于更晚的 Transfer Assessment 开发节点，应在后续章节单独写明。

---

## 8．从本章能证明的架构不变量

这部分不是额外的设计愿景，而是上述阶段的合同与测试共同围绕的约束：

1. **请求不是 Mastery Evidence**：`StudentLearningRequestV01` 保存学习活动意图，不写 `ObjectiveStateV02`。
2. **有请求／无请求分支不同**：无请求沿用旧 `DecisionEngineV01`；有请求可在支持的动作内覆盖状态依赖教学列表，但不能绕过后续 Assessment Integrity。
3. **做出 Decision ≠ 执行 Action**：`PersonalizedDecisionResultV01` 与 `PersonalizedTeachingTurnResultV01` 表示不同阶段。
4. **生成 Agent 文字 ≠ 发放持久化题目**：Recorded Assessment Item 的版本与 Scope 仍由原有 Session / Repository 校验。
5. **一次个性化请求只能驱动该 Adapter 实例中的一个决定**：不是分布式全局去重，也不是身份认证。
6. **旧 Orchestrator 不应在个性化决定之后再做第二次决定**：否则会丢失原 Student Request 的选择语义。
7. **状态与时间一致性**：请求时间不能早于 State Snapshot 或晚于 Decision；适配器路径额外要求与 Assessment Decision 时间相等。
8. **失败不能伪装成功**：Agent 异常、非字符串或空白内容会被拒绝；这不证明已经实现端到端的学生可见交付确认。
9. **本阶段的个性化来源不必然持久化**：Adapter V0.1 明确不把 Request 和 `selection_source` 写入旧 Assignment。

---

## 9．Guard Casebook：哪些只是预防性测试？

以下行为由历史测试覆盖，但在这批原始资料中**没有相应真实生产事故日志**，因此标记为 `GUARD` 而非 `BUG`。

| Guard ID | 被覆盖的失效情境 | 测试文件与函数 |
|---|---|---|
| `GUARD-13B-01` | 请求 Objective 与 State 不匹配 | `test_student_request_v01.py::test_request_must_match_current_objective` |
| `GUARD-13B-02` | 请求早于 State Snapshot 或晚于 Decision | `test_request_cannot_be_older_than_state_snapshot`、`test_request_cannot_occur_after_decision` |
| `GUARD-13B-03` | 时间缺失时区或夹带任意字段 | `test_request_timestamp_must_be_timezone_aware`、`test_request_contract_rejects_unstructured_extra_fields` |
| `GUARD-13B-04` | 旧 Decision Context 静默忽略学生请求 | `test_personalized_context_does_not_inherit_old_context` |
| `GUARD-13B-05` | 没有请求时意外改变旧策略 | `test_no_request_uses_existing_baseline` |
| `GUARD-13B-06` | Request 被错误宣称为 Agent 已执行或 Mastery 已更新 | `test_decision_result_does_not_claim_agent_execution`、`test_request_does_not_modify_authoritative_student_state` |
| `GUARD-13C-01` | Personalized Decision 之后旧 Orchestrator 再决定一次 | `ad0f9a51` Orchestrator 的单次决策结构和相关路由测试 |
| `GUARD-13C-02` | Agent 返回空白或无效内容、失败被静默隐藏 | `test_invalid_agent_output_is_rejected`、`test_agent_failure_is_not_silently_replaced` |
| `GUARD-13C-03` | Explanation / Hint 被作为 Numeric Assignment 发放 | `test_explanation_request_cannot_become_numeric_assignment`、`test_hint_request_cannot_become_numeric_assignment` |
| `GUARD-13C-04` | 同一个 Adapter 重复消费请求或时间不匹配 | `test_explicit_request_cannot_be_reused_for_another_turn`、`test_request_timestamp_must_match_decision` |
| `GUARD-13C-05` | “请求 Transfer”被误认为“Transfer 成功” | `test_transfer_request_does_not_claim_transfer_success` |

唯一作为本章 **Historical Bug** 写入的是 13C-2B 的错误测试断言，因为我们拥有用户提供的真实失败、修复及回归输出。

---

## 10．开发者学习：这些代码教会我们什么 C/SWE 设计原则？

### 10.1 Domain Contract 不等于 Transport Contract

`StudentLearningRequestV01` 是教学意图的 Domain Contract，而 API 的登录 Session、HTTP 请求来源和 Student Identity 是外层 Transport / Authorization 的事情。Domain Contract 检查 Scope 和时间，却不会自动认证 HTTP 调用方。这能让本地 CLI 与未来 Web 应用复用核心契约，但前提是外层真的承担认证责任。

### 10.2 Composition 避免静默语义丢失

当新 Context 比旧 Context 多了关键的 `student_request`，不要简单继承或把字段隐藏在 dict 中交给旧函数。显式组合让函数签名能表达「这次决策必须考虑 Student Request」，并防止原始 `DecisionEngineV01` 被误用。

### 10.3 Adapter 负责协议转换，不应复制业务规则

`PersonalizedNumericSessionTurnAdapterV01` 让新 Orchestrator 满足旧 Session 的 `run_turn` Interface，转换必要的 Decision / Agent Kind / Content；但 Item Revision、Assignment INSERT 和 Attempt 提交仍由现有 Service 负责。复用让旧系统的数据库修复不用分别复制到两套发题路径。

### 10.4 Test Oracle 必须观察业务结果

依赖对象存在，并不表示发生了业务调用。禁止发题的测试应通过 Recording Agent 的调用记录和／或 Assignment Repository 的数据库状态观察，而不是要求 `RecordingAgent` 对象在夹具中根本不存在。本章真实错误正好说明了这一点。

### 10.5 留住三层不同的“成功”

- `decision selected`：函数返回一个合法 Teaching Action。
- `content produced`：匹配的 Agent Port 返回符合内容合同的字符串。
- `assessment completed`：数据库持久化的 Assignment 接收到 Attempt，评分与 Evidence Eligibility 进一步处理。

这三层不可以互相代替；更远的「学生真正学会」还需要后续新题、保持和迁移证据。

---

## 11．给未来研究 Jev / Small Decision Model 保留怎样的对照基线？

**以下是本次历史分析推导出的未来研究建议，不能写成 13B／13C 当时已实现的系统能力。**

未来若引入 Jev 或其他结构化 Decision Model，可以沿用明确的输入与输出边界：输入脱敏的 Objective State Snapshot、明确 Request、支持的动作与版本；输出单个建议动作及其原始结果。保留原本的 Policy Constraints 和现有 Student State / Assessment 服务，让模型无权直接写 Mastery。

实验必须分别记录：模型是否按规则输出、实际调用了什么 Agent、是否成功交付，以及学生在新题和延迟练习上的表现。只比较「模型和旧 Policy 选择的动作一致率」，验证的是模仿程度，而不是教学效果。不得将现有 13B/13C 的确定性决策流程改写为已经训练的小型模型或真实 Jev 调用。

---

## 12．可追溯来源、缺口与复查命令

**历史源码包**：`decision_orchestration_history_source_pack.zip`。本章主要引用该 ZIP 中以下路径：

```text
0e9b77b1/backend/app/services/decision/student_request_v01.py
0e9b77b1/backend/tests/test_student_request_v01.py
0e9b77b1/docs/07_personalized_decision_policy_v0.1.md
5aec0609/backend/app/services/decision/personalized_engine_v01.py
5aec0609/backend/tests/test_personalized_engine_v01.py
5aec0609/docs/08_personalized_decision_selection_v0.1.md
ad0f9a51/backend/app/services/decision/personalized_turn_orchestrator_v01.py
ad0f9a51/backend/tests/test_personalized_turn_orchestrator_v01.py
ad0f9a51/docs/09_personalized_teaching_turn_v0.1.md
9ea307b7/backend/app/services/decision/personalized_numeric_session_adapter_v01.py
9ea307b7/backend/tests/test_personalized_numeric_session_adapter_v01.py
9ea307b7/docs/10_personalized_numeric_session_adapter_v0.1.md
```

**真实错误日志**：此前用户提供的 13C-2B Terminal 记录：`1 failed, 25 passed → 两个测试断言修复 → 26 passed → 324 passed → e52095f`。该测试提交版本未被包含在本章的 Decision Source Pack 中，仍需补充 `e52095f` 的测试正文和 `docs/11_personalized_numeric_sqlite_integration_v0.1.md` 才能给出完整的 Assertion 前后 Diff。**已确认的原始错误断言可以引用，未知的最终断言不能凭空补写。**

只读复查示例：

```bash
# 仅查看历史文件；不要在工作区写回任何版本
git show 0e9b77b1:backend/app/services/decision/student_request_v01.py
git show 5aec0609:backend/app/services/decision/personalized_engine_v01.py
git show ad0f9a51:backend/app/services/decision/personalized_turn_orchestrator_v01.py
git show 9ea307b7:backend/app/services/decision/personalized_numeric_session_adapter_v01.py
git show e52095f:backend/tests/test_personalized_numeric_session_sqlite_v01.py
```

**结论**：13B 引入不改变 Mastery 的学生请求和确定性动作选择；13C 将动作选择接到真实 Agent Port 与既有 Recoverable Numeric Session；13C-2B 的原始集成日志确认一项测试 Oracle Bug 被修复。后续的 Assistance Presentation、可恢复 CLI 和 Provenance Snapshot 属于更晚阶段，应在下一章独立考察。 
