# src/app.py
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse
from pathlib import Path
from pydantic import BaseModel

# --- 내부 모듈 ---
from .deps import get_engine
from .prompts import FEW_SHOT_PROMPT_TEMPLATE, FINANCIAL_KNOWLEDGE
from .services import guardrails, hyperclova_client
from .services.emo_metrics import EmoMeter, intervention_text
from .services.portfolio import (
    load_user_assets,
    enrich_capm,
    attach_live_values,
    maturity_projection,
)
from .services.isa_tax import (
    run_isa_tax_calculation,
    merge_with_investment,
    summarize_overall,
    build_prompt,
)

import pandas as pd
from sqlalchemy import text  # ✅ 이름 존재 여부 체크용

app = FastAPI(title="ISA Psy Finance API")

# === 상태 ===
meter = EmoMeter()
conversation_log: list[dict] = []

# 세션 상태: 처음엔 이름을 먼저 받는다
session_state = {
    "await_name": True,
    "name": None,
}

# 포트폴리오 컨텍스트(선택지 프롬프트 캐시)
last_portfolio = {
    "name": None,               # 마지막으로 조회한 사용자 이름
    "prompts": None,            # {"current": "...", "maturity": "..."}
}

class ChatIn(BaseModel):
    text: str

# ===== 공용 유틸 =====
def is_portfolio_intent(txt: str) -> bool:
    t = txt.replace(" ", "")
    return any(k in t for k in ("포트폴리오", "요약", "자산", "isa", "ISA"))

def is_select_current(txt: str) -> bool:
    t = txt.replace(" ", "")
    return any(k in t for k in ("현재해지", "중도해지", "중도", "해지", "현재"))

def is_select_maturity(txt: str) -> bool:
    t = txt.replace(" ", "")
    return any(k in t for k in ("3년유지", "3년", "유지", "만기", "만기유지"))

def build_portfolio_for_user(user_name: str):
    """
    DB에서 사용자의 자산 불러와 CAPM/실시간/만기 예측/세제까지 계산하고
    '현재 해지' / '3년 유지' 각각의 설명용 프롬프트를 만들어 반환.
    """
    engine = get_engine()

    # 1) 사용자 및 자산 로드
    user_id, account_date, df = load_user_assets(engine, user_name)

    # 2) CAPM 보강 + 실시간 가격
    df = enrich_capm(engine, df)
    df = attach_live_values(df)

    # 3) 만기 예측
    df, years_left, current_total, forecast_total, mix_rm_msg = maturity_projection(df, account_date)

    # 4) 세제 계산을 위해 users 테이블/현재/만기 수익금 dict 준비
    df_users = pd.read_sql("SELECT * FROM users", engine)
    current_profit_dict = df.set_index('name')['현재 수익금(원)'].to_dict()
    maturity_profit_dict = df.set_index('name')['만기 수익금(원,원금대비)'].to_dict()

    # 5) ISA 세금 케이스: 현재 해지 vs 3년 유지
    df_cur, df_mat = run_isa_tax_calculation(
        df=df, df_users=df_users,
        current_profit_dict=current_profit_dict,
        maturity_profit_dict=maturity_profit_dict,
        is_current_period_met=False,
        is_maturity_period_met=True
    )
    df_cur = merge_with_investment(df_cur, df)
    df_mat = merge_with_investment(df_mat, df)
    overall_cur = summarize_overall(df_cur, "현재 해지(중도)")
    overall_mat = summarize_overall(df_mat, "3년 만기(유지)")

    # 6) 설명용 프롬프트 생성
    user_state_stub = {}  # 감정/성향을 아직 안 쓰면 빈 dict로도 build_prompt 동작
    prompt_cur = build_prompt(df_cur, overall_cur, "현재 해지(중도)", user_state_stub)
    prompt_mat = build_prompt(df_mat, overall_mat, "3년 만기(유지)", user_state_stub)

    return {
        "mix_rm_msg": mix_rm_msg,
        "years_left": years_left,
        "current_total": current_total,
        "forecast_total": forecast_total,
        "report_prompts": {"current": prompt_cur, "maturity": prompt_mat},
    }

# --- 세션 요약용: 대화 로그로 감정/성향 뽑아내기 ---
def finalize_profile_from_log(conv_log: list[str] | list[dict]) -> tuple[str | None, str | None]:
    # compact history
    history_lines = []
    for turn in conv_log[-60:]:
        if isinstance(turn, dict):
            prefix = "유저" if turn.get("role") == "user" else "상담사"
            history_lines.append(f"{prefix}: {turn.get('content','')}")
        else:
            history_lines.append(str(turn))
    history_text = "\n".join(history_lines)

    prompt = f"""
아래는 유저와 상담사의 대화 기록입니다. 이 기록만을 근거로 유저의 현재 감정과 투자 성향을 간결하게 추정하세요.
- 감정은 핵심 1개(불안/후회/혼란/기대/기쁨/중립)
- 성향은 '안정적' / '중립적' / '공격적' 중 하나
- 설명 없이 JSON만

대화 기록:
{history_text}

반드시 아래 형태의 JSON만 출력:
{{
  "감정": "<한 단어>",
  "성향": "<안정적|중립적|공격적>"
}}
""".strip()

    try:
        content = hyperclova_client.chat([
            {"role": "system", "content": "너는 대화 로그로부터 사용자의 감정과 투자 성향을 한 번에 추정하여 JSON만 반환하는 분석기다."},
            {"role": "user", "content": prompt},
        ])
    except Exception:
        return None, None

    import json
    try:
        data = json.loads(content)
    except Exception:
        try:
            s = content.find("{"); e = content.rfind("}") + 1
            data = json.loads(content[s:e]) if s != -1 and e != -1 else {}
        except Exception:
            data = {}
    return data.get("감정"), data.get("성향")

