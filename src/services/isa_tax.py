from typing import Dict, Any, Tuple
import pandas as pd
import numpy as np

def format_krw(x):
    try:
        return f"{int(round(float(x))):,}원"
    except Exception:
        return "-"

def safe_div(a, b):
    if b is None:
        return None
    try:
        b = float(b)
        if b == 0 or (isinstance(b, float) and np.isnan(b)):
            return None
        return float(a) / b
    except Exception:
        return None


# ---- A. 전처리 ----
def prepare_isa_data(df_users: pd.DataFrame, df_assets: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
    df_users = df_users.copy()
    df_assets = df_assets.copy()

    df_users['tax_free_limit'] = np.where(
        df_users['isa_user_type'] == '일반형', 2_000_000, 4_000_000
    )

    df_assets['tax_category'] = df_assets['type']
    if 'region' in df_assets.columns:
        mask_etf = df_assets['type'].str.strip().str.lower().str.contains('etf')
        region_norm = df_assets['region'].fillna('').str.strip().str.lower()
        df_assets.loc[df_assets['type'].str.strip().str.lower() == '채권 etf', 'tax_category'] = '채권 ETF'
        df_assets.loc[mask_etf & (region_norm=='domestic') & (df_assets['tax_category']!='채권 ETF'), 'tax_category'] = '국내 ETF'
        df_assets.loc[mask_etf & (region_norm=='global'), 'tax_category'] = '해외 ETF'
    return df_users, df_assets

# ---- B. 세금 계산 ----
def calculate_taxed_profit(profit: Any, is_isa_period_met: bool, asset_type: str, isa_limit_override: int):
    if isinstance(profit, dict):
        capital_gain = float(profit.get('capital_gain', 0.0))
        distribution = float(profit.get('distribution', 0.0))
    else:
        capital_gain = float(profit)
        distribution = 0.0

    total = capital_gain + distribution
    if total <= 0:
        return total, 0.0, {'notes': '손실 구간 과세 없음'}

    valid = {
        '주식': 'KR_STOCK', '채권': 'BOND', '채권 ETF': 'BOND_ETF',
        '국내 ETF': 'KR_ETF', '해외 ETF': 'OVERSEAS_ETF', 'REITs': 'REITS_FUND', '리츠': 'REITS_FUND',
    }
    atype = valid.get(asset_type, 'UNSUPPORTED')
    if atype == 'UNSUPPORTED':
        return total, 0.0, {'notes': f'지원 외 유형: {asset_type}'}

    isa_limit = int(isa_limit_override)

    def isa_9p9(amount: float):
        taxable = max(0.0, amount - isa_limit)
        tax = taxable * 0.099
        return amount - tax, tax

    # 중도해지 => ISA 요건 미충족
    if not is_isa_period_met:
        if atype in ('BOND','BOND_ETF','REITS_FUND','OVERSEAS_ETF'):
            tax = total * 0.154
            return total - tax, tax, {'notes': '중도해지: 일반계좌 15.4% 일괄'}
        if atype == 'KR_ETF':
            tax = distribution * 0.154
            after = capital_gain + (distribution - tax)
            return after, tax, {'notes': '중도해지: 국내 주식형 ETF 분배금 15.4%, 매매차익 0%'}
    
    # ISA 요건 충족
    if atype in ('BOND','BOND_ETF','REITS_FUND','OVERSEAS_ETF'):
        after, tax = isa_9p9(total)
        return after, tax, {'notes': f'ISA 충족: {asset_type} 손익통산, 한도내 0%/초과 9.9%'}

    if atype == 'KR_ETF':
        tax_dist = distribution * 0.154
        net = capital_gain + (distribution - tax_dist)
        if net <= isa_limit:
            return net, tax_dist, {'notes': 'ISA 충족: 국내 주식형 ETF 분배금 15.4%, 한도내 추가과세 없음'}
        extra = (net - isa_limit) * 0.099
        return net - extra, tax_dist + extra, {'notes': 'ISA 충족: 분배금 15.4% + 한도초과 9.9% 추가'}

    if atype == 'KR_STOCK':
        return total, 0.0, {'notes': '국내주식 매매차익 비과세'}

    return total, 0.0, {'notes': '세금 계산 예외 발생'}

# ---- C. 메인 실행 ----
def run_isa_tax_calculation(
    df: pd.DataFrame, df_users: pd.DataFrame,
    current_profit_dict, maturity_profit_dict,
    is_current_period_met: bool, is_maturity_period_met: bool
):
    df_users_processed, df_assets_processed = prepare_isa_data(df_users, df)
    df_merged = pd.merge(df_assets_processed, df_users_processed, on='user_id')

    # 현재
    rows_cur=[]
    for _, row in df_merged.iterrows():
        asset_name = row['name_x']; user_name = row['name_y']
        profit_data = current_profit_dict.get(asset_name, 0)
        after_tax_profit, tax_amount, notes = calculate_taxed_profit(
            profit=profit_data, is_isa_period_met=is_current_period_met,
            asset_type=row['tax_category'], isa_limit_override=row['tax_free_limit']
        )
        rows_cur.append({
            'user_id': row['user_id'],'user_name': user_name,'asset_name': asset_name,
            'total_profit_before_tax': profit_data,'tax_amount': tax_amount,'after_tax_profit': after_tax_profit,'notes': notes['notes']
        })
    df_cur = pd.DataFrame(rows_cur)

    # 만기
    rows_mat=[]
    for _, row in df_merged.iterrows():
        asset_name = row['name_x']; user_name = row['name_y']
        profit_data = maturity_profit_dict.get(asset_name, 0)
        after_tax_profit, tax_amount, notes = calculate_taxed_profit(
            profit=profit_data, is_isa_period_met=is_maturity_period_met,
            asset_type=row['tax_category'], isa_limit_override=row['tax_free_limit']
        )
        rows_mat.append({
            'user_id': row['user_id'],'user_name': user_name,'asset_name': asset_name,
            'total_profit_before_tax': profit_data,'tax_amount': tax_amount,'after_tax_profit': after_tax_profit,'notes': notes['notes']
        })
    df_mat = pd.DataFrame(rows_mat)
    return df_cur, df_mat

# ---- D. 머지/요약/프롬프트 ----

def merge_with_investment(results_df: pd.DataFrame, assets_df: pd.DataFrame) -> pd.DataFrame:
    df = results_df.copy()
    res_inv_col = None
    for cand in ['invested_amount','invested','investment']:
        if cand in df.columns: res_inv_col=cand; break
    if res_inv_col is not None:
        df['invested']=pd.to_numeric(df[res_inv_col], errors='coerce')
    else:
        df['invested']=pd.NA

    asset_inv_col=None
    for cand in ['invested','investment','invested_amount']:
        if cand in assets_df.columns: asset_inv_col=cand; break
    if asset_inv_col is None:
        raise KeyError("assets_df에 투자금 컬럼 필요")

    need=df['invested'].isna()
    if need.any():
        tmp=assets_df[['user_id','name',asset_inv_col]].rename(columns={'name':'_asset_name', asset_inv_col:'_inv'})
        df=df.merge(tmp, left_on=['user_id','asset_name'], right_on=['user_id','_asset_name'], how='left').drop(columns=['_asset_name'])
        df.loc[need,'invested']=pd.to_numeric(df.loc[need,'_inv'], errors='coerce')
        df=df.drop(columns=['_inv'])

    df['after_tax_profit']=pd.to_numeric(df['after_tax_profit'], errors='coerce')
    def _rate(r):
        d=safe_div(r.get('after_tax_profit'), r.get('invested'))
        return d*100 if d is not None else None
    df['profit_rate']=df.apply(_rate, axis=1)
    return df

def summarize_overall(results_merged: pd.DataFrame, scenario_name: str) -> pd.DataFrame:
    grp = results_merged.groupby(['user_id','user_name'], as_index=False).agg(
        total_invested=('invested','sum'),
        total_after_tax_profit=('after_tax_profit','sum')
    )
    def _rate(r):
        d=safe_div(r['total_after_tax_profit'], r['total_invested'])
        return d*100 if d is not None else None
    grp['overall_profit_rate']=grp.apply(_rate, axis=1)
    grp['scenario']=scenario_name
    return grp[['scenario','user_id','user_name','total_invested','total_after_tax_profit','overall_profit_rate']]

def format_krw(x):
    try: return f"{int(round(x)):,}원"
    except: return "-"

def summarize_rows_for_prompt(df: pd.DataFrame) -> str:
    lines=[]
    for _, r in df.iterrows():
        inv=r.get('invested'); aft=r.get('after_tax_profit'); pr=r.get('profit_rate')
        line=f"- {r['asset_name']}: 투자금 {format_krw(inv)}, 세후 수익 {format_krw(aft)}, 손익률 {('%.2f%%' % pr) if pr is not None else 'N/A'}"
        notes=str(r.get('notes','') or '').strip()
        if notes: line+=f" | 참고: {notes}"
        lines.append(line)
    return "\n".join(lines)

def summarize_overall_for_prompt(overall_df: pd.DataFrame) -> str:
    lines=[]
    for _, r in overall_df.iterrows():
        lines.append(
            f"[{r['scenario']}] {r['user_name']} 총 투자금 {format_krw(r['total_invested'])}, "
            f"총 세후수익 {format_krw(r['total_after_tax_profit'])}, "
            f"총 손익률 {('%.2f%%' % r['overall_profit_rate']) if r['overall_profit_rate'] is not None else 'N/A'}"
        )
    return "\n".join(lines)

def build_prompt(results_merged: pd.DataFrame, overall_df: pd.DataFrame, scenario_name: str, user_state: dict) -> str:
    rows_text = summarize_rows_for_prompt(results_merged)
    overall_text = summarize_overall_for_prompt(overall_df)
    return f"""
당신은 개인 투자자의 ISA 계좌 결과를 해석하는 금융 상담가입니다.
사용자 상태:
- 투자 성향: "{user_state.get('성향','미상')}"
- 현재 감정: "{user_state.get('감정','미상')}"

시나리오: "{scenario_name}"

[시나리오 총계]
{overall_text}

[종목별 요약]
{rows_text}

지침:
1) 종목별 손익률을 근거로 한 줄씩 해설.
2) 시나리오 총계를 한 문장으로 요약.
3) '현재 해지(중도)'는 ISA 비과세 한도 적용 대상 아님을 명시.
4) 전체 포트폴리오 한 줄 총평: 사용자의 감정/성향과 연결.
""".strip()