"""安全规则：写在一个地方，拆步骤、画图、查图、练习时看镜头都用这一份。

为什么：以前是每张图出问题再去改提示词，改了这张、下张又错。现在规则先定好，
每个环节都从这里取，改规则只改这一个文件。

每条规则：
- id / name：危险类别
- words：步骤文字里出现这些词就算命中（小写匹配）
- plan：拆步骤时必须遵守的做法（写进步骤里）
- picture：画图时的正面描述（用正面说法，避免触发图片模型的内容过滤）
- check：查图时判为不安全的情形
- watch：练习时镜头里看到就要立刻叫停的情形
命中任何一条的步骤：AI 图不画手（只画物品），老师最好用真实照片；练习时老师需要在旁边。
"""
import re

RULES = [
    {
        "id": "heat", "name": "Hot liquid / hot surface",
        "words": ["hot", "boil", "kettle", "pour", "stove", "oven", "toaster", "microwave", "iron", "steam",
                  "pan", "grill", "hot pot", "hotpot", "kettle", "fry", "bake", "heat"],
        "plan": "Before pouring anything hot, add a step that puts the cup/mug on the counter. Never hold a cup while "
                "hot liquid goes in. Hold hot things only by their handle. Spouts and pan handles point away from the body.",
        "picture": "Any cup or mug being filled stands on the counter by itself. Handles and spouts point away from the "
                   "person. The free hand rests flat on the counter, away from the action.",
        "check": "a hand holds a cup/mug that is receiving liquid from a kettle or pot; a hand is near a spout, steam, "
                 "a burner or a hot surface; a spout or pan handle points toward the person",
        "watch": "a hand is holding the cup while hot water is poured into it, or a hand or arm is over steam, a spout "
                 "or a hot surface",
    },
    {
        "id": "sharp", "name": "Knives / sharp tools",
        "words": ["knife", "cut", "slice", "chop", "peel", "scissors", "blade", "grater", "razor"],
        "plan": "Use a cutting board on a flat surface. The blade points down and away. The other hand holds the food "
                "with fingers curled in. Carry a knife point-down at the side.",
        "picture": "The cutting tool rests flat on a cutting board, pointing away from the person. Fingers of the "
                   "other hand are curled in, well behind the tool.",
        "check": "fingers are in front of or under a blade; a blade points toward a person; someone holds food in "
                 "the air while cutting it",
        "watch": "fingers are in front of the blade, or the blade points toward the body, or food is cut in the air",
    },
    {
        "id": "electric", "name": "Electricity near water",
        "words": ["plug", "unplug", "outlet", "socket", "cord", "switch on", "power"],
        "plan": "Dry hands before touching plugs, cords or switches. Unplug by pulling the plug, never the cord. "
                "Plugs and cords stay away from the sink.",
        "picture": "Dry hands; the plug is held by its base; the cord is away from any water.",
        "check": "wet hands or water near a plug, cord or outlet; pulling a plug by its cord",
        "watch": "a plug, cord or appliance base is in or next to water, or the cord is being pulled",
    },
    {
        "id": "chemical", "name": "Cleaning chemicals",
        "words": ["bleach", "cleaner", "detergent", "spray", "chemical", "soap pod", "dish pod"],
        "plan": "Point spray nozzles away from the face. Never mix cleaners. Close the cap right after use.",
        "picture": "The spray nozzle points at the surface, away from the face; the bottle is closed when not in use.",
        "check": "a nozzle points toward a face; two cleaners are mixed; a pod or cleaner is near the mouth",
        "watch": "a spray nozzle points toward a face, or a cleaner or pod is near the mouth",
    },
]

# 永远不做的任务（拆步骤时直接拒绝）
REFUSE = "medication, power tools, weapons, gas appliances with open flame, or anything a caregiver would never let a beginner practice"


def hazards(step: dict) -> list[str]:
    """这一步命中哪些危险类别。"""
    text = " ".join([step.get("text", ""), step.get("safety") or "", " ".join(step.get("objects", []))]).lower()
    out = [r["id"] for r in RULES if any(re.search(r"\b" + re.escape(w) + r"\b", text) for w in r["words"])]
    if step.get("safety") and not out:
        out.append("other")
    return out


def _pick(ids):
    return [r for r in RULES if not ids or r["id"] in ids]


def plan_text() -> str:
    return "\n".join(f"   - {r['name']}: {r['plan']}" for r in RULES)


def picture_text(ids=None) -> str:
    return " ".join(r["picture"] for r in _pick(ids))


def check_text() -> str:
    return "; ".join(r["check"] for r in RULES)


def watch_text(ids) -> str:
    rs = [r for r in RULES if r["id"] in (ids or [])]
    return "; ".join(r["watch"] for r in rs)
