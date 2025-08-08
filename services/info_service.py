def get_market_snapshot(user_query: str) -> dict:
    # 실제 정보 호출 대신 데모 스냅샷
    return {
        "summary": "오늘 시장은 보합권 혼조. 대형 기술주 강세, 에너지 약세.",
        "highlights": ["나스닥 +0.8%", "WTI 하락 → 에너지 섹터 약세", "미 10Y 금리 소폭 하락"],
    }