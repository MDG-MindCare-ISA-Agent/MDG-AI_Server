# pipeline.py
from typing import Dict, Any
from services.memory_service import load_history, save_turn, set_last_options
from steps import (
    step1_parse_validate,
    step2_analyze_emotion,
    step2b_route_plan,
    step3a_fetch_info,
    step3_choose_strategy,
    step4_simulate_return,
    step5_format_output,
)

def run_pipeline(pipeline_name: str, payload: Dict[str, Any], convo_id: str) -> Dict[str, Any]:
    ctx: Dict[str, Any] = {
        "_meta": {"pipeline": pipeline_name, "convo_id": convo_id},
        "input": payload or {},
        "history": load_history(convo_id),
    }

    ctx = step1_parse_validate.parse_and_validate(ctx)
    ctx = step2_analyze_emotion.analyze_emotion(ctx)
    ctx = step2b_route_plan.route_plan(ctx)
    ctx = step3a_fetch_info.fetch_info(ctx)
    ctx = step3_choose_strategy.choose_strategy(ctx)
    ctx = step4_simulate_return.simulate_return(ctx)
    ctx = step5_format_output.format_output(ctx)

    output = ctx["output"]

    # 이번 턴에 제시한 선택지 저장 → 다음 턴 "1번해줘" 매핑
    if output.get("_choices"):
        set_last_options(convo_id, output["_choices"])

    # 히스토리 저장
    user_record = {
        "text": payload.get("text", ""),
        "investment": payload.get("investment"),
        "pick": payload.get("pick"),
        "strategies": payload.get("strategies"),
    }
    save_turn(convo_id, user_record, output)
    return output