from services.emotion_service import analyze_with_hyperclova

def analyze_emotion(ctx):
    """
    2단계: 감정 분석
    - 사용자 발화(text)를 HyperCLOVA X로 분석
    - 결과를 ctx["emotion"]에 저장
    """
    text = ctx.get("input", {}).get("text", "")
    if not text:
        ctx["emotion"] = {"primary": "중립", "confidence": 0.0, "triggers": []}
        return ctx

    emotion_result = analyze_with_hyperclova(text)
    if "type" not in emotion_result:
        emotion_result["type"] = "info"
    ctx["emotion"] = emotion_result
    return ctx