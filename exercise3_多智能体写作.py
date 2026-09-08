r"""练习 3：多智能体写作流水线（独立重写练习 · 不需要 API Key）

【题目】
写一个"水果介绍短文生成小队"：输入一种水果名，多个 Worker 并行各写一段，
Editor 拼成短文，Critic 审稿发现"缺总评"→ 打回 Editor 补总评 → 再审通过。

全部用【内置素材 + 规则】实现，不调用任何 AI。

【验收标准】跑通后应该看到类似过程：
  📋 Planner：把「苹果」拆成 3 个子任务：外观 / 口感 / 营养
  🔧 Worker 完成：「外观」
  🔧 Worker 完成：「口感」
  🔧 Worker 完成：「营养」
  ✍️ Editor：第 1 稿完成（无总评）
  🧐 Critic：缺少【总评】，score=5，打回重写
  ✍️ Editor：第 2 稿完成（已补总评）
  🧐 Critic：评分 10，通过 ✅
  最终短文包含：外观、口感、营养、总评 四段

【要求自己写的部分】（从上到下）
1. 内置素材库 FRUIT_INFO：至少 3 种水果，每种含 3 个部分
   （外观 / 口感 / 营养）各一句 + 一句【总评】；另写通用兜底句
   （水果名不在素材库时也能写）
2. State 类，字段至少：
   topic: str            # 水果名（用户输入）
   subtopics: list[str]  # Planner 拆出的部分名
   subtopic: str         # Send 分发给单个 Worker 的"分支私有任务"
   pieces: Annotated[list, operator.add]   # ★ 各 Worker 产出段落，自动累加
   draft: str            # Editor 拼出的稿子
   critique: str         # Critic 的意见
   score: float          # Critic 打分
   iterations: int       # 写了几稿（防无限循环）
3. def planner(state)     —— 把 topic 拆成固定 3 部分 ["外观","口感","营养"]，存进 state
4. def route_research(state) —— ★ 返回 Send 列表（fan-out）：
      每个部分派一个任务：Send("worker", {"subtopic": 部分名})
5. def worker(state)      —— 从素材库取"这个部分"的句子；
      组装成带标签的一段："【外观】苹果红彤彤的……"
      return {"pieces": [这一段]}        # reducer 自动累加
6. def editor(state)      —— ★ fan-in 节点（所有 Worker 完成后只执行一次）：
      把 pieces 按顺序拼成 draft；
      如果 state 里已有 critic 的"缺总评"意见（或已是第 2 稿），
      就再补上素材库里的【总评】句
      iterations + 1 存回 state
7. def critic(state)      —— 规则版审稿：
      检查 draft 里有没有"【总评】"：
      有 → score = 10，critique = "通过"
      没有 → score = 5，critique = "缺少【总评】，请补充"
8. def should_revise(state) —— 条件边（反思循环）：
      score >= 8 或 iterations >= 2 → 结束；否则 → 回 editor 重写
9. 拼图（参考 case2_research_team/graph.py）：
      START → planner →（条件边返回 Send）→ worker
      worker → editor → critic →（条件边）→ editor 或 END
      记得 compile(checkpointer=InMemorySaver())
10. main：输入水果名（默认"苹果"），invoke 后打印完整短文和过程

【小提示】
- 新东西就三个：Send（派任务）、operator.add（列表累加 reducer）、
  条件边返回 Send 时第三参数用 ["worker"] 列表
  （全部能在 case2_research_team 的 nodes.py / graph.py / state.py 里找到参考）
- 素材缺失时的兜底：worker 里判断素材库有没有这个水果，
  没有就用通用句 f"{topic}是一种常见的水果……"
- 别整段抄 case2——那是研究小组，你写的是水果小队，逻辑自己搭
- 卡住 10 分钟 → 回来要提示（1/2/3 级），一次只看一级
"""
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
    draft = state.get("draft", "")
    if "【总评】" in draft:                             # 有总评 → 通过
        print("🧐 Critic：评分 10，通过 ✅")
        return {"score": 10.0, "critique": "通过"}
    else:                                              # 没总评 → 打回
        print("🧐 Critic：缺少【总评】，score=5，打回重写")
        return {"score": 5.0, "critique": "缺少【总评】，请补充"}

MAX_DRAFTS = 2

def should_revise(state):
    score=state.get("score",10.0)
    iterations=state.get("iterations",0)
    if score >= 8.0 or iterations >= MAX_DRAFTS:
       return "end"
    return "revise"

builder = StateGraph(State)
builder.add_node("planner", planner)
builder.add_node("worker", worker)
builder.add_node("editor", editor)
builder.add_node("critic", critic)

builder.add_edge(START, "planner")
builder.add_conditional_edges("planner",route_research,["worker"])
builder.add_edge("worker", "editor")        # 所有 Worker 完成 → editor 只跑一次（fan-in）
builder.add_edge("editor", "critic")
builder.add_conditional_edges("critic", should_revise, {"revise": "editor", "end": END})  # 反思循环

graph = builder.compile(checkpointer=InMemorySaver())


def main():
    config = {"configurable": {"thread_id": "ex3"}}
    result = graph.invoke({"topic": "苹果"}, config)

    print("\n===== 最终短文 =====")
    print(result["draft"])
    print("\n（共写", result["iterations"], "稿）")

if __name__ == "__main__":
    main()
