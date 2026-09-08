r"""练习 4（升级版）：水果介绍"发布流水线"——多智能体 + 人工审核 + 多轮反思

【升级了什么】（和练习 3 比）
① critic 更真实：多项检查（缺段？无总评？太短？），逐项扣分 + 列出批语
② ★ 新增"人工审核发布"：critic 达标后 → interrupt 暂停，把稿子交给真人审核员
   → 审核员输 y（发布）/ n（驳回）——把练习 2 的 HITL 融进多智能体流程
③ 建议最后用 get_state_history 看看整个流程留下了多少检查点

【流程图】
topic（水果名）
  → planner：拆成 外观/口感/营养
  → route_research：Send ×3（fan-out）
  → worker ×3：各写一段 → pieces[]（reducer 累加）
  → editor：拼稿；被批过就补总评/补缺失段（fan-in，只跑一次/轮）
  → critic：多项检查打分
      ├─ 不达标 → 回 editor（反思循环，最多 3 稿）
      └─ 达标 → human_review（★ interrupt 暂停，等真人）
                    ├─ 审核员输 y → "✅ 文章已发布"
                    └─ 输 n → "❌ 已驳回，未发布"
  → END

【验收标准】
1. 能看到 3 个 🔧 Worker 各自完成（fan-out）
2. critic 至少打回一次（第 1 稿缺总评 → 第 2 稿补上 → 通过）（反思循环）
3. 通过后弹审核：终端出现"请审核员决定：发布 y / 驳回 n"，等你输入
4. 输 y → 打印"✅ 已发布"+ 全文；重新跑输 n → "❌ 已驳回"
5.（可选）跑完后打印 get_state_history，能看到一堆检查点

【要求自己写的部分】（可以直接拿练习 3 的代码当底子改）
1. 复用：FRUIT_INFO + 兜底句 + State（topic/subtopics/subtopic/pieces/draft/critique/score/iterations）
2. planner / route_research / worker —— 同练习 3（任务单记得带 topic！）
3. editor —— 拼稿 + 按批语补内容（第 2 稿补总评；批语提到缺哪段就补哪段）
4. critic —— 多项检查打分：
     缺【外观】/【口感】/【营养】任一段 → 扣分并在批语写"缺XX"
     无【总评】→ 扣分，批语写"缺少【总评】，请补充"
     稿子 < 50 字 → 扣分，批语写"内容太短"
     全部通过 → score = 10
5. should_revise —— score >= 8 或 iterations >= 3 → 去 human_review；否则回 editor
6. ★ human_review —— 用 interrupt：
     payload = {"标题": topic + "介绍", "全文": draft}
     decision = interrupt(payload)
     decision == "y" → reply = "✅ 文章已发布"
     decision == "n" → reply = "❌ 已驳回，未发布"
     （参考案例 A 的 human_review / 练习 2 的 refund_request 写法）
7. 拼图：
     START → planner →（Send）→ worker → editor → critic
     critic →（should_revise）→ editor | human_review
     human_review → END
8. main：两次 invoke 模式（第一次触发流程停在 human_review，
    打印审核信息 → input() 收 y/n → 第二次 Command(resume=...)）
    （参考案例 A run_demo / 练习 2 的 main）

【小提示】
- interrupt / Command 的 import：from langgraph.types import interrupt, Command
- editor 里"按批语补缺失段"：检查 critique 里有没有"外观/口感/营养"字样，
  缺哪段就从 FRUIT_INFO/兜底句取哪段补上（参考练习 3 editor 补总评的写法）
- 卡住 10 分钟 → 回来要提示（1/2/3 级）
"""
from langgraph.types import interrupt, Command


# ============================================================
# 你的代码从这行下面开始（可先把练习 3 的代码粘进来再改）
# ============================================================
from zlib import MAX_WBITS

