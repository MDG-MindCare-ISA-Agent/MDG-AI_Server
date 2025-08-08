# steps/step4_simulate_return.py
from routing import needs_simulation
from services.simulation_service import run_simulation

def simulate_return(ctx):
    """
    4단계: 수익률 시뮬레이션
    - 선택된 전략(target_allocations)과 기간 기반으로 시나리오 계산
    """
    if not needs_simulation(ctx):
        ctx["simulation"] = None
        return ctx
    strategy = ctx.get("strategy") or {}
    horizon_months = ctx.get("input", {}).get("horizon_months", 12)
    ctx["simulation"] = run_simulation(strategy, horizon_months=horizon_months)
    return ctx