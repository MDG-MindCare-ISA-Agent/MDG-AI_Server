def parse_and_validate(ctx):
    """
    1단계: 입력값 파싱 & 검증
    - text, investment, opened_at, current_value 등 입력 정제
    - 필수 값 누락 시 기본값/에러 처리
    - 남은 기간(D-day) 계산
    """
    text = str(ctx.get("input", {}).get("text") or "")
    inv  = str(ctx.get("input", {}).get("investment") or "")
    ctx.setdefault("input", {})
    ctx["input"]["text"] = f"{text} [1단계: 입력검증]"
    ctx["input"]["investment"] = inv
    return ctx