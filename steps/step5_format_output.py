# steps/step5_format_output.py
def format_output(ctx):
    parts = []

    # 1) 공감/멘트
    emo = ctx.get("emotion") or {}
    if emo.get("message"):
        parts.append(emo["message"])

    # 2) 본문 파츠 합치기
    for key in ("portfolio_answer", "info_answer", "strategy_answer", "simulation_answer"):
        val = ctx.get(key)
        if val:
            parts.append(val)

    ans = "\n\n".join([p for p in parts if p])

    # 3) output 생성
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

    # 4) ✅ 이 턴의 선택지(있으면) output에 실어 보냄 → pipeline에서 set_last_options로 저장
    if ctx.get("choices"):
        output["_choices"] = ctx["choices"]

    ctx["output"] = output
    return ctx