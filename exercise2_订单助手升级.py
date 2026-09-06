r"""练习 2（升级版）：把迷你客服升级成"会算账、会审核、会回溯的订单助手"

【开始之前】
1. 打开你写好的 exercise1_mini_kefu.py
2. 把【分隔线以下】你写的代码（import、知识库、订单表、State、节点、路由、拼图、main）
   全部复制进本文件【分隔线以下】——这是你自己的代码，随便复制
3. 然后按下面 3 个关卡，一关一关往上加（每关做完先跑通再进下一关）

============================================================
【关卡 1】加一个"计算器"意图（练：新增节点 + 扩展条件边）
============================================================
需求：用户问"399 打 8 折是多少"或"200 加 30 等于多少"，图能算出来。

做法（不用 AI，用规则）：
  a. 在 parse_input 的意图判断里，加一个新意图 "calc"：
     话里含 "算" 或 "多少" → intent = "calc"
     （放在 order 判断之后、faq 兜底之前）
  b. 写一个新节点 def calculator(state)：
     - 从 user_input 里提取数字和运算
     - 第 1 版先只支持：X 打 N 折 → X * N / 10
       （会了以后，再自己加：X 加/减/乘/除以 Y）
     - 返回 {"reply": "结果是 xxx", "messages": [助手消息]}
  c. 在拼图里：注册节点 + 在条件边映射表加 "calc": "calculator"

验收：问 "399 打 8 折是多少" → 回 "结果是 319.2"
     问 "200 加 30 等于多少"（如果你做到第二版）→ "结果是 230"
     问原来的问题（退货/查单）→ 行为不变

============================================================
【关卡 2】加"退款 + 人工审核"（练：interrupt 暂停 / Command 恢复）★核心
============================================================
需求：用户说"我要退款，订单号 A001" → 图先暂停，把"审核单"抛给真人 →
     真人在终端输入 y（同意）/ n（驳回）→ 图继续：同意就真改订单，驳回就取消。

做法：
  a. 意图判断加 "refund"：话里含 "退款" 或 "退" 且带单号 → intent = "refund"
  b. 新节点 def refund_request(state)：
     - 用单号查订单表（复用 ORDERS）
     - 查不到 → 直接回 "没有找到可退款的订单"
     - 查到 → 调 interrupt({...审核单...})，把结果存进 state
     （先参考案例 A 的 nodes.py 里 human_review 怎么写 interrupt）
  c. 新节点 def refund_execute(state) / 或 def refund_denied(state)：
     - 审核通过 → 改订单状态为"已退款"，返回成功话术
     - 驳回 → 返回取消话术
  d. main() 里要"两次 invoke"（先参考案例 A 的 run_demo.py 第 2 段）：
     - 第一次 invoke → 图停在 interrupt → 打印审核单内容
     - 在终端 input() 等审核员输入 y / n
     - 第二次 invoke(Command(resume={...})) → 图继续跑完
     - 需要 import：from langgraph.types import interrupt, Command

验收：输 "我要退款，订单号 A001" → 终端弹出审核单（含订单号、金额）
     输入 y → 回 "已通过审核并退款 399 元"，且订单状态真的变成"已退款"
     重新跑、输入 n → 回 "已取消退款"，订单状态没变

============================================================
【关卡 3 · 挑战】时间旅行：改口重跑（练：get_state_history / update_state）
============================================================
需求：关卡 2 跑完后，模拟"审核员改口"：同意退了 399，但想改成只退 200。

做法（参考案例 A 的 run_demo.py 第 3 段）：
  a. 正常跑一次退款（同意退 399）
  b. 用 graph.get_state_history(config) 找到"执行退款之前"的快照
     （找 next == ("refund_execute",) 的那个）
  c. 用 graph.update_state(快照config, {"审核结果": 改成退 200})
  d. 再 graph.invoke(None, 新config) —— 从分叉点重跑
验收：第二次跑的退款话术里是 200，而不是 399

============================================================
【规则】跟练习 1 一样：
- 语法拿不准 → 翻案例 A 的 nodes.py / graph.py / run_demo.py 看写法（允许）
- 禁止整段复制案例 A 的实现（思路可以学，代码自己写）
- 卡住 10 分钟 → 回来要提示（1/2/3 级），一次只看一级
- 每关跑通、输出正确，再进下一关
"""
# ============================================================
# 你的代码从这行下面开始（先粘贴 exercise1 的代码，再往上加）
# ============================================================
from typing import TypedDict,Annotated
from langgraph.graph.message import add_messages
import re
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import interrupt, Command   # ← 文件顶部加这一行
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
    calc:float|None

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
    elif "算" in text or "多少" in text:
        intent = "calc"
        order_id = "找不到此订单"
    else:
        intent = "faq"
        order_id = "找不到此订单"

    if "退款" in text or "退" in text and match is not None:
        intent="refund"
        order_id = match.group(0)
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
# b. 写一个新节点 def calculator(state)：
#      - 从 user_input 里提取数字和运算
#      - 第 1 版先只支持：X 打 N 折 → X * N / 10
#        （会了以后，再自己加：X 加/减/乘/除以 Y）
#      - 返回 {"reply": "结果是 xxx", "messages": [助手消息]}


