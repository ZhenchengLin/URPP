# 第一篇完整技术章节：Foundation → Student State V0.2

> **Archive status：SOURCE-BASED HISTORICAL RECONSTRUCTION。** 本章根据用户上传的 `early_architecture_source_pack.zip` 中 30 个历史版本文件撰写。原始代码可以证明“当时的设计与实现是什么”，但不能自动证明“开发者当时为什么改动、遇到了哪个报错、做了几次尝试”。没有原始失败日志的部分标明为 **事后对比分析**，不是历史 Bug。
>
> **适用版本：** `93e3680` → `0dda011` → `f61cd4b` → `2de3b83` → `90b83fa`。这些是本章的 Git 历史节点，不等于已经确认 Implementation 0–13 的编号边界。**本章没有审查当前 HEAD `a82b2ad` 的同名文件**；不能把早期代码语义直接当作当前线上语义。以下所有代码路径均为相应 Commit 中的版本。

## 01｜最初产品不是聊天机器人

初始 `README.md` 与 `docs/00_product_spec.md` 把 URPP 定义为单学生、单门活跃大学 STEM 课程的 **persistent learning-control loop**：课程资料逐步到达，系统维护学习目标与可追溯的学习证据，依据当前状态选下一步教学动作，教学后再进行形成性评估。North Star 的原文是：“Given the course requirement and current student evidence, what is the next best teaching action?”

最初的目标有十二项，不是十二个已经完成的功能：课程资料改变 Course Model；要求转为 Learning Objectives；状态陈述由证据支持且可追踪；状态可升、可降、可未知；动作来自受约束空间并有 reason code；教学后评估；评估产生 Evidence Events；新证据改变后续教学；暴露不确定性；对照更简单的 baselines。这些条目是 **V0 Must Demonstrate**，不是该次提交的测试结果。

初始 `docs/07_evaluation_plan.md` 设计了四类对照：Generic LLM、Course RAG、URPP Lite（课程上下文 + Student State）、Full URPP（Course Model + Objective + Student Evidence + Pedagogical Policy）。文档列出 course grounding、state-sensitive adaptivity、learning gain、transfer performance 等指标；**源资料没有显示这些对照在初始 Commit 就已经跑完**。

### 设计上为何不能直接“问 LLM 该教什么”

本章可直接确认的项目设计原则是：**Evidence History 是 source of truth，Objective State 是 derived estimate；LLM 可以提出结构化观察，不直接改写 Student State。** 原始文件将 Course Model、Learning Objectives、Student State、Pedagogical Policy 和 Assessment 拆分为职责。它们当时大多处于设计/占位阶段，不能因为目录存在就认为完整教学闭环已经运行。

`docs/04_course_model.md` 特意区分 RAG 回答“内容在哪里讨论”，Course Model 回答“概念在该课程中起什么作用”。`docs/08_privacy_safety.md` 规定不推断非必要的医学、心理、IQ、固定学习风格等属性，并计划允许学生查看和质疑系统推断。这些是原始产品边界，不是后来研究才加上的原则。

**源码证据：** `93e3680:README.md`；`93e3680:docs/00_product_spec.md`；`93e3680:docs/01_architecture.md`；`93e3680:docs/04_course_model.md`；`93e3680:docs/07_evaluation_plan.md`；`93e3680:docs/08_privacy_safety.md`。

## 02｜最初真正写下了哪些代码？

初始 `backend/app/main.py` 创建 FastAPI 实例并引入 health router；不能推断它当时已经接收学习答案、访问 SQLite 或驱动 Professor Agent。`backend/app/llm/client.py` 只有一个 `LLMClient(Protocol)` 边界，定义 `generate_json(prompt_name, payload)` 与 `embed(texts)`：**这是接口，不是已连接模型的证据**。

初始领域模型则比运行时能力更完整。`LearningObjective` 包括 `objective_id`、`course_id`、`concept_id`、Bloom 的 `cognitive_demand`、`knowledge_type`、先修目标、`source_refs`、`source_type`、`authority`、状态及创建/更新时间。`EvidenceEvent` 已经包含学生/课程/会话/目标 identity，`outcome`、范围 `[0,1]` 的 `correctness`、可为 `None` 的 `assistance_level`、`novelty`、`transfer_distance`、`evidence_strength`、`model_confidence` 和 `created_at`。`ObjectiveState` 则有 `state_score`、`confidence`、independent/transfer success 计数与 `status_reason`。

