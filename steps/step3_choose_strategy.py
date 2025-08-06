from services.strategy_service import recommend_strategy

def choose_strategy(ctx):
    """
    3단계: 전략 추천
    - 감정 + 투자 상태 기반 맞춤 전략 생성
    - 세제 혜택 D-day 고려
    """
    ctx["input"]["text"] = f"{ctx['input'].get('text','')} -> [3단계: 전략선택]"
    return ctx