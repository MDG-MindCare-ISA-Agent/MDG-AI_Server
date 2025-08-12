import pandas as pd, numpy as np
from sqlalchemy import text
from .capm import get_beta, get_live_price_yf, rm_for_region, capm_expected_return
from ..deps import RF, RM_DOMESTIC, RM_GLOBAL

def load_user_assets(engine, user_name:str):
    with engine.begin() as conn:
        user = conn.execute(text("SELECT user_id, name, account_date FROM users WHERE name=:n"), {"n": user_name}).fetchone()
        if not user: raise ValueError(f"'{user_name}' 사용자를 찾을 수 없습니다.")
        user_id = int(user[0]); account_date = pd.to_datetime(user[2])

    q = """
    SELECT asset_id, user_id, type, name, ticker, region,
           ratio AS weight_pct, invested AS invested_amount, count, beta_override
    FROM assets WHERE user_id=:uid
    """
    df = pd.read_sql(text(q), engine, params={"uid": user_id})
    if df.empty: raise ValueError("해당 사용자의 자산이 없습니다.")
    return user_id, account_date, df

def enrich_capm(engine, df: pd.DataFrame):
    betas=[]
    for _, r in df.iterrows():
        beta=None
        if pd.notna(r.get('beta_override')): beta=float(r['beta_override'])
        elif pd.notna(r.get('ticker')): beta=get_beta(engine, r['ticker'])
        if beta is None: beta = 1.0 if str(r['region']).lower()=='domestic' else 1.2
        betas.append(beta)
    df=df.copy()
    df['beta_live']=betas
    df['rm_assigned']=df['region'].map(rm_for_region)
    df['expected_return']=df.apply(lambda r: capm_expected_return(r['beta_live'], RF, r['rm_assigned']), axis=1)
    df['기대 수익률 (%)']=(df['expected_return']*100).round(2)
    return df

def attach_live_values(df: pd.DataFrame):
    live_prices=[]; live_values=[]; live_returns=[]
    for _, r in df.iterrows():
        tkr=r.get('ticker'); qty=r.get('count'); inv=float(r['invested_amount']) if pd.notna(r['invested_amount']) else np.nan
        price=get_live_price_yf(tkr) if pd.notna(tkr) else None
        if (price is not None) and pd.notna(qty):
            try: val=float(price)*float(qty)
            except: val=np.nan
        else: val=np.nan
        if pd.notna(inv) and inv!=0 and pd.notna(val): rr=(val-inv)/inv
        else: rr=np.nan
        live_prices.append(price); live_values.append(val); live_returns.append(rr)
    df=df.copy()
    df['live_price']=live_prices
    df['current_value_live']=np.round(live_values,0)
    df['현재 수익률 (실시간 %)']=(np.array(live_returns)*100).round(2)
    safe_inv=df['invested_amount'].astype(float).replace(0, np.nan)
    df['현재 수익금(원)']=(df['current_value_live']-df['invested_amount']).round(0)
    df['현재 수익금(%)']=((df['current_value_live']/safe_inv-1.0)*100).round(2)
    return df

def maturity_projection(df: pd.DataFrame, account_date, today=None):
    today = pd.Timestamp.today().normalize() if today is None else pd.to_datetime(today)
    maturity_date = pd.to_datetime(account_date) + pd.DateOffset(years=3)
    years_left = max(0.0, (maturity_date - today).days/365.25)

    base_now_value = df['current_value_live'].astype(float).where(df['current_value_live'].notna(), df['invested_amount'].astype(float))
    w = df['invested_amount'].astype(float); w = w / w.sum()
    domestic_ratio = w[df['region']=='domestic'].sum(); global_ratio = w[df['region']=='global'].sum()

    if global_ratio>0:
        mix_rm = domestic_ratio*RM_DOMESTIC + global_ratio*RM_GLOBAL
        df['expected_return_mixRm']=df.apply(lambda r: capm_expected_return(r['beta_live'], RF, mix_rm), axis=1)
        df['기대 수익률_mixRm (%)']=(df['expected_return_mixRm']*100).round(2); r_col='expected_return_mixRm'
        mix_rm_msg=f"🔗 혼합 Rm 적용: {mix_rm:.4f} [domestic={domestic_ratio:.2%}, global={global_ratio:.2%}]"
    else:
        mix_rm=RM_DOMESTIC; r_col='expected_return'; mix_rm_msg=f"🔗 해외 0% → 국내 Rm({mix_rm:.4f}) 사용"

    r_annual = df[r_col].astype(float)
    df=df.copy()
    df['forecast_value_at_maturity']=(base_now_value*(1.0+r_annual)**years_left).round(0).astype('int64')
    df['만기까지 예상 누적수익률 (%)']=(((df['forecast_value_at_maturity']/base_now_value)-1.0)*100).round(2)

    df['만기 수익금(원,원금대비)']=(df['forecast_value_at_maturity']-df['invested_amount']).round(0)
    df['만기 수익금(%)']=((df['forecast_value_at_maturity']/df['invested_amount'].replace(0,np.nan)-1.0)*100).round(2)
    df['앞으로 기대수익(원,현재→만기)']=(df['forecast_value_at_maturity']-base_now_value).round(0)
    df['앞으로 기대수익(%)']=((df['forecast_value_at_maturity']/base_now_value-1.0)*100).round(2)

    current_total = float(base_now_value.sum())
    forecast_total = float(df['forecast_value_at_maturity'].sum())
    return df, years_left, current_total, forecast_total, mix_rm_msg