from services.emotion_service import analyze_with_hyperclova

def analyze_emotion(ctx):
    """
    2단계: 감정/의도 분석
    CLOVA 키가 없으면 로컬 폴백으로 'type'을 뽑아냄.
    """
    if ctx.get("force_pick"):
        ctx["emotion"] = {"type":"info","primary":"중립","confidence":0.0,"triggers":[],"message":""}
        return ctx
    text = ctx.get("input", {}).get("text", "")
    if not text:
        ctx["emotion"] = {"type": "info", "primary": "중립", "confidence": 0.0, "triggers": [], "message": ""}
        return ctx

    result = analyze_with_hyperclova(text)
    if "type" not in result:
        result["type"] = "info"
    # empathy를 최상단 메시지로 노출
    result.setdefault("empathy", "")
    result["message"] = result.get("empathy") or ""
    ctx["emotion"] = result
    return ctx