值得留意：**最初 `EvidenceEvent` 就允许 `assistance_level=None`**，它不是在 13E 才发明的字段。最初的 `docs/02_learning_objective_evidence_student_state.md` 已定义 0–6 的 Assistance Ladder，并明确“Student questions do not automatically mean weakness”“Self-report is weak evidence by default”“Unknown / insufficient evidence is valid”。但初始模型允许未知，并不等于当时已经实现了后来的 SQLite Provenance 或严格评估资格管线。

初始 CourseMaterial 只有识别、类型、week、course_date、来源与处理状态等字段；初始 `Misconception` 是带 `SUSPECTED/ACTIVE/IMPROVING/RESOLVED/RECURRING` 的模型。**模型类声明与持续维护误解状态的实际服务是不同的完成度。**

**源码证据：** `93e3680:backend/app/main.py`；`93e3680:backend/app/llm/client.py`；`93e3680:backend/app/domain/learning/models.py`；`93e3680:backend/app/domain/student/models.py`；`93e3680:backend/app/domain/course/models.py`；`93e3680:docs/02_learning_objective_evidence_student_state.md`。

## 03｜V0.1 的目标：从 Evidence Events 推导一个状态

初始 `docs/03_state_update_engine.md` 只有 791 字节，写明状态 **NEXT**，列出尚未解决的问题，例如一次独立成功应改变多少状态、怎样对辅助成功加权、冲突证据如何结合、什么时候维持 Unknown。下一次历史版本 `0dda011:docs/03_state_update_engine.md` 扩为 1,581 行 **V0.1 Design Candidate**；这属于设计文档，不是生产实现。

V0.1 设计的核心不变量是 deterministic、order independent、duplicate safe、evidence traceable、Unknown 可成立、状态可升降、缺乏新证据不是负面证据。设计将 Evidence 分为可参与表现推断的 Performance Evidence、只提供上下文的 student question/self-report/teacher observation、以及用于模型纠偏的 student dispute。特别注意：**保留一条事件 ≠ 允许它改变掌握判断**。

V0.1 的候选计算方案围绕 `evidence_strength ∈ [-1,1]`：

```text
effective_strength_i = evidence_strength_i
                     × model_confidence_i
                     × recency_weight_i
                     × evidence_type_weight_i
positive_mass = Σ max(effective_strength_i, 0)
negative_mass = Σ max(-effective_strength_i, 0)
state_score = positive_mass / (positive_mass + negative_mass)
```

若总 mass 为 0，设计要求 `state_score=None`。候选 confidence 使用 quantity、session diversity、recency、consistency 的显式加权和；需要最少两条 eligible evidence、mass≥0.75 才离开 UNKNOWN；COMPETENT、STRONG 还有独立完成次数、跨会话、transfer/retrieval 等额外 gate。**这些数值是旧设计的启发式参数，不能当成经教育实验校准的掌握概率。**

### 初始 V0.1 的一处重要架构问题（事后设计分析）

在旧方案中，有符号的 `evidence_strength`、对结果解释的 `model_confidence`、时间衰减、证据数量、学生是否独立完成，容易在同一个数值周围相互混合。即使评分很高，也需要额外 gate，说明**表现得分和证据是否充分是两个不同问题**。这不是我们找到了一份当时的异常日志，而是直接对比两个设计版本可见的建模方向变化。

**源码证据：** `93e3680:docs/03_state_update_engine.md`（NEXT）；`0dda011:docs/03_state_update_engine.md`（§3、§5–17、§38–40）。

## 04｜f61cd4b 到底改了什么？不是“整个旧文档重写”

本次资料包允许精确比较 `0dda011:docs/03_state_update_engine.md` 与 `f61cd4b:docs/03_state_update_engine.md`：后者**只在文件顶部增加四行提示**，说明此文件为历史 V0.1 Design Candidate、被 `03b_state_update_engine_v0.2.md` 取代，保留供比较；其余旧设计正文保持不变。真正的新设计在新增的 `docs/03b_state_update_engine_v0.2.md`（1,112 行）中。

