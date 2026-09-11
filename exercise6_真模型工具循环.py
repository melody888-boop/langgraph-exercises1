r"""练习 6（升级版）：手写工具调用循环 —— 换成【真模型 DeepSeek】

【和练习 5 的关系】
练习 5：假模型（规则决定要不要调工具）→ 练"图的机制"
练习 6：真模型（DeepSeek 自己决定要不要调工具）→ 练"接入真实 API"
★ 图的机制（chatbot / 条件边 / tools_node / ToolMessage / 循环 / checkpointer）完全不变，
  只把 fake_model 换成 llm.bind_tools(...) —— 这就是"接口相同，替换实现"的威力。

【前置条件】
1. 根目录要有 .env（若没有：cp .env.example .env，填入你的 DeepSeek Key）
   .env 内容：
       LLM_API_KEY=sk-你的DeepSeek密钥
       LLM_BASE_URL=https://api.deepseek.com/v1
       LLM_MODEL=deepseek-chat
2. 需要装依赖（工作区 .venv 已装）：langgraph、langchain-openai、python-dotenv

【流程图（和练习 5 一样）】
用户消息
  → chatbot：把「系统提示 + 全部历史」交给【真模型】（已 bind_tools 工具菜单）
      真模型自己决定：
      ├─ 直接回答 → AIMessage(content=文字, tool_calls=[]) → END
      └─ 要调工具 → AIMessage(content="", tool_calls=[{name,args,id}])
  → 条件边：最后一条有 tool_calls？ → tools 节点
  → tools 节点：按名字执行工具（func(**args)）→ 结果包 ToolMessage（带 tool_call_id）→ 回历史
  → 回 chatbot（循环）→ 真模型看到工具结果 → 再决定……
  → 直到不再要工具 → END

【和练习 5 相比，要改的 5 处】
① 工具函数要加 @tool（★ 关键）：
      from langchain_core.tools import tool
      @tool
      def calculator(expression: str) -> str:
          '''计算一个纯数学表达式，支持 + - * / 和括号、幂。用户问数值计算时使用。'''
          ...
   为什么？真模型要靠"工具对象"里的 名字 + 说明(docstring) + 参数schema
   来决定用哪个工具 —— 这就是练习 5 里你问过的"为什么第一步没有 @tool"的答案：
   假模型不需要，真模型必须要有。
   注意：docstring 就是给模型看的"使用说明书"，要写清楚"什么时候用"。

② 新增 llm.py（或写在文件顶部）：创建真模型 + 绑定工具
      from dotenv import load_dotenv
      from langchain_openai import ChatOpenAI
      load_dotenv()
      model = ChatOpenAI(
          model=os.getenv("LLM_MODEL", "deepseek-chat"),
          api_key=os.getenv("LLM_API_KEY"),
          base_url=os.getenv("LLM_BASE_URL", "https://api.deepseek.com/v1"),
          temperature=0.1,
      )
      model_with_tools = model.bind_tools([calculator, query_order])   # ★ 工具菜单绑给模型

③ chatbot 节点：把 fake_model 换成真模型
      def chatbot(state):
          messages = [SystemMessage(content=SYSTEM_PROMPT)] + list(state["messages"])
          ai = model_with_tools.invoke(messages)      # ← 只有这一行变了！
          return {"messages": [ai]}

④ tools_node：执行工具。加 @tool 后，工具对象用 .invoke(args) 执行
      TOOL_FUNCS = {t.name: t for t in [calculator, query_order]}
      ...
      result = TOOL_FUNCS[name].invoke(args)          # 或 .func(**args) 也行
      ToolMessage(content=str(result), tool_call_id=call_id, name=name)

⑤ main：测试几个真问题（需要 API Key，会花钱——每次约 2~6 次调用）
      问 "帮我算 23 乘以 47 等于多少"   → 看到 🔧 调 calculator，回答含 1081
      问 "查一下订单 A001 什么状态"    → 看到 🔧 调 query_order
      问 "你好，你能做什么"            → 不调工具，直接回答
      连问两轮同一线程                 → 记忆生效（messages 累积）

【验收标准】
1. 出现 "🔧 调用工具: calculator(...)" 且最终回答里有正确数值 → 真模型自主调工具 ✅
2. "🔧 调用工具: query_order(...)" 且回答含订单信息 ✅
3. 纯聊天问题不出现 🔧（模型知道不需要工具）✅
4. 同一线程连续几轮，历史消息条数递增（checkpointer 记忆）✅

【小提示】
- 参考实现就在工作区：case3_tool_agent/llm.py、tools.py、agent.py
  （那是同一套真机实现，语法可以看；但建议你按上面 5 处自己改练习 5 的代码，
   体会"只换模型"这个动作）
- 真模型输出不可控：如果它不调工具直接答（或调错工具），可以
  · 把工具 docstring 写得更明确
  · 在 SYSTEM_PROMPT 里加一句"涉及数值计算必须用 calculator"
- API 报错常见原因：Key 没填/没余额/网络不通 → 报错原文贴出来即可定位
- 卡住 10 分钟 → 回来要提示（1/2/3 级）
"""
# ============================================================
# 你的代码从这行下面开始写（建议先把练习 5 的代码粘进来，再按上面 5 处改）
# ============================================================

