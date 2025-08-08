# steps/step4_simulate_return.py
def simulate_return(ctx):
    """
    4단계 자리 보존: (향후) 수익률 분석/시뮬레이션 훅.
    지금은 아무 것도 하지 않고 그대로 반환합니다.
    """
    ctx["simulation"] = None
    return ctx