这很重要：未来读者看到 `03_state_update_engine.md` 的高页数，不能误以为 f61cd4b 的大改都发生在这个旧文件；不能把旧文件中的 V0.1 数值当作 V0.2 的当前规范。

| 主题 | V0.1 候选设计 | V0.2 候选设计 |
|---|---|---|
| 聚合量 | Signed `evidence_strength` 的正负质量比例 `state_score` | `correctness` 的加权平均 `performance_estimate` |
| 证据质量 | 聚合了 recency、类型及模型 confidence；另算 confidence | `diagnostic_weight = assistance × novelty × type × interpretation`；另算 `evidence_support_score` |
| 时间 | 旧证据通过 recency 影响聚合权重 | **recency 不改变 performance_estimate**；另报告 freshness |
| 最小证据 | ≥2 eligible events、mass≥0.75 | ≥2 distinct valid assessment items、mass≥0.75 |
| COMPETENT | score/confidence + ≥1 independent success | performance≥0.75 + ≥2 independent successful **distinct items** + novelty gate |
| STRONG | 旧 score/confidence + independence/session + transfer 或 retrieval | performance≥0.90 + ≥3 independent items + ≥2 sessions + objective-aligned transfer 或 delayed retrieval |
| 可追溯性 | evidence ID、policy version 等原则 | 显式 included/excluded IDs、排除理由、scoring policy version、as_of |

**设计理由必须分层表达：** 文档明确写出 V0.2 要区分 Performance Estimate、Evidence Support、Performance Stability 和 Evidence Freshness，并规定自评不能直接变成表现证据；从工程角度，这减少了“分数高 = 证据强”“时间久 = 已遗忘”的混淆。**我们未找到 f61cd4b 提交前的原始讨论或失败日志，不能进一步编写开发者当时的心理活动或虚构决策会议。**

**源码证据：** `0dda011:docs/03_state_update_engine.md`；`f61cd4b:docs/03_state_update_engine.md`；`f61cd4b:docs/03b_state_update_engine_v0.2.md`（§2、§8–18、§19–23、§26–29）。

## 05｜V0.2 的数据合同：为什么需要新建 `state_v02.py`

`2de3b83` 的 `EvidenceEventV02` 使用 Pydantic `BaseModel`，`ConfigDict(frozen=True, extra="forbid")`，用于阻止普通字段修改和意外注入未声明字段（**不是数据库不可篡改保证**）。它在旧模型身份信息之外增加 `assessment_item_id`、`response_group_id`、`objective_alignment`、`assessment_validity`、`prior_solution_exposure`、`scoring_policy_version`。

`assessment_item_id` 让系统知道两条记录是否来自同一道题；`response_group_id` 用于标记不同题号下同一次相关回应；`objective_alignment` 防止把背定义的成绩当成解题应用目标的证据；`assessment_validity` 防止无效题进入聚合；`prior_solution_exposure` 防止“看过解答后没有再请求 Hint”被简单解释为独立完成。`assistance_level=None` 与 `prior_solution_exposure=None` 都保留未知条件，不得在解释中默认为 0/False。

`ObjectiveStateV02` 不再暴露旧的 `state_score`/`confidence` 字段，而是明确区分 `performance_estimate`、`evidence_support_score`、`evidence_support`、`performance_stability`、`evidence_freshness`，并保留 `included_evidence_ids`、`excluded_evidence_ids`、`exclusion_reasons`、`policy_version`、`scoring_policy_version` 和 `as_of`。这个结构是**可解释的派生快照**，不是原始事实表。

两个时间字段 `EvidenceEventV02.created_at` 和 `ObjectiveStateV02.as_of` 有 timezone-aware validator；估计器后续还将拒绝 `created_at > as_of` 的未来事件。**这说明时间语义在早期就被写入设计与代码，但不能把后来的 CLI 提交后时间戳 Bug 写成此时已发生。**

`90b83fa` 的 Schema 相比 `2de3b83` 又增加 `retrieval_delay_hours: float | None`，要求非负，`None` 表示延迟尚未确立。没有明确延迟就不能把一次普通 retrieval 自动当成 delayed retrieval。

