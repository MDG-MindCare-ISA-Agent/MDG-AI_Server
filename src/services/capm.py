import re, requests, numpy as np, pandas as pd, datetime as dt
from sqlalchemy import text
import yfinance as yf
from ..deps import RF, RM_DOMESTIC, RM_GLOBAL, BETA_TTL_DAYS

def rm_for_region(region:str)->float:
    return RM_GLOBAL if str(region).lower()=="global" else RM_DOMESTIC

def capm_expected_return(beta: float, rf: float, rm: float) -> float:
    return float(rf) + float(beta)*(float(rm)-float(rf))

def fetch_beta_from_yahoo(ticker: str):
    try:
        t = yf.Ticker(ticker); info = t.info
        for k in ("beta","beta3Year","beta_3y"):
            if info.get(k) is not None: return float(info[k])
    except Exception: pass
    try:
        url=f"https://finance.yahoo.com/quote/{ticker}/key-statistics?p={ticker}"
        html=requests.get(url,timeout=8).text
        m=re.search(r'Beta \(5Y Monthly\).*?>([-+]?\d*\.\d+|\d+)<', html)
        if m: return float(m.group(1))
    except Exception: pass
    return None

def get_beta(engine, ticker: str, force_refresh=False, ttl_days=BETA_TTL_DAYS):
    with engine.begin() as conn:
        if not force_refresh:
            row=conn.execute(text("""
              SELECT beta, fetched_at FROM capm_beta_cache
              WHERE ticker=:t AND source='yahoo'
            """), {"t": ticker}).fetchone()
            if row:
                beta, fetched_at = float(row[0]), row[1]
                if fetched_at and (dt.datetime.utcnow()-fetched_at.replace(tzinfo=None) <= dt.timedelta(days=ttl_days)):
                    return beta
        beta=fetch_beta_from_yahoo(ticker)
        if beta is not None:
            conn.execute(text("""
              INSERT INTO capm_beta_cache (ticker, source, beta, fetched_at)
              VALUES (:t,'yahoo',:b,UTC_TIMESTAMP())
              ON DUPLICATE KEY UPDATE beta=:b, fetched_at=UTC_TIMESTAMP()
            """), {"t": ticker, "b": beta})
        return beta

def get_live_price_yf(ticker:str):
    if not ticker: return None
    try:
        t=yf.Ticker(ticker); finfo=getattr(t,'fast_info',{}) or {}
        for k in ('last_price','lastPrice','regularMarketPrice','previousClose'):
            v=finfo.get(k)
            if v is not None and np.isfinite(v): return float(v)
        hist=t.history(period='5d')
        if len(hist)>0: return float(hist['Close'].dropna()[-1])
    except Exception: pass
    return None