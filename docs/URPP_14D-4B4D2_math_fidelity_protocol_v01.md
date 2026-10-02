# URPP 14D-4B4D2 — Mathematical Fidelity Evaluation Protocol v0.1

**状态：EVALUATION DESIGN / PROVISIONAL SOURCE TRANSCRIPTION，未修改 URPP 仓库、未运行模型或 pytest。**

## 1. 版本和来源

- 代码基线：`ZhenchengLin/URPP`，`design/logical-decision-engine`，远端 HEAD `076bdf4c4eeb98d341eb16f165c42bde456d7910`（准备本草案时核对）。Mac 工作区仍有独立的 MathJax 改动，不得混入本阶段。
- 学习资料：用户此前分享的 URPP Course Pack 查看器文本导出，其中包含文件 `URPP_CT_LTRI_2018_part1_pages_1-6.pdf` 的第 4、5、6 页 Extracted Text；Pack SHA-256 `fbf19109e86539e119afe8cee3acd3e9a8d812e2c334217c911263ba56dbeeb2`。本草案**尚未对照原始 PDF 的页面图像**；`/Delta1z` 一类提取痕迹不应未经核查就认定为论文的精确排版。正式的公式金标准应在原 PDF 第 4–6 页上进行视觉核对后冻结。
- 论文出处：用户资料中标注为 Ha and Mueller，*Look-Up Table-Based Ray Integration Framework*，IEEE Transactions on Medical Imaging 37(2), 2018。论文使用限制随原资料保留；本文件只记录短的数学表达式、核查条件和指向用户本地 Course Pack 的定位信息，不纳入原文长段落、真实 Session ID 或上传 PDF。
- 证据等级：以下为 **SOURCE-EXTRACTED PROVISIONAL**，不是 URPP 自动判断已证实；先前 Ollama CLI 输出属于 **PROJECT OBSERVATION**；“特定 Prompt 会提升正确率”属于待检验的 **HYPOTHESIS**。

## 2. 公式核查卡（待原 PDF 视觉确认）

| 公式 | 本地定位 | 从已保存的 extracted text 可确定的关键结构 | 不可接受的改写/遗漏 |
|---|---|---|---|
| (7) | excerpt-4，PDF 第 4 页 | `p_i^θ ≈ [1/(|sin α_i| γ_{φ,i} γ_{ϕ,i})] Σ_{n∈Ω_SBP} f[n] d_n / ||v_n−v_src||²`。`d_n` 为 ray–voxel intersection **volume**；两个 `γ` 与 `|sin α_i|` 均在**外部前因子的分母**。 | 把 `γ` 移到分子；把 `d_n` 称为无权重长度；将加权和说成简单的 `Σ f[n]`；假设本页证明了全部公式推导（原文说明推导在补充材料）。 |
| (10) | excerpt-5，PDF 第 5 页 | `h_{PL_s,top}=V_{PL_s,top}/(Δx Δy)`；底平面类似计算，两平面高度的差构成 `h_eff`，`V_overlap=S_base h_eff`。 | 把式 (10) 直接说成对**任意**体积的通用 `h=V/(Δx Δy)`，丢掉它是指定 top plane 的半空间体积和两个平面之差。 |
| (15) | excerpt-6，PDF 第 6 页 | **Regression Method** 的分段高度近似：`height=Δz/2−D_pl` 当 `0≤D_pl≤Δz/2`；否则 `0`。邻接文字出现简化角度条件 `θ_ϕ=θ_φ=0`，须核实它与式 (15) 的精确适用关系。 | 将它称作 overlap-distance method；漏掉分段条件、阈值、`D_pl` 或 `Δz/2`；把近似称为严格精确公式。 |
| (16) | excerpt-6，PDF 第 6 页 | **Distance Method**：沿穿过 voxel 中心的 common z-axis 计算重叠长度；存在 overlap 时 `h_eff=min(z⁺,t_c⁺)−max(z⁻,t_c⁻)`，否则 `0`。`t_c⁺,t_c⁻` 来自 detector-bin corners 在该轴上的投影。 | 将式 (16) 说成 regression；写成 `max(上界)−min(下界)`；忽略无重叠时为零，或把 `t_c` 误说成原始探测器 t 坐标。 |

**公式排版限制：**上表是经已保存纯文本摘录整理的可检验结构；原始 PDF 未在本轮提供。符号上下标、原文 `t±` 对应的 detector-bin edge 定义、式 (15) 的简化条件必须由原始 PDF 图片人工确认后才可升为 `HUMAN_VERIFIED_SOURCE`。不要让其他 LLM 根据这份模型转述反向补全原文。

## 3. 冻结的最小评价样本（在查看候选模型新输出之前确定）

使用相同 pinned Course Pack、模型 tag、Gateway/Prompt/Selector 版本；以独立临时工作区运行现有只读 CLI，不改原始 Session。为避免历史上下文影响，另建 synthetic 测试时须独立标明是 `single-turn` 还是 `follow-up`。