**源码证据：** `2de3b83:backend/app/domain/learning/state_v02.py`（`EvidenceEventV02`、`ObjectiveStateV02`）；`90b83fa:backend/app/domain/learning/state_v02.py`（`retrieval_delay_hours`）。

## 06｜Eligibility 是事件级筛选，不是 Student State 本身

`2de3b83:backend/app/services/student_model/eligibility_v02.py` 定义冻结的 `EvidenceDecision(eligible, reason, diagnostic_weight)`，以及 `evaluate_evidence(event, policy)`。判断顺序如下；**顺序会决定多个异常同时存在时首先返回的 `reason`**：

```text
EvidenceEventV02
  → Evidence Type 必须是 performance 类型
  → objective_alignment == DIRECT
  → assessment_validity == VALID
  → outcome != neutral 且 correctness 存在
  → assistance_level != None
  → assessment_item_id 存在
  → model_confidence ≥ policy.min_model_confidence
  → 计算 diagnostic_weight
  → weight > 0 ? ELIGIBLE : EXCLUDED
```

候选权重为 `assistance_weight × novelty_weight × evidence_type_weight × model_confidence`，最后裁剪到 `[0,1]`。例如已知 `assistance_level=2`、`novelty=similar`、`problem_attempt`、`model_confidence=1.0`，单次候选 weight 为 `0.60×0.75×1.00×1.00=0.45`。这是 **算权重的示例，不是一次真实学生成绩**。

重要语义：`assistance_level=None` 会返回 `assistance_level_unknown`；而 `assistance_level=2` 并非“完全没有教学价值”，在其他条件合格时仍可进入**表现估计**，但是不算独立成功。`assistance_level=6` 的权重为 0，会返回 `zero_diagnostic_weight`。**早期代码没有验证外部帮助条件的能力：记录中的 `0` 是模型字段值，不应被向用户宣传为监考证明。**

`prior_solution_exposure=True` 时，eligibility 将 novelty weight 限制至 repeated 的权重上限，并不是简单删除全部事件；在 State Estimator 中，独立成功条件又明确要求 `prior_solution_exposure is False`。这是两个不同规则：**允许谨慎保留表现信息，不把它提升为独立完成。**

### 实现修订：拒绝自相矛盾的 Outcome 与 Correctness

精确比较 `2de3b83` 与 `90b83fa` 的 `eligibility_v02.py`：后者新增 `inconsistent_outcome_correctness` 检查，例如 `outcome="failure"` 但 `correctness=1.0`、`success` 但 `correctness!=1.0`、`neutral` 却有数值成绩。否则同一条记录可能在标签上失败、数值上成功，并被当作正面证据。**这里有可确认的代码修订和新增回归测试；当前 ZIP 不包含当时失败的 Terminal 日志，因此只能称为「已证实的防护修订」，不能虚构为“线上 Bug 曾造成了错误掌握结论”。**

**源码证据：** `2de3b83:backend/app/services/student_model/eligibility_v02.py`；`90b83fa:backend/app/services/student_model/eligibility_v02.py`；同两个 Commit 的 `backend/tests/test_evidence_policy_v02.py`。

## 07｜Policy 不是教育科学事实，而是版本化工程参数

`StatePolicyV02` 使用冻结 dataclass，默认包含 `min_model_confidence=0.65`、`minimum_evidence_mass=0.75`、`minimum_distinct_items=2`、`competent_threshold=0.75`、`strong_threshold=0.90`、`competent_independent_successes=2`、`strong_independent_successes=3`、`strong_minimum_sessions=2`、`max_session_evidence_mass=1.5`、`stale_after_days=21`。

`90b83fa` 又新增 `min_retrieval_delay_hours=24.0`。将这项参数明确写入 Policy 的好处是延迟检索的资格不是由函数中不可见的临时常量决定。**0.65、1.5、21 天、24 小时都属于原始文档声明的暂定工程策略，不能在网站里叙述为经过实验验证的通用学习阈值。**

有一个后续审计关注点：`StatePolicyV02` 是冻结 dataclass，但在这份历史实现的 `estimate_objective_state` 入口中，显式验证了 `as_of` 与 `max_session_evidence_mass>0`，并没有展示对所有阈值之间逻辑关系的统一初始化验证。这是 **事后代码审阅问题**，不是已知的历史失败。

