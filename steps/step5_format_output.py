def format_output(ctx):
    """
    5단계: 출력 포맷팅
    - 사용자용 요약 메시지 생성 (공감 → 근거 → 실행)
    - 운영용 데이터 포함 가능
    """
    ctx["input"]["text"] = f"{ctx['input'].get('text', '')} -> [5단계: 출력완료]"
    ctx["output"] = {
        "result": ctx["input"]["text"],
        "investment": ctx["input"].get("investment"),
        "emotion": ctx.get("emotion")  # 감정 분석 결과 포함
    }
    return ctx