# ============================================================
# 你的代码从这行下面开始写 ↓
# ============================================================
from langgraph.types import Send
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import StateGraph, START, END
from langgraph.types import Send
from typing import Annotated
import operator
FRUIT_INFO:dict[str,dict]={
    "苹果":{
        "外观":"苹果是一种常见的水果，它的果实通常为圆形，颜色为绿色或红色。",
        "口感":"苹果的口感通常为多汁且略带酸味。",
        "营养":"苹果富含维生素C和纤维素，对人体有益。",
        "总评":"苹果是一种非常健康的水果，富含维生素和矿物质，对人体有益。"
    },
    "香蕉":{
        "外观":"香蕉是一种常见的水果，它的果实通常为长条形，颜色为黄色。",
        "口感":"香蕉的口感通常为多汁且略带甜味。",
        "营养":"香蕉富含维生素C和纤维素，对人体有益。",
        "总评":"香蕉是一种非常健康的水果，富含维生素和矿物质，对人体有益。"
    },
    "橘子":{
        "外观":"橘子是一种常见的水果，它的果实通常为圆形，颜色为橙色。",
        "口感":"橘子的口感通常为多汁且略带酸味。",
        "营养":"橘子富含维生素C和纤维素，对人体有益。",
        "总评":"橘子是一种非常健康的水果，富含维生素和矿物质，对人体有益。"
    },
    "葡萄":{
        "外观":"葡萄是一种常见的水果，它的果实通常为圆形，颜色为紫色。",
        "口感":"葡萄的口感通常为多汁且略带酸味。",
        "营养":"葡萄富含维生素C和纤维素，对人体有益。",
        "总评":"葡萄是一种非常健康的水果，富含维生素和矿物质，对人体有益。"
    }
}

def 兜底句(topic, part):
    """素材库没有的水果，按部分现编通用句子。"""
    if part == "外观":
        return f"{topic}是一种常见的水果，果实通常为圆形，颜色多样。"
    elif part == "口感":
        return f"{topic}的口感通常为多汁，风味独特。"
    elif part == "营养":
        return f"{topic}含有丰富的维生素和膳食纤维。"
    elif part == "总评":
        return f"{topic}是一种健康可口的水果，适合日常食用。"
    else:
        return f"关于{topic}的{part}暂无资料。"     # 兜底的兜底，绝不返回 None

class State:
    topic: str
    subtopics: list[str]
    subtopic: str
    pieces: Annotated[list, operator.add]
    draft: str
    critique: str
    score: float
    iterations: int
    reply:str

def planner(state):
    topic=state.get("topic")
    subtopics=["外观","口感","营养",]
    print(f"planner把{topic}拆分成3个部分:{subtopics}")
    return {"subtopics": subtopics}


def route_research(state):
    parts=state.get("subtopics",["外观","口感","营养"])
    topic=state.get("topic")
    send_list=[]
    for part in parts:
        send_list.append(Send("worker",{"subtopic":part,"topic":topic}))
    return send_list

def worker(state):
    topic=state.get("topic")
    part=state.get("subtopic")
    if topic in FRUIT_INFO:
        sentence=FRUIT_INFO[topic][part]
    else:
        sentence=兜底句(topic,part)
    pieces=["【"+part+"】"+sentence]
    return {"pieces":pieces}


def editor(state):
    topic=state.get("topic")
    iterations=state.get("iterations",0)+1
    lines=[]
    for part in state.get("subtopics"):
        marker="【"+part+"】"
        for p in state.get("pieces"):
            if p.startswith(marker):
                lines.append(p)
                break
    draft="\n".join(lines)
    if "【总评】" not in draft and ("总评" in state.get("critique", "") or iterations >= 2):
        if topic in FRUIT_INFO:
            ping = FRUIT_INFO[topic]["总评"]
        else:
            ping = 兜底句(topic, "总评")
        draft += "\n\n【总评】" + ping  # ✅ 直接拼上标签文字
        print("✍️ Editor：第", iterations, "稿完成")
    return{
            "draft": draft,
            "iterations": iterations
        }
def critic(state):
    draft=state.get("draft","")
    parts=state.get("subtopics",[])
    problems=[]
    for part in parts:
        marker = "【" + part + "】"
        if marker not in draft:
            problems.append(f"缺少【{part}】，请补充")
    if "【总评】" not in draft:
        problems.append("缺少【总评】，请补充")
    if len(draft) < 50:
        problems.append("内容太短")
    score = 10.0 - 3.0 * len(problems)
    if score < 0:
            score = 0.0
    critique = "；".join(problems) if problems else "通过"
    print("🧐 Critic：评分", score, "——", critique)
    return {"score": score, "critique": critique}  # ✅ 别忘了 return！