**源码证据：** `2de3b83:backend/app/services/student_model/policy_v02.py`；`90b83fa:backend/app/services/student_model/policy_v02.py`。

## 08｜逐步走过 `estimate_objective_state()` 的实际执行过程

这是 `90b83fa:backend/app/services/student_model/state_update_v02.py` 中的真实早期实现。它不调用 LLM，也不直接访问数据库；接收已经构造的 `EvidenceEventV02[]`，对指定学生、课程、目标、`as_of` 生成 `ObjectiveStateV02`。以下顺序严格对应历史源文件的 13 个 `STEP`。

**STEP 0｜校验时间与 Policy。** `as_of` 必须有时区，`max_session_evidence_mass` 必须为正数。时区不是显示偏好，而是为了保证时间排序与未来事件判断有一致含义。

**STEP 1｜验证 Scope，按 evidence_id 去重。** 每条事件的 student/course/objective 必须与请求一致，`created_at` 不得晚于 `as_of`。相同 `evidence_id` 且整条事件相同可以重复出现，但不能增加证据；相同 ID、不同内容抛出 `ValueError`，不能悄悄挑选一个版本。

**STEP 2｜Eligibility。** 按 `created_at UTC + evidence_id` 的确定性顺序逐条调用 `evaluate_evidence`。不合格事件保留 `exclusion_reasons`；合格事件按 `(session_id, assessment_item_id)` 分组。**排除是从状态计算中排除，不是删除原始 Evidence History。**

**STEP 3｜控制相关证据。** 对同一 session+item 选最早的 eligible attempt；后续同题事件标记 `correlated_repeat_in_session`。接着对同 session 的相同 `response_group_id` 再去重，标记 `correlated_response_group_in_session`；不同 session 的相同 response group 不会被这个规则跨会话合并。该策略控制同一会话多次重复的权重，并不证明不同 session 的两条记录一定在真实世界中相互独立。

**STEP 4｜Session Cap。** 汇总每次会话的 candidate weights，如果某会话超过 `max_session_evidence_mass=1.5`，对其所有被选中的事件同比例缩放。这样同一会话大量低差异题目不能无限积累 aggregate mass。缩放后的 weight 才参与下一步。

**STEP 5｜Performance Estimate。** 实际计算是 `sum(weight_i × correctness_i) / sum(weight_i)`，使用 `math.fsum`；总质量为零时为 `None`。**correctness 表示该题评分，不是 mastered 的概率；performance_estimate 也是原始策略下的表现估计，而非科学校准的学生能力概率。**

**STEP 6｜Diversity 与 Independent Success。** 统计 distinct item、session；独立成功辅助函数的必要条件为 success、correctness≈1、assistance_level==0、`prior_solution_exposure is False`。注意这里的 *independent* 是代码元数据定义；是否真的没有外部帮助，历史函数无法证实。

**STEP 7｜Transfer / Retrieval。** 成功 Transfer 要求 `EvidenceType.TRANSFER_ATTEMPT`、通过独立成功条件、`novelty="novel"`。Delayed Retrieval 除通过独立成功条件，还要求 `retrieval_delay_hours >= policy.min_retrieval_delay_hours`。没有延迟字段或延迟不足的普通 retrieval，不满足该 Strong gate。

**STEP 8｜State Gates。** 若 mass 为零、distinct items<2 或 mass<0.75，状态为 UNKNOWN。否则 estimate<0.40 对应 EMERGING；estimate<0.75 对应 DEVELOPING；更高表现仍需独立 item / novelty 才能进入 COMPETENT，STRONG 还需三道 distinct independent items、跨两次 session，并有相应 Transfer 或 Delayed Retrieval。独立成功条件不满足的高成绩可停在 DEVELOPING。

**STEP 9｜Evidence Support。** `support_score = min(mass/3,1) × min(distinct_items/3,1)`；UNKNOWN 时 support 为 INSUFFICIENT；其余根据工程阈值分为 LIMITED、MODERATE、SUBSTANTIAL。它不是另一个意义不明的“学生能力分数”。

**STEP 10｜Performance Stability。** 小于两条合格评分 → INSUFFICIENT_DATA；最高与最低 correctness 差距≥0.50 → MIXED；否则 CONSISTENT。这里“稳定”是基于有限证据的离散判别，不等于跨时间的学习保持已经被证实。

