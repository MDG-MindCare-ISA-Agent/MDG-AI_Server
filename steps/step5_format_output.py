# steps/step5_format_output.py
import re
from typing import List
from routing import needs_smalltalk

def _clean(text: str) -> str:
    if not text:
        return ""
    t = re.sub(r"[ \t]+", " ", text.strip())
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t

def _build_quick_replies(choices) -> List[str]:
    if choices:
        return [f"{i+1}번으로 해줘" for i in range(min(len(choices), 4))]
    return ["전략 추천해줘", "포트폴리오 요약 알려줘", "시뮬 돌려줘"]

def format_output(ctx):
    # ✅ 스몰토크면 감정/본문 파츠 다 무시하고 '가벼운 인사 질문'만 출력
    if needs_smalltalk(ctx):
        ans = "안녕하세요! 오늘은 어떤 점이 가장 궁금하신가요?"
        output = {
            "emotion": None,                # 감정블록 비표시 (원하면 ctx.get("emotion")로 유지 가능)
            "info": None,
            "strategies": [],
            "strategy": None,
            "simulation": None,
            "_meta": ctx.get("_meta", {}),
            "answer": ans,
            "message": ans,
            "ok": True,
            "quick_replies": ["전략 추천해줘", "포트폴리오 요약 알려줘", "시뮬 돌려줘"],
            "_plan": ctx.get("_plan", {}),  # 디버그용
        }
        ctx["output"] = output
        return ctx

    # ─────────────────────────────────────────────────────────
    # (이하는 기존 로직: 투자 관련 플로우일 때만 동작)
    # ─────────────────────────────────────────────────────────
    parts = []

    emo = ctx.get("emotion") or {}
    if emo.get("message"):
        parts.append(emo["message"])

    for key in ("portfolio_answer", "info_answer", "strategy_answer", "simulation_answer"):
        val = ctx.get(key)
        if val:
            parts.append(val)

    if not any(parts):
        parts.append("말씀 잘 들었어요. 혹시 지금 가장 신경 쓰이는 지점을 한 가지만 알려주실 수 있을까요?")

    ans = _clean("\n\n".join([p for p in parts if p]))

    output = {
        "emotion": ctx.get("emotion"),
        "info": ctx.get("info"),
        "strategies": ctx.get("strategies"),
        "strategy": ctx.get("strategy"),
        "simulation": ctx.get("simulation"),
        "_meta": ctx.get("_meta", {}),
        "answer": ans,
        "message": ans,
        "ok": True,
    }

    if ctx.get("choices"):
        output["_choices"] = ctx["choices"]

    output["quick_replies"] = _build_quick_replies(output.get("_choices"))

    if ctx.get("profile_running"):
        output["_profile_running"] = ctx["profile_running"]
    if (ctx.get("input") or {}).get("history_summary"):
        output["_history_summary"] = ctx["input"]["history_summary"]
    if ctx.get("_hint_for_next"):
        output["_hint_for_next"] = ctx["_hint_for_next"]
    if ctx.get("_plan"):
        output["_plan"] = ctx["_plan"]

    ctx["output"] = output
    return ctx