import ast
import operator
import os
from typing import Annotated, TypedDict

from dotenv import load_dotenv
from langchain_core.messages import SystemMessage, ToolMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages

# ---------------------------------------------------------------
# 工具 1：安全计算器
# ---------------------------------------------------------------

# 订单数据（模拟数据库）
ORDERS = {
    "A001": {"item": "无线机械键盘", "amount": 399.0, "status": "已发货"},
    "A002": {"item": "蓝牙降噪耳机", "amount": 1299.0, "status": "已签收"},
}

# 白名单：允许的运算符号 → 对应的真实运算函数
ALLOWED_OPERATORS = {
    ast.Add: operator.add,      # 加号 +
    ast.Sub: operator.sub,      # 减号 -
    ast.Mult: operator.mul,     # 乘号 *
    ast.Div: operator.truediv,  # 除号 /
    ast.Pow: operator.pow,      # 幂号 **
}


def compute_node(node):
    """把一个"数学节点"算成数字（不用 eval，只允许数字 + 四则运算，更安全）。"""
    # 情况 1：节点就是一个数字，比如 23
    if isinstance(node, ast.Constant):
        value = node.value
        if isinstance(value, (int, float)):
            return value
        raise ValueError("出现了不是数字的内容")

    # 情况 2：节点是一个运算，比如 a + b 或 a * b
    if isinstance(node, ast.BinOp):
        func = ALLOWED_OPERATORS.get(type(node.op))
        if func is None:
            raise ValueError("不支持的运算符")
        left_value = compute_node(node.left)
        right_value = compute_node(node.right)
        return func(left_value, right_value)

    # 情况 3：负号，比如 -5
    if isinstance(node, ast.UnaryOp):
        if isinstance(node.op, ast.USub):
            return -compute_node(node.operand)
        raise ValueError("不支持这种一元运算")

    # 其它任何情况：一律拒绝
    raise ValueError("表达式里含有不允许的内容")


@tool
def calculator(expression: str) -> str:
    """计算一个纯数学表达式。只支持数字、+ - * /、括号和幂运算。
    当用户的问题涉及数值计算时使用；参数 expression 必须是能直接计算的数学式子。"""
    try:
        tree = ast.parse(expression, mode="eval")
        value = compute_node(tree.body)
        return str(round(float(value), 6))
    except Exception as exc:
        return "无法计算：" + str(exc)


# ---------------------------------------------------------------
# 工具 2：查订单
# ---------------------------------------------------------------