**STEP 11｜Freshness。** 根据最近满足 assistance 0 且 prior exposure False 的合格 assessment 日期判断是否超过 21 天；时间流逝只改变 freshness，不直接改变 performance_estimate 或 state。这里统计的最后一次“independent assessment”并不要求成功，且仍依赖存入事件的元数据，不能直接等同于经外部认证的独立作答。

**STEP 12｜Scoring Version 检查。** 如果参与聚合的事件出现多个 `scoring_policy_version`，抛出 `ValueError`，要求显式迁移。不同评分规则不能被悄悄揉成一个可比较成绩。

**STEP 13｜构建可追溯状态。** 输出当前 state、performance、support、stability、freshness、质量与计数、纳入/排除的 evidence IDs、reason codes、policy/scoring version 和 as_of。没有新的数据采集、用户授权或 LLM 判断发生在这个纯估计函数里。

```text
EvidenceEvent[]
  → validate scope and as_of
  → deduplicate by evidence_id
  → event-level eligibility / reason codes
  → same item & response-group correlation controls
  → per-session weight cap
  → weighted performance estimate
  → independent / transfer / retrieval counts
  → minimum evidence & higher-state gates
  → support / stability / freshness
  → ObjectiveStateV02 + provenance
```

**源码证据：** `90b83fa:backend/app/services/student_model/state_update_v02.py`（`estimate_objective_state`、`_independent_success`、`_time_key`）。

## 09｜三组具体数值例子：为什么“答对”不等于“COMPETENT”

以下为**根据历史规则人工构造的解释用例，并非运行记录**，不是原始学生数据；假设题目直接对齐目标、valid、model_confidence=1、题目 ID 相异、没有 prior exposure，除特别注明外 novelty=novel，且没有其他约束。

**A：只有一道独立新题答对。** 事件的 weight=1，weighted correctness=1，因此 performance_estimate=1；但 distinct items=1，小于 2，最终 `UNKNOWN`。这不是认定学生“不会”，而是证据数量不足。

**B：两道独立新题答对。** 在同一 session 下，原始 weight=1+1=2，session cap 1.5 将每条缩到 0.75；mass=1.5，performance_estimate=1，两个不同 item、两个独立成功、novelty gate 通过，因此 `COMPETENT`。由于 Strong 至少要求三道独立 item 和两个 session，这里不是 STRONG。

**C：五次 Hint Level 2 后在五个不同 session 对不同新题答对。** 每条 weight=0.60，mass=3、performance_estimate=1、distinct items=5，但独立成功数为 0，最终 `DEVELOPING`。**这里说明早期 V0.2 的已知辅助成功在条件齐备时可参与表现估计，但不能代替独立成功；它与后期 `assistance_level=None` 被完全排除是不同情况。**

## 10｜现有历史测试究竟证明了什么？

`2de3b83:backend/tests/test_evidence_policy_v02.py` 包含九个定义明确的 `test_` 函数，覆盖独立新题、辅助降低权重、完整 Walkthrough 权重 0、self-report、未对齐、低解释置信、缺失 Assessment ID、Solution Exposure、无效 Assessment。

在 `90b83fa` 的同名测试中新增三项：矛盾的 outcome/correctness 被排除；有效 failure 仍可保留为负面表现；合法 partial result 仍可计入。历史的 `test_state_update_v02.py` 另有 20 个 `test_` 函数，覆盖无证据、自评、单次成功、COMPETENT/STRONG、延迟检索、辅助成功、同题重复、重复 ID 冲突、输入顺序、时间流逝、真实失败导致状态下降、跨学生数据、未来数据、Solution Exposure、Response Group 与矛盾证据等。

**这 9+3+20 是本资料包中可静态数出的测试函数数量，不是我们在当前沙箱或你的最新仓库实际执行 pytest 的结果。** 此处不声明某一历史 Commit 的完整测试总数，除非找到当时原始 Terminal 输出。`test_...` 的存在证明有预期行为的代码化断言，是否每个历史版当时通过，还应以相关 Checkpoint 的实际测试输出确认。

