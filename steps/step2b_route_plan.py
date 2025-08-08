# steps/step2b_route_plan.py
from routing import derive_plan

def route_plan(ctx):
    """2.5단계: emotion.type 기반 실행 플랜 결정."""
    return derive_plan(ctx)