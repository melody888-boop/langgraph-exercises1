r"""练习 1：迷你客服图（独立重写练习）—— 你的代码写在本文件里！

【题目】
写一个"迷你客服"：用户问一句话，图判断它是"政策咨询(faq)"还是"查订单(order)"，
然后走对应节点回答。全部用规则判断，不调用任何 AI（不需要 API Key）。

【验收标准】跑通后应该看到：
  问 "你们退货时效是几天？"        → 回答里包含 "7 天" 或你定的退货政策内容
  问 "帮我查一下订单 A001"        → 回答里包含商品名或状态（来自订单表）
  问 "查订单 Z999"               → 回答 "没有找到订单"
  同一线程连问两轮 → 消息历史在累积（messages 变多）

【要求自己写的部分】（从上到下，缺一不可）
1. 一个迷你"政策知识库"：列表或字典，每条含 关键词列表 + 回答文本
   （至少 2 条：退货、运费。可以再加发票。）
2. 一个迷你"订单表"：字典，至少 2 单（单号、商品名、状态）
3. State 类：字段 user_input / intent / reply / messages
   messages 要能"追加"（自己写一个 reducer 函数，或查资料用官方 add_messages）
4. def parse_input(state)      —— 用【关键词规则】判断意图：
     话里含 "订单" 或形如 A001 的单号 → intent = "order"，顺便提取订单号
     话里含退货/运费/发票等词     → intent = "faq"
     都判断不出                 → intent = "faq"（安全默认）
5. def faq_answer(state)       —— 查迷你知识库：关键词命中就回对应回答；
                                  没命中回"资料库无匹配，请转人工"
6. def order_lookup(state)     —— 用订单号查迷你订单表：
                                  找到 → 拼出订单信息回复
                                  没有 → 回"没有找到订单 xxx"
7. def route_by_intent(state)  —— 条件边：按 intent 分流到 faq_answer / order_lookup
8. 拼图 + 编译 + 一个简单的 main()：
     用 StateGraph、add_node、add_conditional_edges、compile(checkpointer=...)
     然后用几个测试问题 invoke，把 reply 打印出来

【小提示】
- 节点函数套路永远是：读 state → 干活 → return 要更新的字段 dict
- 提取订单号可以 import re，用 re.search(r"A\d{3}", text)（实在不会就先用 if "A001" in text）
- messages 里存普通 dict：{"role": "user", "content": ...} / {"role": "assistant", ...}
- 写完用下面的"一键运行_练习1.command"双击运行，或：
  /Users/wangyanhong/deepseekharness/.venv/bin/python exercise1_mini_kefu.py

写吧！卡住超过 10 分钟再找我要提示（提示分 1/2/3 级，别一次看完）。
"""
# ============================================================
# 你的代码从这行下面开始写 ↓
# ============================================================
from typing import TypedDict,Annotated
from langgraph.graph.message import add_messages
import re
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import InMemorySaver
KNOWLEDGE_BASE: list[dict]=[
    {
    "keywords":["退货", "无理由", "几天", "7天", "七天", "时效", "期限"],
    "answer":("本店支持签收后 7 天内无理由退货（不影响二次销售），"
            "定制类商品除外；退货需保留吊牌与包装。"),
},
    {
    "keywords":["运费", "邮费", "谁出", "承担", "退货运费"],
    "answer":("因质量问题退货运费由商家承担；无理由退货的运费由买家承担；"
            "使用运费险的订单可在退款页面申请理赔。"),
    },
    {
    "keywords":["发票", "开票", "报销"],
    "answer":("订单确认收货后可申请电子发票：我的订单 -> 申请开票，"
            "信息填写正确后 24 小时内发送到邮箱。"),
    }
    ]

ORDERS: dict[str, dict] = {
    "A001": {
        "id": "A001",
        "item": "无线机械键盘",
        "buyer": "张三",
        "amount": 399.0,
        "status": "已发货",
        "refunded_amount": None,
    },
    "A002": {
        "id": "A002",
        "item": "蓝牙降噪耳机",
        "buyer": "张三",
        "amount": 1299.0,
        "status": "已签收",
        "refunded_amount": None,
    },
}

class ServerState(TypedDict):
    messages: Annotated[list, add_messages]
    user_input:str|None
    intent:str|None
    order_id:str|None
    reply:str

