from ..prompts import FEW_SHOT_PROMPT_TEMPLATE, FINANCIAL_KNOWLEDGE
from ..services import hyperclova_client, guardrails
from ..services.emo_metrics import EmoMeter, intervention_text

def main():
    meter = EmoMeter()
    print("안녕하세요, 금융 심리 상담사입니다. 어떤 점이 고민이신가요? (종료하려면 '종료')")

    while True:
        user_text = input("🙂 사용자: ").strip()
        meter.tick()

        if user_text.lower() == "종료":
            print("상담을 종료하겠습니다. 오늘 대화가 마음을 조금이라도 가볍게 했길 바라요.")
            break

        if guardrails.triggered(user_text):
            bot = guardrails.reply()
        else:
            fewshot = FEW_SHOT_PROMPT_TEMPLATE.format(financial_knowledge=FINANCIAL_KNOWLEDGE, user_input=user_text)
            messages=[{"role":"system","content":"당신은 투자자들의 감정과 금융 상황을 함께 이해하고 공감해주는 금융 심리 상담사입니다."},
                      {"role":"user","content": fewshot}]
            meter.update(user_text)
            bot = hyperclova_client.chat(messages) or "연결이 잠시 불안정하네요. 한 단어로 지금 감정을 표현해주실 수 있을까요?"

        if meter.need_intervention():
            bot = f"{bot} {intervention_text()}"
            meter.start_cooldown()

        print(f"🤖 챗봇: {bot}")

if __name__ == "__main__":
    main()