| ID | 当前请求 | 目标资料 | 主要判定 |
|---|---|---|---|
| M07-COPY | 请完整写出论文公式 (7)，保留所有乘除位置和求和符号。 | excerpt-4 | 必须给出公式；外部 `γ` 不可移到分子；结构完整。 |
| M07-EXPLAIN | 请解释公式 (7) 中交集体积、距离平方与角度归一化各在什么位置。 | excerpt-4 | `d_n` 是体积，距离平方与角因子各在正确分母，不能只描述无权重求和。 |
| M10-COPY | 写出公式 (10)，并解释两个平面高度如何得到 `h_eff`。 | excerpt-5 | 指定 top-plane 高度；高度差；不把近似体积方法称为精确体积公式。 |
| M15-COPY | 请写出式 (15) 的完整分段公式、阈值和方法名称。 | excerpt-6 | Regression Method；`D_pl` 和 `Δz/2`；分段完整。 |
| M16-COPY | 请写出式 (16) 的完整分段公式、变量含义和无重叠分支。 | excerpt-6 | Distance Method；正确 min/max；否则 0；`t_c` 为投影端点。 |
| M15-M16 | 式 (15) 和 (16) 分别是什么方法？把两条完整公式写出来。 | excerpt-6 | 两方法不互换；两条都给出；不只用概述代替公式。 |
| M07-MISSING | 只提供不包含公式 (7) 的受限 excerpt 时，请抄出式 (7)。 | 无足够来源 | 不可伪造方程、引用或把其他页说成式 (7)；应返回不足证据。 |
| M07-FOLLOW | 上轮问“论文有哪些数学公式”，本轮问“把 function 发给我”。 | bounded 4–5 页 | 如果范围不能覆盖全篇，须指出未覆盖，询问需要哪些公式或给出**本轮已提供来源**中的代表式；不可声称全部公式已经展示。 |

## 4. 两层验收（相互独立）

**L1 Engineering / 机器可验：**请求中仅包含已授权完整 excerpt；合法 JSON 与状态；Source ID 是本轮集合成员；无关来源不可填充；损坏 JSON 有界重试；失败与 CLI 复测不可写原始 DB；新的测试不能通过削弱旧 Contract 获得绿色。

**L2 Mathematical / 对照原文：**由人或独立审核者根据冻结的原 PDF 公式逐条检查：A. 用户要求写公式时是否真正写出；B. 分子/分母与求和位置；C. 方法名称、变量定义、适用条件；D. 不明确之处是否如实表示不足证据。任一关键数学关系反转、凭空补全或引用范围错误，`L2=FAIL`，即使 `L1=PASS` 也不得称为已核验课程解释。

L2 记录每项为 `PASS / FAIL / NOT_ASSESSABLE`，另记 `error_category` 为 `formula_structure / variable_definition / applicability / answer_omission / attribution / unsupported_claim / extraction_ambiguity`。不依赖只搜索固定 LaTeX 子串：同一数学表达式可能有等价排版，但要严格核对数学关系。自家 LLM 对自己的输出判分只能用作候选初筛，不能作为最终金标准。

## 5. 已观察故障与后续实验（不改旧事实）

- 先前真实 CLI：公式 (7) 的 `γ` 被写在外部前因子的分子；另一回答把加权求和解释成无权重总和。**L1 通过，L2 失败。**
- 先前真实 CLI：式 (15)/(16) 的请求第一次出现 invalid JSON escape；一次修复后 L1 通过，但模型只给两种方法的概述而未抄出两条公式，**L2 的 answer_omission 失败**；式 (15) 的方法名称与重叠距离概念有混淆风险。
- 待测 H-MATH-01：针对明确索取公式的请求，加入“保持源公式形状，不确定时拒答”的有界教学提示，是否降低 L2 严重错误率？对照当前固定版本，复用同一评估清单和原 PDF，记录正确率、拒答率、失败类别、生成 tokens 与延迟；结果不达标不启用。
- 待测 H-MATH-02：从经过人工核对的 `EquationRecord`（公式标签、原文定位、变量、条件、审阅版本）**确定性展示公式**，由 LLM 只负责解释，是否减少公式抄录错误？需核对记录的授权、版本与定位，不得从未验证纯文本自动授予 `reviewed` 状态。研究性原型不自动写 Student State、Evidence 或 Mastery。

## 6. 下一次实施前的退出条件

1. 取原 PDF 第 4–6 页原图并人工核对本文件的每个公式与符号，记录 PDF 原文件 SHA-256 和 `reviewed_by/at`；没有 PDF 时维持 `PROVISIONAL`，不把此稿纳入“准确率 gold”。
2. 将上表 8 个 case 固定成版本化实验 fixture；至少一组旧版本原始模型输出保留作为回归失败样本（合规且不进入公开仓库的私人文本除外）。
3. 首先只做只读评测 Harness / 报告，不改 Professor 生成链路；若决定引入 EquationRecord 或 Prompt A/B，另开有界 task card，定义失败/取消/回退与数据迁移边界。
4. 结构验收和内容验收在报告中分列，不以单个 `VALIDATED_NOT_SAVED` 代替 L2。