# def parse_input(state:ServerState)->dict:
#     text=state.get(user_input).strip()
#     if not text:
#         return {"intent":"feq","messages":[]}
#     match = re.search(r"A\d{3}",text)
#     if "订单" in text or match is not None:#or代表或
#         intent = "order"
#         if match is not None:
#             order_id = match.group(0)#.group()等价于group()
#         else:
#             order_id = "找不到此订单号"
#             return {
#                 "intent":"order",
#                 "order_id":"order_id",
#                 "messages":[{"role":"user","content":"text"}]
#             }
#     if "退货" in text or "运费" in text or "发票" in text:
#         intent = "faq"
#         return {
#             "intent":"faq",
#             "messages":[{"role":"user","content":"text"}]
#         }
#错误代码


def parse_input(state: ServerState)->dict:
    text = state.get("user_input").strip()
    match = re.search(r"[A-Z]\d{3}",text)
    if match is not None or "订单" in text:
        intent = "order"
        if match is None:
            order_id = "找不到此订单号"
        else:
            order_id = match.group(0)
    else:
        intent = "faq"
        order_id = "找不到此订单"
    return {
        "intent":intent,
        "order_id":order_id,
        "messages":[{"role":"user","content":text}]
    }


# def faq_answer(state:ServerState)->dict:
#     for knowledge in KNOWLEDGE_BASE:
#         kw = knowledge["keywords"]
#         if any(kw in state["user_input"] for kw in knowledge["keywords"]):
#             return {"reply":knowledge["answer"],"messages":[]}
#         else:
#             return {"reply":"资料库无匹配，请转人工","messages":[]}

def faq_answer(state:ServerState)->dict:
    question = state.get("user_input")
    for policy in KNOWLEDGE_BASE:
        for keywords in policy["keywords"]:
            if keywords in question:
                return {
                    "reply":policy["answer"],
                    "messages":[{"role":"assistant","content":policy["answer"]}]
                }
    return {
        "reply":"资料库无匹配，请转人工",
        "messages":[{"role":"assistant","content":"资料库无匹配，请转人工"}],
    }

#上面为return写法


#found写法：
def faq_answer(state):
    question = state.get("user_input", "")

    reply = "资料库无匹配，请转人工。"   # 默认答案
    found = False

    for policy in KNOWLEDGE_BASE:
        for keyword in policy["keywords"]:
            if keyword in question:
                reply = policy["answer"]   # 命中 → 只【改变量】，不 return
                found = True
                break
        if found:
            break

    # ★ 循环结束后，不管命中没命中，都会走到这里
    return {                                # ← 唯一的 return 在这里
        "reply": reply,
        "messages": [{"role": "assistant", "content": reply}],
    }


# def order_lookup(state:ServerState)->dict:
#     id = state.get("order_id")
#     for policy2 in ORDERS:
#         if order_id in id:
#             reply = id
#


def order_lookup(state:ServerState)->dict:
    order_id=state.get("order_id")
    if order_id==None:
        reply="请提供订单号"
    else:
        order=ORDERS.get(order_id)
        if order is None:
            reply="没有找到此订单，请核对您的订单号"
        else:
            reply=(
                "订单 " + order["id"] + "：" + order["item"]
                + "，实付 ¥" + str(order["amount"])
                + "，当前状态：" + order["status"] + "。"
            )
    return {
        "reply":reply,
        "messages":[{"role":"assistant","content":reply}],
    }

def route_by_intent(state):
    return state.get("intent","faq")


builder = StateGraph(ServerState)
builder.add_node("parse_input", parse_input)
builder.add_node("faq_answer", faq_answer)
builder.add_node("order_lookup", order_lookup)

builder.add_edge(START, "parse_input")
builder.add_conditional_edges("parse_input",
                             route_by_intent,
                             {
                                 "faq": "faq_answer",
                                 "order": "order_lookup",
}
                             )
builder.add_edge("faq_answer", END)
builder.add_edge("order_lookup", END)
graph=builder.compile(checkpointer=InMemorySaver())


def main():
    config = {"configurable": {"thread_id": "demo-1"}}
    questions = ["退货时效是几天？", "帮我查一下订单 A001", "查订单 Z999"]
    for q in questions:
        result = graph.invoke({"user_input": q}, config)
        print("问：", q)
        print("答：", result["reply"])
        print()
if __name__ == "__main__":
    main()