### 有原始代码修改证据，但暂时没有失败日志的“修复”

| 观察 | 确认依据 | 可以写成什么 | 不可以写成什么 |
|---|---|---|---|
| 新增 Outcome/Correctness 一致性校验 | 两次历史版 eligibility 文件差异 + 对应新增测试 | “实现阶段增加了防自相矛盾记录的资格校验” | “曾发生某次线上错判并导致学生状态污染” |
| 新增 retrieval_delay_hours 和 ≥24h 规则 | Schema、Policy、Estimator 与延迟检索测试 | “实现中将普通检索与有明确延迟的检索分离” | “开发期间发生某个已复现的延迟计时故障” |
| 从 signed strength 转为 weighted correctness | 旧设计与新设计文档 | “确认发生的架构/模型规范变化” | “此前线上模型失效，迫使团队重构” |

## 11｜事后代码审阅：下一轮应继续核查，而不是倒写成历史 Bug

以下为当前上传 **早期历史代码** 的边界与可讨论点，不能未经最新 HEAD 和原始 Bug 日志核对就认定为当前系统缺陷：

1. `_independent_success` 根据事件元数据 `assistance_level==0` 与 `prior_solution_exposure is False` 判定；其字段来源及用户外部帮助并不在这个纯估计函数的验证范围内。
2. 同题重复按 `(session_id, assessment_item_id)` 合并；跨 session 的同题作答并不会被这一规则完全视为相同历史暴露，后续应核查不同下游是否有额外限制。
3. response group 的相关性判断同样限定在 session 内；不同 session 共用 group ID 的数据不会在这个步骤中去重，测试亦明确覆盖该设计。
4. `Pydantic frozen=True` 约束模型赋值，不保证持久层不可更改；具体数据库写入保护属于更晚的工程阶段。
5. `EvidenceSupportScore`、`model_confidence` 与 `PerformanceEstimate` 具有不同含义；不应向用户将任何一项呈现为经校准的“掌握概率”。

这些检查项应在本网站后续的 **Architecture Evolution / Current-State Audit** 中与 HEAD 代码对照，而不是混入早期历史 Debugging Case。

## 12｜能够确认的历史节点与剩余证据缺口

| Git 节点 | 本资料包直接提供的内容 | 仍未提供的内容 |
|---|---|---|
| `93e3680` | 产品/架构/课程/教学/隐私文档；最初 Domain Model、FastAPI 入口与 LLM Protocol | 完整初始执行日志、实际课程导入或教学演示记录 |
| `0dda011` | 1,581 行的 V0.1 State Update 设计候选 | 提交前各次讨论、曾经失败的实现尝试 |
| `f61cd4b` | 旧文档仅加四行 superseded 提示；新增 1,112 行 V0.2 设计 | 当时变更决策的逐次讨论与实验输出 |
| `2de3b83` | Schema、Eligibility、Policy、九个测试函数 | 对应 Commit 的原始 pytest 输出、此前未提交的错误尝试 |
| `90b83fa` | State Estimator、Schema/Policy/Eligibility 修订、测试函数 | 原始失败日志、提交前修改次数、当时总测试结果 |

**后续网站编排：** 本章应作为「Foundation / Early Student State」的完整技术内容，与 `Implementation 0–13` 编号索引分开，直到取得能够直接确定每个 Implementation 边界的原始 Roadmap。下一轮可沿真实 Commit 顺序继续 Assessment / Evidence Scoring，而不是依据文件名猜测实施编号。

## 附｜如何复核本章中的每条历史陈述

在 URPP 仓库根目录，使用只读 Git 命令查看具体版本，例如：

```bash
git show 93e3680:docs/00_product_spec.md
git show 0dda011:docs/03_state_update_engine.md
git show f61cd4b:docs/03b_state_update_engine_v0.2.md
git show 2de3b83:backend/app/services/student_model/eligibility_v02.py
git show 90b83fa:backend/app/services/student_model/state_update_v02.py
git diff 2de3b83 90b83fa -- backend/app/services/student_model/eligibility_v02.py
```

原始资料包中的历史文件也可直接从 `early_architecture_source_pack.zip` 复核。**本章不包含真实学生数据，不运行 URPP 程序，不修改证据规则，不推断尚未验证的开发事故。**