MAX_DRAFTS = 3
def should_revise(state):
    score=state.get("score",10.0)
    iterations=state.get("iterations",0)
    if score >= 8 or iterations >= MAX_DRAFTS:
        return "human_review"
    return "revise"


def human_review(state:State)->dict:
    topic=state.get("topic")
    draft=state.get("draft")
    payload={"标题":topic+"介绍","全文":draft}
    decision=interrupt(payload)
    if decision=="y":
        return {"reply": "✅ 文章已发布"}
    else:
        return {"reply": "❌ 已驳回，未发布"}



builder=StateGraph(State)
builder.add_node("planner",planner)
builder.add_node("worker",worker)
builder.add_node("editor",editor)
builder.add_node("critic",critic)
builder.add_node("human_review",human_review)


builder.add_edge(START,"planner")
builder.add_conditional_edges("planner",route_research,["worker"])
builder.add_edge("worker","editor")
builder.add_edge("editor","critic")
builder.add_conditional_edges("critic",should_revise,{
    "revise":"editor",
    "human_review":"human_review"
})
builder.add_edge("human_review",END)
checkpointer=InMemorySaver()
graph=builder.compile(checkpointer=checkpointer)
config={"configurable":{"thread_id":"exercise_4"}}



# def main():
#     print("===== 自动验收：练习 4 =====")
#
#     # —— 场景 1：审核员点 y（发布）——
#     cfg_y = {"configurable": {"thread_id": "验收-y"}}
#     first = graph.invoke({"topic": "苹果"}, cfg_y)
#
#     停了吗 = "reply" not in first          # 第一次 invoke 应停在 human_review（还没有 reply）
#     print(("✅" if 停了吗 else "❌"), "第一次 invoke 停在人工审核")
#
#     final_y = graph.invoke(Command(resume="y"), cfg_y)   # 自动点 y
#     reply_y = final_y.get("reply", "")
#     draft = final_y.get("draft", "")
#     print(("✅" if "发布" in reply_y else "❌"), "点 y →", reply_y)
#
#     for part in ["【外观】", "【口感】", "【营养】", "【总评】"]:
#         print(("✅" if part in draft else "❌"), "短文包含", part)
#
#     n_稿 = final_y.get("iterations", 0)
#     print(("✅" if n_稿 >= 2 else "❌"), "反思循环跑过（iterations =", n_稿, "）")
#
#     # —— 场景 2：审核员点 n（驳回）—— 用另一个线程，避免和场景1串档 ——
#     cfg_n = {"configurable": {"thread_id": "验收-n"}}
#     graph.invoke({"topic": "苹果"}, cfg_n)
#     final_n = graph.invoke(Command(resume="n"), cfg_n)
#     reply_n = final_n.get("reply", "")
#     print(("✅" if "驳回" in reply_n else "❌"), "点 n →", reply_n)
#
#     # —— 附加：看看留了多少检查点 ——
#     print("线程『验收-y』共留下", len(list(graph.get_state_history(cfg_y))), "个检查点")
#
#     print("===== 验收结束 =====")


def main():
    # 手动体验版：流程会停在 human_review，等你在终端输入 y / n
    config = {"configurable": {"thread_id": "手动-1"}}

    first = graph.invoke({"topic": "苹果"}, config)
    # ↑ 第一次 invoke：图跑到 human_review 的 interrupt → 冻结在这里返回

    print("\n===== 请审核员审阅 =====")
    print("标题：苹果介绍")
    print("全文：")
    print(first.get("draft", ""))       # 从冻结状态里把稿子打出来给审核员看
    print("=========================")

    answer = input("请审核员决定：发布 y / 驳回 n > ").strip().lower()
    # ↑ ★ 程序停在这里等你输入！你敲 y 或 n 再回车

    final = graph.invoke(Command(resume=answer), config)
    # ↑ 第二次 invoke：把决定喂回图 → 图从 human_review 继续 → 跑完

    print("结果：", final.get("reply"))


if __name__ == "__main__":
    main()        # 改成调用自动验收（想手动体验时改回 main()）
