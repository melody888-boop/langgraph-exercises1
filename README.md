# LangGraph 练习作品集（Agent 开发入门）

> 从零手写的六个 LangGraph 小项目，由浅入深串成一条练习链：
> **状态图 → 工具节点 + 人工审核 → 多智能体并行 + 反思循环 → 人工终审发布 → 工具调用循环（ReAct）→ 接入真模型**。
> 覆盖 StateGraph、条件边、reducer、checkpointer、Send 并行（fan-out/fan-in）、反思循环、
> Human-in-the-loop（interrupt）、Tool Calling（tool_calls / ToolMessage）等核心机制。

---

## 项目 1：迷你客服 Agent（`exercise1_mini_kefu.py`）

**一句话**：一张纯规则的状态图——听懂用户意图，分流到"政策问答"或"查订单"，自动回复。

```
用户输入 → parse_input（意图识别）
              ├─ faq   → faq_answer（知识库关键词检索 → 回答）
              └─ order → order_lookup（按订单号查表 → 回复）
```

**机制**：`StateGraph` + `State`(TypedDict)、`messages` 用官方 `add_messages`（多轮记忆）、
条件边分流、`compile(checkpointer=InMemorySaver())`。

## 项目 2：订单助手升级版（`exercise2_订单助手升级.py`）

**一句话**：加入"计算器工具节点"、"退款人工审核"与"检查点历史查看"。

**机制**：
- 新意图 + 新节点：计算器（从用户话里提取数字与运算）
- **Human-in-the-loop**：`interrupt()` 暂停 → 审核员确认 → `Command(resume=...)` 恢复（退款必须人工确认才改数据）
- **检查点历史**：`get_state_history()` 查看线程全部快照（时间旅行的第一步）

## 项目 3：多智能体写作小队（`exercise3_多智能体写作.py`）

**一句话**：输入水果名，多个 Worker 用 Send 并行各写一段，Editor 汇合拼稿，Critic 审稿打回重写。

**机制**：`Send` 动态 fan-out、`operator.add` reducer 累加、fan-in 汇合、
反思循环（critic 打分 → 回炉重写，`iterations` 上限防死循环）。

## 项目 4：水果介绍"发布流水线"（`exercise4_发布流水线.py`）

**一句话**：在项目 3 基础上加"人工审核发布"——critic 多项打分循环后，稿子经真人（interrupt）确认才发布。

**机制**：critic 多项检查打分（缺段 / 缺总评 / 太短逐项扣分）、
**机器初审 + 人工终审**、`interrupt` 放进多智能体流程末尾、脚本化自动验收（`Command(resume="y"/"n")` 代替人工点测）。

## 项目 5：手写工具调用循环（`exercise5_工具调用循环.py`，离线）

**一句话**：用"规则假模型"代替真模型，手写 ReAct 工具循环——练机制，不花钱。

```
用户消息 → chatbot（假模型决定要不要调工具）
             ├─ 不用工具 → 直接回答 → END
             └─ 要调工具 → 返回带 tool_calls 的 AIMessage
                  → tools 节点执行 → 结果包成 ToolMessage（带 tool_call_id）回历史
                  → 回到 chatbot（循环）→ 直到不再要工具
```

**机制**：`AIMessage(tool_calls=[...])` 构造、条件边检查 `last.tool_calls`、
`func(**args)` 执行工具、`ToolMessage` 与 `tool_call_id` 配对、循环 + checkpointer。

## 项目 6：接入真模型 DeepSeek（`exercise6_真模型工具循环.py`）

**一句话**：把项目 5 的"假模型"换成真模型 DeepSeek——图的机制一字不改，只换决策者。

**机制**：
- `@tool` 装饰器（真模型需要"工具对象"：名字 + docstring 说明 + 参数 schema）
- `ChatOpenAI(model="deepseek-chat", base_url="https://api.deepseek.com/v1")` + **`bind_tools([...])`** 绑定工具菜单
- 真模型**自主决定**调哪个工具、参数填什么（Function Calling）
- 工具结果经 `ToolMessage` 回填后，模型据此给出最终回答

> 项目 5 → 6 体现了一个重要认知：**"模型"只是一个接口**（收 messages、返回 AIMessage），
> 换成真模型时，图的编排、工具节点、循环逻辑全都不用动。

## 目录结构

```
.
├── README.md
├── requirements.txt
├── .env.example                       # 项目 6 需要的密钥模板
├── .gitignore                         # 已忽略 .env
├── exercise1_mini_kefu.py
├── exercise2_订单助手升级.py
├── exercise3_多智能体写作.py
├── exercise4_发布流水线.py
├── exercise5_工具调用循环.py
└── exercise6_真模型工具循环.py
```

## 运行方法

```bash
pip install -r requirements.txt

# 项目 1~5：纯离线，不需要任何 API Key
python exercise1_mini_kefu.py
python exercise2_订单助手升级.py      # 退款环节需你在终端输入 y / n
python exercise3_多智能体写作.py
python exercise4_发布流水线.py        # main()=手动审核；自动验收()=脚本自动点测
python exercise5_工具调用循环.py      # 假模型版：不花钱练工具循环

# 项目 6：需要 DeepSeek API Key
cp .env.example .env                  # 填入 LLM_API_KEY
python exercise6_真模型工具循环.py     # 看到 🔧 行 = 真模型自主调工具成功
```

## 环境要求

- Python 3.10+
- 依赖见 `requirements.txt`：`langgraph`、`langchain-openai`、`python-dotenv`
- 项目 6 需要 DeepSeek（或任何 OpenAI 兼容服务）API Key；其余项目无需联网

## 说明（写给自己也写给看的人）

这组项目是学习 LangGraph 阶段的"练功房"作品，**刻意由浅入深、做成一条练习链**：

| 阶段 | 学到什么 |
|---|---|
| 1 | 从零组装一张状态图（State / 节点 / 条件边 / 编译） |
| 2 | 加工具节点 + `interrupt` 人工审核 + 查看检查点历史 |
| 3 | `Send` 并行 fan-out / fan-in + reducer 累加 + 反思循环 |
| 4 | 把机制组合成带"人工终审"的完整流水线 + 自动验收 |
| 5 | 手写 ReAct 工具循环（tool_calls / ToolMessage / 循环） |
| 6 | 接入真模型，用 `bind_tools` 实现 Function Calling |

它们**不是**最终的作品集大项目，而是理解下面这些概念的载体——面试时我能对着代码讲清楚：

- 为什么用 Graph 而不是 LCEL 链 / if-else：状态显式、可检查点、可中断恢复、可回放
- `interrupt()` 与 `Command(resume=...)`：作为"通用暂停键"，可放在任何需要人把关的位置（机器初审 + 人工终审）
- `Send` fan-out 与 reducer fan-in：多智能体并行协作与结果汇合
- 反思循环：评分 + 稿数上限，控制"改到满意为止"且不死循环
- Tool Calling 全流程：`@tool` → `bind_tools` → `tool_calls` → 执行 → `ToolMessage` 配对 → 循环
- "模型是接口"：假模型与真模型可互换，编排逻辑不受影响
- 工程排查经验：节点要"所有路径都 return"、字段名三处对齐、Send 任务单要带全分支所需数据
