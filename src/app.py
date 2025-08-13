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
        "overall_cur": overall_cur,
        "overall_mat": overall_mat,
    }

def _diff_and_text(overall_cur, overall_mat):
    """세후수익 차이(diff)와 비교 문구를 동시에 반환"""
    try:
        cur_profit = float(overall_cur['total_after_tax_profit'].iloc[0])
        mat_profit = float(overall_mat['total_after_tax_profit'].iloc[0])
        diff = mat_profit - cur_profit
        if diff > 0:
            txt = f"3년 유지 시, 현재 해지보다 세후 수익이 약 {diff:,.0f}원 더 높습니다."
        elif diff < 0:
            txt = f"현재 해지 시, 3년 유지보다 세후 수익이 약 {-diff:,.0f}원 더 높습니다."
        else:
            txt = "두 시나리오의 세후 수익 차이는 없습니다."
        return diff, txt
    except Exception:
        return None, "두 시나리오 비교 데이터를 불러오지 못했습니다."

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

def build_comparison_text(overall_cur, overall_mat):
    try:
        cur_profit = float(overall_cur['total_after_tax_profit'].iloc[0])
        mat_profit = float(overall_mat['total_after_tax_profit'].iloc[0])
        diff = mat_profit - cur_profit
        if diff > 0:
            return diff, f"3년 유지 시, 현재 해지보다 세후 수익이 약 {diff:,.0f}원 더 높습니다."
        elif diff < 0:
            return diff, f"현재 해지 시, 3년 유지보다 세후 수익이 약 {(-diff):,.0f}원 더 높습니다."
        else:
            return 0.0, "두 시나리오의 세후 수익 차이는 없습니다."
    except Exception:
        return None, "두 시나리오 비교 데이터를 불러오지 못했습니다."