def calculator(state:ServerState)->dict:
    text=state.get("user_input")
    calc=None
    if "折" in text:
        number=re.findall(r"\d+",text)
        if len(number)>=2:
            price=float(number[0])
            discount=float(number[1])
            calc=price*discount/10
            reply=str(price) + " 打 " + str(discount) + " 折 = " + str(calc)
        else:
            reply="请输入原价和折扣,比如：399 打 8 折"
    else:
        reply="我只会算'X 打 N 折'，比如：399 打 8 折"
    return {
        "reply":reply,
        "messages":[{"role":"assistant","content":reply}],
        "calc":calc
    }


# 【关卡 2】加"退款 + 人工审核"（练：interrupt 暂停 / Command 恢复）★核心
# ============================================================
# 需求：用户说"我要退款，订单号 A001" → 图先暂停，把"审核单"抛给真人 →
#      真人在终端输入 y（同意）/ n（驳回）→ 图继续：同意就真改订单，驳回就取消。
#
# 做法：
#   a. 意图判断加 "refund"：话里含 "退款" 或 "退" 且带单号 → intent = "refund"
#   b. 新节点 def refund_request(state)：
#      - 用单号查订单表（复用 ORDERS）
#      - 查不到 → 直接回 "没有找到可退款的订单"
#      - 查到 → 调 interrupt({...审核单...})，把结果存进 state
#      （先参考案例 A 的 nodes.py 里 human_review 怎么写 interrupt）
#   c. 新节点 def refund_execute(state) / 或 def refund_denied(state)：
#      - 审核通过 → 改订单状态为"已退款"，返回成功话术
#      - 驳回 → 返回取消话术
#   d. main() 里要"两次 invoke"（先参考案例 A 的 run_demo.py 第 2 段）：
#      - 第一次 invoke → 图停在 interrupt → 打印审核单内容
#      - 在终端 input() 等审核员输入 y / n
#      - 第二次 invoke(Command(resume={...})) → 图继续跑完
#      - 需要 import：from langgraph.types import interrupt, Command
#
# 验收：输 "我要退款，订单号 A001" → 终端弹出审核单（含订单号、金额）
#      输入 y → 回 "已通过审核并退款 399 元"，且订单状态真的变成"已退款"
#      重新跑、输入 n → 回 "已取消退款"，订单状态没变

def refund_request(state:ServerState)->dict:
    #查订单
    order_id=state.get("order_id")
    order=ORDERS.get(order_id)
    if order is None:
        reply="没有找到可退款的订单，请核对您的订单号"
        return {"reply":reply,"messages":[{"role":"assistant","content":reply}]}
    payload={
        "title":"退款人工审核",
        "order_id":order["id"],
        "amount":order["amount"],
        "item":order["item"],
        "status":order["status"],
    }
    decision=interrupt(payload)
    if decision=="y":
        reply="已通过审核并退款 " + str(order["amount"]) + " 元"
        order["status"]="已退款"
    else:
        reply="人工取消退款，如有疑问请联系人工客服"
    return {"reply":reply,"messages":[{"role":"assistant","content":reply}]}

# 【关卡 3 · 挑战】时间旅行：改口重跑（练：get_state_history / update_state）
# ============================================================
# 需求：关卡 2 跑完后，模拟"审核员改口"：同意退了 399，但想改成只退 200。
#
# 做法（参考案例 A 的 run_demo.py 第 3 段）：
#   a. 正常跑一次退款（同意退 399）
#   b. 用 graph.get_state_history(config) 找到"执行退款之前"的快照
#      （找 next == ("refund_execute",) 的那个）
#   c. 用 graph.update_state(快照config, {"审核结果": 改成退 200})
#   d. 再 graph.invoke(None, 新config) —— 从分叉点重跑
# 验收：第二次跑的退款话术里是 200，而不是 399






def route_by_intent(state):
    return state.get("intent","faq")


builder = StateGraph(ServerState)
builder.add_node("parse_input", parse_input)
builder.add_node("faq_answer", faq_answer)
builder.add_node("order_lookup", order_lookup)
builder.add_node("calculator", calculator)
builder.add_node("refund_request", refund_request)

builder.add_edge(START, "parse_input")
builder.add_conditional_edges("parse_input",
                             route_by_intent,
                             {
                                 "faq": "faq_answer",
                                 "order": "order_lookup",
                                 "calc": "calculator",
                                 "refund": "refund_request",
                              }
                             )
builder.add_edge("faq_answer", END)
builder.add_edge("order_lookup", END)
builder.add_edge("calculator", END)
builder.add_edge("refund_request", END)

checkpointer=InMemorySaver()
graph=builder.compile(checkpointer=checkpointer)
config = {"configurable": {"thread_id": "exercise2"}}

def main():
# ① 第一次 invoke（你已写）：触发退款 → 图停在 interrupt
   first = graph.invoke({"user_input": "我要退款，订单号 A001"}, config=config)
# 注意：现在 first 里没有最终 reply（图还没跑完）

# ② 告诉审核员该决定了，并用 input() 等他在终端输入
   print("🔔 退款审核单已提交，请审核员决定……")
   answer = input("同意退款输入 y，取消输入 n > ").strip().lower()

# ③ 第二次 invoke：把决定喂回图（★ 必须用同一个 config！）
   final = graph.invoke(Command(resume=answer), config=config)

# 现在图真正跑完了，打印最终结果
   print("结果：", final["reply"])
   查看历史(config)

def 查看历史(config):
    print("\n===== 线程历史（最新的在最前面）=====")
    snapshots = list(graph.get_state_history(config))   # 拿到这个线程的所有检查点
    for i, s in enumerate(snapshots):
        print("#" + str(i), "→ 接下来要跑的节点:", s.next)
        print("      当时的状态:", s.values)
        print()


if __name__ == "__main__":
    main()