def build_session_summary():
    emotion, tendency = finalize_profile_from_log(conversation_log)
    return {
        "감정": emotion,
        "성향": tendency,
        "불안지수": round(meter.anxiety, 2),
        "회피성향": round(meter.loss_aversion, 2),
    }

# ===== 라우트 =====
@app.get("/health")
def health():
    return {"ok": True}

@app.get("/", response_class=HTMLResponse)
def root_page():
    html_path = Path(__file__).parent / "templates" / "chat.html"
    if not html_path.exists():
        return HTMLResponse("<h1>chat.html 파일이 없습니다.</h1>", status_code=500)
    return HTMLResponse(html_path.read_text(encoding="utf-8"))

@app.get("/portfolio/summary")
def portfolio_summary(user_name: str = Query(..., description="예: 이현주")):
    try:
        result = build_portfolio_for_user(user_name)
    except ValueError as e:
        raise HTTPException(404, str(e))
    return result

@app.post("/chat")
def chat(in_: ChatIn):
    txt = in_.text.strip()
    meter.tick()

    # 0) 세션 시작: '첫 메시지 = 이름' (✅ 존재 검증 추가)
    if session_state["await_name"]:
        name_try = txt
        engine = get_engine()
        exists = False
        try:
            with engine.begin() as conn:
                row = conn.execute(text("SELECT 1 FROM users WHERE name=:n LIMIT 1"), {"n": name_try}).fetchone()
                exists = row is not None
        except Exception:
            # DB 오류 시에도 안전하게 이름 재요청
            exists = False

        if not exists:
            reply = f"'{name_try}'라는 이름을 찾지 못했어요. 등록된 성함으로 다시 입력해 주세요."
            conversation_log.extend([
                {"role": "user", "content": txt},
                {"role": "assistant", "content": reply},
            ])
            # 계속 이름 대기 상태 유지
            session_state["await_name"] = True
            session_state["name"] = None
            last_portfolio["name"] = None
            last_portfolio["prompts"] = None
            return {"reply": reply, "metrics": {"anxiety": meter.anxiety, "loss_aversion": meter.loss_aversion}}

        # 존재하는 이름 → 세션 확정
        session_state["name"] = name_try
        session_state["await_name"] = False
        last_portfolio["name"] = name_try
        last_portfolio["prompts"] = None

        reply = (
            f"{name_try} 고객님, 반갑습니다. 어떤 것을 도와드릴까요? "
            "포트폴리오 요약이 필요하시면 '포트폴리오'라고 말씀해 주세요. "
            "(대화를 마치실 땐 '종료'를 입력하면 요약과 시뮬레이션을 한 번에 보여드려요)"
        )
        conversation_log.extend([
            {"role": "user", "content": txt},
            {"role": "assistant", "content": reply},
        ])
        return {"reply": reply, "metrics": {"anxiety": meter.anxiety, "loss_aversion": meter.loss_aversion}}

    # === 종료 분기 ===
    if txt in ("종료", "그만", "quit", "exit"):
        summary = build_session_summary()

        # 세션 이름이 있으면 시뮬도 함께 반환
        sim = None
        if session_state["name"]:
            try:
                result = build_portfolio_for_user(session_state["name"])
                last_portfolio["prompts"] = result["report_prompts"]
                sim = {
                    "name": session_state["name"],
                    "years_left": result["years_left"],
                    "current_total": result["current_total"],
                    "forecast_total": result["forecast_total"],
                    "mix_rm_msg": result["mix_rm_msg"],
                }
            except Exception:
                sim = None

        reply = "상담을 종료할게요. 요약과 포트폴리오 시뮬 결과를 아래에 정리했어요."
        conversation_log.extend([
            {"role": "user", "content": txt},
            {"role": "assistant", "content": reply},
        ])

        # 안전 리셋 (reset() 없을 때 직접 0으로)
        try:
            meter.reset()  # 있으면 사용
        except AttributeError:
            meter.anxiety = 0.0
            meter.loss_aversion = 0.0
            if hasattr(meter, "cooldown"):
                meter.cooldown = 0
            if hasattr(meter, "last_ts"):
                meter.last_ts = None

        # 포트폴리오 흐름/로그 초기화
        last_portfolio["name"] = None
        last_portfolio["prompts"] = None
        conversation_log.clear()

        # 다음 세션을 위해 이름 재요청 모드로 복귀
        session_state["await_name"] = True
        session_state["name"] = None

        return {
            "reply": reply,
            "summary_preface": "대화를 기반으로 산출된 불안도와 회피도입니다.",
            "summary": summary,
            "simulation": sim,
            "metrics": {"anxiety": summary["불안지수"], "loss_aversion": summary["회피성향"]},
        }

    # 1) 포트폴리오 트리거: 저장된 이름으로 즉시 준비
    if is_portfolio_intent(txt):
        name = session_state["name"]
        if not name:
            # 이례적 상태: 이름 없으면 다시 받기
            session_state["await_name"] = True
            reply = "어떤 사용자의 포트폴리오를 볼까요? 이름을 알려주세요. (예: 이현주)"
            conversation_log.extend([
                {"role": "user", "content": txt},
                {"role": "assistant", "content": reply},
            ])
            return {"reply": reply, "metrics": {"anxiety": meter.anxiety, "loss_aversion": meter.loss_aversion}}

        try:
            result = build_portfolio_for_user(name)
        except ValueError:
            # DB에 이름이 없으면 재요청
            session_state["await_name"] = True
            session_state["name"] = None
            last_portfolio["name"] = None
            last_portfolio["prompts"] = None
            reply = f"'{name}' 사용자를 찾지 못했어요. 성함을 다시 알려주시면 재시도할게요."
            conversation_log.extend([
                {"role": "user", "content": txt},
                {"role": "assistant", "content": reply},
            ])
            return {"reply": reply, "metrics": {"anxiety": meter.anxiety, "loss_aversion": meter.loss_aversion}}

        # 성공: 선택지 프롬프트 캐시
        last_portfolio["name"] = name
        last_portfolio["prompts"] = result["report_prompts"]
        reply = f"'{name}'님의 포트폴리오 요약을 준비했어요. '현재 해지' 또는 '3년 유지' 중에 선택해 주세요."
        conversation_log.extend([
            {"role": "user", "content": txt},
            {"role": "assistant", "content": reply},
        ])
        return {"reply": reply, "metrics": {"anxiety": meter.anxiety, "loss_aversion": meter.loss_aversion}}

    # 2) 포트폴리오 선택지 응답
    if last_portfolio.get("prompts"):
        if is_select_current(txt):
            prompt = last_portfolio["prompts"]["current"]
            try:
                reply = hyperclova_client.chat([
                    {"role": "system", "content": "당신은 투자자에게 ISA 세금/혜택/기대수익을 오해 없이 쉽게 설명하는 상담사입니다."},
                    {"role": "user", "content": prompt},
                ])
            except Exception:
                reply = "지금은 요약을 불러오지 못했어요. 잠시 뒤 다시 요청해 주실까요?"
            conversation_log.extend([
                {"role": "user", "content": txt},
                {"role": "assistant", "content": reply},
            ])
            return {"reply": reply, "metrics": {"anxiety": meter.anxiety, "loss_aversion": meter.loss_aversion}}

        if is_select_maturity(txt):
            prompt = last_portfolio["prompts"]["maturity"]
            try:
                reply = hyperclova_client.chat([
                    {"role": "system", "content": "당신은 투자자에게 ISA 세금/혜택/기대수익을 오해 없이 쉽게 설명하는 상담사입니다."},
                    {"role": "user", "content": prompt},
                ])
            except Exception:
                reply = "지금은 요약을 불러오지 못했어요. 잠시 뒤 다시 요청해 주실까요?"
            conversation_log.extend([
                {"role": "user", "content": txt},
                {"role": "assistant", "content": reply},
            ])
            return {"reply": reply, "metrics": {"anxiety": meter.anxiety, "loss_aversion": meter.loss_aversion}}

    # 3) 일반 공감 챗 (가드레일→감정 프롬프트)
    if guardrails.triggered(txt):
        reply = guardrails.reply()
    else:
        fewshot = FEW_SHOT_PROMPT_TEMPLATE.format(
            financial_knowledge=FINANCIAL_KNOWLEDGE,
            user_input=txt,
        )
        messages = [
            {"role": "system", "content": "당신은 투자자들의 감정과 금융 상황을 함께 이해하고 공감해주는 금융 심리 상담사입니다."},
            {"role": "user", "content": fewshot},
        ]

        # 감정 메트릭 업데이트
        meter.update(txt)

        try:
            reply = hyperclova_client.chat(messages) or "연결이 잠시 불안정하네요. 한 단어로 지금 감정을 표현해주실 수 있을까요?"
        except Exception:
            reply = "연결이 잠시 불안정하네요. 한 단어로 지금 감정을 표현해주실 수 있을까요?"

    # 필요 시 1회 개입 문구 부착
    if meter.need_intervention():
        reply = f"{reply} {intervention_text()}"
        meter.start_cooldown()

    conversation_log.append({"role":"user","content":txt})
    conversation_log.append({"role":"assistant","content":reply})

    return {"reply": reply, "metrics": {"anxiety": meter.anxiety, "loss_aversion": meter.loss_aversion}}

# === 개발용: 직접 실행 ===
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.app:app", host="0.0.0.0", port=8000, reload=True)