@tool
def query_order(order_id: str) -> str:
    """查询订单状态。当用户询问某个订单的情况时使用；
    参数 order_id 是订单号，例如 A001。"""
    order_id = order_id.strip().upper()
    order = ORDERS.get(order_id)
    if order is None:
        return "没有找到订单 " + order_id
    return ("订单 " + order_id + "：" + order["item"] + "，实付 ¥"
            + str(order["amount"]) + "，状态：" + order["status"])


# 工具注册表：按名字找工具对象（模型靠名字调用）
TOOL_FUNCS = {
    "calculator": calculator,
    "query_order": query_order,
}

# ---------------------------------------------------------------
# 真模型 + 绑定工具
# ---------------------------------------------------------------

load_dotenv()
model = ChatOpenAI(
    model=os.getenv("LLM_MODEL", "deepseek-chat"),
    api_key=os.getenv("LLM_API_KEY"),
    base_url=os.getenv("LLM_BASE_URL", "https://api.deepseek.com/v1"),
    temperature=0.1,
)
model_with_tools = model.bind_tools([calculator, query_order])

# ---------------------------------------------------------------
# 1. State：状态长什么样
# ---------------------------------------------------------------


class State(TypedDict):
    messages: Annotated[list, add_messages]


SYSTEM_PROMPT = (
    "你是一个电商店铺助手，手上有两个工具：\n"
    "1) calculator：涉及任何数值计算时必须使用；\n"
    "2) query_order：用户询问订单时使用。\n"
    "能用工具就用工具，回答简洁、口语化。"
)

# ---------------------------------------------------------------
# 2. 节点：图里的每个方框
# ---------------------------------------------------------------


def chatbot(state) -> dict:
    """方框①：让"会调工具的模型"基于完整历史回答一次。"""
    messages = [SystemMessage(content=SYSTEM_PROMPT)] + list(state["messages"])
    ai = model_with_tools.invoke(messages)
    return {"messages": [ai]}


def route_after_chatbot(state):
    """条件边：看模型最后一句话，是想调工具，还是已经直接回答了。"""
    last = state["messages"][-1]
    if last.tool_calls:
        return "tools"
    return "end"


def tools_node(state):
    """方框②：把模型要求的工具真正执行一遍。"""
    last = state["messages"][-1]  # 模型那条"要工具"的回复
    results = []
    for call in last.tool_calls:  # 可能一次要调多个工具
        name = call["name"]  # 工具名，如 "calculator"
        args = call["args"]  # 参数，如 {"expression": "23*47"}
        call_id = call["id"]  # 这次调用的编号

        t = TOOL_FUNCS.get(name)  # 按名字查注册表，找到工具对象
        if t is None:
            content = "没有这个工具：" + name
        else:
            try:
                content = str(t.invoke(args))  # 执行 → 结果转文字
            except Exception as exc:
                content = "工具执行出错：" + str(exc)

        print("🔧 调用工具:", name, args, "->", content)
        results.append(ToolMessage(content=content, tool_call_id=call_id, name=name))
    return {"messages": results}  # 结果追加进历史


# ---------------------------------------------------------------
# 3. 拼图：把节点连起来并编译
# ---------------------------------------------------------------

builder = StateGraph(State)
builder.add_node("chatbot", chatbot)
builder.add_node("tools", tools_node)
builder.add_edge(START, "chatbot")
builder.add_conditional_edges("chatbot", route_after_chatbot, {"tools": "tools", "end": END})
builder.add_edge("tools", "chatbot")
graph = builder.compile(checkpointer=InMemorySaver())


def main():
    config = {"configurable": {"thread_id": "ex6-参考"}}
    questions = [
        "帮我算 23 乘以 47 等于多少",
        "查一下订单 A001 现在什么状态",
        "你好，你能做什么",
    ]

    for q in questions:
        print("👤 用户：", q)
        result = graph.invoke({"messages": [{"role": "user", "content": q}]}, config)

        for m in reversed(result["messages"]):      # 找"有内容的 AI 消息"
            if m.type == "ai" and m.content:
                print("🤖 助手：", m.content)
                break
        print()


if __name__ == "__main__":
    main()