def build_encouragement(summary: dict, diff_profit: float | None) -> str:
    emotion = (summary or {}).get("감정") or "중립"
    tendency = (summary or {}).get("성향") or "중립적"

    # 어떤 선택이 유리한지에 따라 톤을 달리한다.
    if diff_profit is None:
        headline = "데이터 확인에 약간의 문제가 있었어요."
        tip = "조금만 있다가 다시 시도하면 정상적으로 비교가 가능할 거예요."
    elif diff_profit > 0:
        headline = "숫자 기준으로는 ‘3년 유지’가 더 유리해 보여요."
        tip = "세후 수익이 더 커질 여지가 있으니, 급하지 않다면 계획대로 유지하는 쪽을 검토해보세요."
    elif diff_profit < 0:
        headline = "숫자 기준으로는 ‘현재 해지’가 상대적으로 유리해 보여요."
        tip = "필요 자금·리스크 허용도까지 함께 고려해, 일부만 정리하는 전략도 선택지예요."
    else:
        headline = "두 선택의 차이가 크지 않아요."
        tip = "현금흐름·목표 시점 등 비재무적 요인을 반영해 결정해보면 좋아요."

    # 감정/성향 맞춤 한 줄
    emo_map = {
        "불안": "불안하게 느끼는 건 너무 자연스러워요. 정보로 차근차근 확인하면 충분히 잘 하실 수 있어요.",
        "혼란": "정보가 많아 혼란스러울 수 있어요. 핵심 숫자만 잡고 한 단계씩 정리해봐요.",
        "후회": "과거 판단에 너무 매이지 마세요. 오늘의 선택이 내일의 방향을 만듭니다.",
        "기대": "기대가 있을 때일수록 기본 가정을 점검하면 더 견고해져요.",
        "기쁨": "좋은 흐름일 때 원칙을 재확인하면 성과를 오래 끌고 갈 수 있어요.",
        "중립": "차분히 숫자를 확인하고 원칙대로 가면 충분합니다.",
    }
    emo_line = emo_map.get(emotion, emo_map["중립"])

    tend_map = {
        "안정적": "안정 추구 성향이라면 분산과 현금버퍼를 유지하며 결정해보세요.",
        "중립적": "수익/리스크 균형을 기준으로 포지션을 일부 조정하는 전략이 잘 맞습니다.",
        "공격적": "수익 기대가 크더라도 손실 한도와 기간 규칙을 함께 세워주세요.",
    }
    tend_line = tend_map.get(tendency, tend_map["중립적"])

    return f"{headline}\n{emo_line}\n{tend_line}\n{tip}"

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
        comparison_text = None
        reports = None  
        diff_profit = None 
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
                comparison_text = build_comparison_text(
                    result["overall_cur"], result["overall_mat"]
                )

                diff_profit, comparison_text = build_comparison_text(
                    result["overall_cur"], result["overall_mat"]
                )
            
                pc = result["report_prompts"]["current"]
                pm = result["report_prompts"]["maturity"]

                try:
                    current_report = hyperclova_client.chat([
                        {"role": "system", "content": "당신은 수치 근거로 간결하게 말하는 금융 상담가입니다."},
                        {"role": "user", "content": pc},
                    ])
                except Exception:
                    current_report = "현재 해지 리포트를 생성하지 못했습니다."

                try:
                    maturity_report = hyperclova_client.chat([
                        {"role": "system", "content": "당신은 수치 근거로 간결하게 말하는 금융 상담가입니다."},
                        {"role": "user", "content": pm},
                    ])
                except Exception:
                    maturity_report = "3년 유지 리포트를 생성하지 못했습니다."

                reports = {
                    "current": current_report,
                    "maturity": maturity_report,
                }
            except Exception:
                sim = None

        encouragement = build_encouragement(summary, diff_profit)

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
            "comparison": comparison_text,
            "encouragement": encouragement,  
            "reports": reports,
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
        name = session_state["name"]
        # 안전장치: 이름 없으면 재요청
        if not name:
            session_state["await_name"] = True
            reply = "어떤 사용자의 포트폴리오를 볼까요? 이름을 알려주세요. (예: 이현주)"
            conversation_log.extend([
                {"role": "user", "content": txt},
                {"role": "assistant", "content": reply},
            ])
            return {"reply": reply, "metrics": {"anxiety": meter.anxiety, "loss_aversion": meter.loss_aversion}}

        # 최신 포트폴리오/프롬프트/비교 데이터 로드
        try:
            result = build_portfolio_for_user(name)
        except Exception:
            reply = "요약을 불러오지 못했어요. 잠시 뒤 다시 시도해 주세요."
            conversation_log.extend([
                {"role": "user", "content": txt},
                {"role": "assistant", "content": reply},
            ])
            return {"reply": reply, "metrics": {"anxiety": meter.anxiety, "loss_aversion": meter.loss_aversion}}

        last_portfolio["name"] = name
        last_portfolio["prompts"] = result["report_prompts"]

        # 비교(차액 + 문구)
        diff_profit, comparison_text = _diff_and_text(result["overall_cur"], result["overall_mat"])
        # 세션 요약(감정/성향) 기반 응원
        session_summary = build_session_summary()
        encouragement = build_encouragement(session_summary, diff_profit)

        # 선택지: 현재해지
        if is_select_current(txt):
            pc = result["report_prompts"]["current"]
            try:
                current_report = hyperclova_client.chat([
                    {"role": "system", "content": "당신은 수치 근거로 간결하게 말하는 금융 상담가입니다."},
                    {"role": "user", "content": pc},
                ])
            except Exception:
                current_report = "현재 해지 리포트를 생성하지 못했습니다."

            reply = f"'{name}'님의 현재 해지 리포트를 정리했어요."
            conversation_log.extend([
                {"role": "user", "content": txt},
                {"role": "assistant", "content": reply},
            ])
            return {
                "reply": reply,
                "reports": {"current": current_report},
                "metrics": {"anxiety": meter.anxiety, "loss_aversion": meter.loss_aversion},
            }

        # 선택지: 3년유지
        if is_select_maturity(txt):
            pm = result["report_prompts"]["maturity"]
            try:
                maturity_report = hyperclova_client.chat([
                    {"role": "system", "content": "당신은 수치 근거로 간결하게 말하는 금융 상담가입니다."},
                    {"role": "user", "content": pm},
                ])
            except Exception:
                maturity_report = "3년 유지 리포트를 생성하지 못했습니다."

            reply = f"'{name}'님의 3년 유지 리포트를 정리했어요."
            conversation_log.extend([
                {"role": "user", "content": txt},
                {"role": "assistant", "content": reply},
            ])
            return {
                "reply": reply,
                "reports": {"maturity": maturity_report}, 
                "metrics": {"anxiety": meter.anxiety, "loss_aversion": meter.loss_aversion},
            }

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