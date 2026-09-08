# LangGraph 练习作品集（Agent 开发入门）

> 用 LangGraph 从零手写的两个小项目，展示状态图、条件分支、人工审核（Human-in-the-loop）与检查点（Checkpointer）等核心机制。全部**离线可运行**，不需要任何 API Key。

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

## 运行方法

```bash
# 1. 安装依赖（只需 LangGraph）
pip install -r requirements.txt

# 2. 运行项目 1
python exercise1_mini_kefu.py

# 3. 运行项目 2（退款演示需要你在终端扮演审核员，输入 y / n）
python exercise2_订单助手升级.py
```

> 两个项目都是单文件、无外部依赖（除了 LangGraph），也没有任何大模型调用，**纯离线运行**，方便快速演示与讲解。

## 环境要求

- Python 3.10+
- 依赖见 `requirements.txt`


这两个项目是我学习 LangGraph 阶段的"练功房"作品：**刻意做得小而清晰，目的是亲手打通一张图的完整链路**（状态定义 → 节点 → 条件边 → 编译 → 多轮记忆 → 人工审核 → 查看历史快照）。

它们**不是**最终的作品集大项目，而是理解下面这些概念的载体——面试时我能对着代码讲清楚：

- 为什么用 Graph 而不是 LCEL 链/if-else：状态显式、可检查点、可中断恢复、可回放
- `interrupt()` 与 `Command(resume=...)` 的"暂停—恢复"机制，以及生产环境如何把它包装成网页人工审核
- `add_messages` / reducer 与消息协议的关系
- `get_state_history` 与时间旅行（回到历史检查点、`update_state` 修改、重新执行）
