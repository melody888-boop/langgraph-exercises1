# LangGraph 练习作品集（Agent 开发入门）

> 用 LangGraph 从零手写的四个小项目，从"单 Agent 状态图"一路练到"多智能体 + 人工审核发布流水线"，
> 覆盖状态图、条件分支、工具节点、人工审核（Human-in-the-loop）、并行分叉（Send）、反思循环与检查点（Checkpointer）等核心机制。
> 全部**离线可运行**，不需要任何 API Key。

---

## 项目 1：迷你客服 Agent（`exercise1_mini_kefu.py`）

**一句话**：一张纯规则的状态图——听懂用户意图，分流到"政策问答"或"查订单"，自动回复。

```
用户输入 → parse_input（意图识别）
              ├─ faq   → faq_answer（知识库关键词检索 → 回答）
              └─ order → order_lookup（按订单号查表 → 回复）
```

**用到的 LangGraph 机制**：
- `StateGraph` + `State`（TypedDict）
- `messages` 字段用官方 `add_messages` reducer（多轮对话记忆）
- 条件边 `add_conditional_edges`（按 intent 分流）
- `compile(checkpointer=InMemorySaver())`（同线程多轮记忆）

## 项目 2：订单助手升级版（`exercise2_订单助手升级.py`）

**一句话**：在项目 1 基础上加入"计算器工具节点"、"退款人工审核"与"检查点历史查看"。

**用到的 LangGraph 机制**：
- **新意图 + 新节点**：计算器（`calculator`）——从用户话里提取数字与运算并计算结果
- **Human-in-the-loop**：`interrupt()` 暂停图，把审核单抛给审核员；`Command(resume=...)` 恢复执行——退款必须经人工确认才真正修改订单状态
- **检查点历史**：`graph.get_state_history()` 查看线程的所有快照（`next` / `values`）——时间旅行（Time-Travel）的第一步

```
用户："我要退款，订单号 A001"
   ↓
refund_request 节点 → interrupt(payload)   ← 图暂停，等待人工审核
   ↓（审核员在终端输入 y / n）
Command(resume="y") → 图继续 → 订单状态改为"已退款"
```

## 项目 3：多智能体写作小队（`exercise3_多智能体写作.py`）

**一句话**：输入水果名，多个 Worker 用 Send 并行各写一段，Editor 汇合拼稿，Critic 审稿打回重写。

**用到的 LangGraph 机制**：
- `Send` 动态 fan-out：planner 拆出子任务 → 每个子任务派一个并行 Worker
- reducer（`operator.add`）：多个 Worker 的段落自动累加进 `pieces`
- fan-in：所有 Worker 完成后 editor 只执行一次
- 反思循环：critic 打低分 → 带批语回 editor 重写，`iterations` 上限防死循环

```
planner 拆 3 部分 → Send ×3 → worker ×3（并行写段）→ pieces[] 累加
  → editor（fan-in 拼稿）→ critic（缺总评 → 打回）→ editor 第 2 稿补总评 → 通过
```

## 项目 4：水果介绍"发布流水线"（`exercise4_发布流水线.py`）

**一句话**：在项目 3 基础上加"人工审核发布"——critic 多项打分循环后，稿子经真人（interrupt）确认才发布。

**用到的 LangGraph 机制**：
- **机器初审 + 人工终审**：critic 多项检查打分（缺段 / 缺总评 / 太短逐项扣分）→ 达标后进入 human_review
- **Human-in-the-loop 放进多智能体流程末尾**：`interrupt()` 暂停整条流水线，真人输 y/n 决定发布或驳回，`Command(resume=...)` 恢复
- 自动化验收：脚本用 `Command(resume="y"/"n")` 代替人工点测，逐条打印 ✅/❌
- `get_state_history` 查看整条流程存档（含 interrupt 暂停点）

```
planner → Send ×3 → worker → editor → critic（多项打分循环，最多 3 稿）
  → human_review（interrupt，真人 y/n）→ 发布 / 驳回 → END
```

## 运行方法

```bash
# 1. 安装依赖（只需 LangGraph）
pip install -r requirements.txt

# 2. 运行各项目
python exercise1_mini_kefu.py                    # 项目 1：迷你客服
python exercise2_订单助手升级.py                  # 项目 2：退款需你输入 y / n
python exercise3_多智能体写作.py                  # 项目 3：写作小队
python exercise4_发布流水线.py                    # 项目 4：底部 main()=手动审核 / 自动验收()=自动检查
```

> 四个项目都是单文件、无外部依赖（除了 LangGraph），也没有任何大模型调用，**纯离线运行**，方便快速演示与讲解。

## 环境要求

- Python 3.10+
- 依赖见 `requirements.txt`

## 说明（重要，写给自己也写给看的人）

这组项目是我学习 LangGraph 阶段的"练功房"作品，**刻意由浅入深、做成一条练习链**：

1. 迷你客服 → 学会"从零组装一张状态图"
2. 订单助手 → 学会"加工具节点 + interrupt 人工审核 + 看历史"
3. 写作小队 → 学会"Send 并行 fan-out / fan-in / 反思循环"
4. 发布流水线 → 学会"把以上机制组合成一条带人工终审的完整流水线"

它们**不是**最终的作品集大项目，而是理解下面这些概念的载体——面试时我能对着代码讲清楚：

- 为什么用 Graph 而不是 LCEL 链/if-else：状态显式、可检查点、可中断恢复、可回放
- `interrupt()` 与 `Command(resume=...)` 的"暂停—恢复"机制，以及它作为"通用暂停键"可放在图里任何需要人把关的位置（机器初审 + 人工终审）
- `Send` fan-out 与 reducer fan-in：多智能体并行协作与结果汇合
- 反思循环如何用评分 + 稿数上限控制"改到满意为止"
- `add_messages` / reducer 与消息协议的关系
- `get_state_history` 与时间旅行（回到历史检查点、`update_state` 修改、重新执行）
