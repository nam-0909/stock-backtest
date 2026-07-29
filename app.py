import streamlit as st
import yfinance as yf
import pandas as pd
import requests
import FinanceDataReader as fdr
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime, timedelta

# 페이지 기본 설정
st.set_page_config(page_title="주식 & ETF 백테스팅 계산기", layout="wide")

# ---------------------------------------------------------
# [스타일 추가] 아이폰 13 미니 전용 모바일 텍스트 짤림/줄바꿈 방지 & UI 최적화
# ---------------------------------------------------------
st.markdown(
    """
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Nanum+Gothic:wght@400;700;800&display=swap" rel="stylesheet">

    <style>
        /* 기본 폰트 적용 */
        html, body, [class*="css"], .stMarkdown {
            font-family: 'Nanum Gothic', sans-serif;
            -webkit-font-smoothing: antialiased;
        }

        /* [핵심 1] 드롭다운(Selectbox) 내부 글씨 줄바꿈 방지 및 말줄임표 처리 */
        div[data-baseweb="select"] * {
            white-space: nowrap !important;
            text-overflow: ellipsis !important;
            overflow: hidden !important;
        }

        /* [핵심 2] 드롭다운 클릭 시 메뉴 항목 한 줄 고정 */
        ul[role="listbox"] li {
            white-space: nowrap !important;
            text-overflow: ellipsis !important;
            overflow: hidden !important;
            font-size: 13px !important;
        }

        /* [핵심 3] 모든 텍스트 영역 LTR(왼쪽->오른쪽) 고정 */
        div[data-testid="stMarkdownContainer"], .stRadio, .stTextInput, .stNumberInput, .stSelectbox {
            direction: ltr !important;
        }

        /* 메인 로고 스타일 정의 */
        .logo-container {
            display: flex;
            align-items: center;
            justify-content: flex-start;
            flex-wrap: wrap;
            gap: 8px;
            margin-bottom: 20px;
            direction: ltr;
        }

        .logo-text {
            color: white;
            background-color: transparent;
            font-family: 'Nanum Gothic', sans-serif;
            font-weight: 800;
            letter-spacing: -1.2px;
            -webkit-text-stroke: 1.2px black;
            text-shadow: 0 0 2px black;
            line-height: 1.1;
            direction: ltr;
        }

        /* 모바일 반응형 크기 최적화 */
        @media (max-width: 768px) {
            .logo-text-large {
                font-size: 26px !important;
            }
            .logo-text-small {
                font-size: 14px !important;
            }
            .logo-chart {
                width: 26px !important;
                height: 26px !important;
            }
        }

        /* PC 크기 설정 */
        @media (min-width: 769px) {
            .logo-text-large {
                font-size: 44px !important;
            }
            .logo-text-small {
                font-size: 20px !important;
            }
            .logo-chart {
                width: 44px !important;
                height: 44px !important;
            }
        }
    </style>
    """,
    unsafe_allow_html=True
)

# ---------------------------------------------------------
# [UI 적용] 로고 레이아웃
# ---------------------------------------------------------
logo_html = """
<div class="logo-container">
    <span class="logo-text logo-text-large">주식 ETF &nbsp;&amp; &nbsp;지수</span>
    <svg class="logo-chart" viewBox="0 0 100 100" style="filter: drop-shadow(0 0 2px black);">
        <rect width="100" height="100" rx="10" fill="white"/>
        <path d="M15 85 L35 45 L65 65 L85 15" stroke="red" stroke-width="8" fill="none" stroke-linecap="round"/>
    </svg>
    <div style="flex-basis: 100%; height: 0;"></div>
    <span class="logo-text logo-text-large">수익률 / 배당금</span>
    <div style="flex-basis: 100%; height: 0;"></div>
    <span class="logo-text logo-text-small">[백테스팅 앱]</span>
</div>
"""
st.markdown(logo_html, unsafe_allow_html=True)

# ---------------------------------------------------------
# [세션 상태 관리]
# ---------------------------------------------------------
if "monthly_amount" not in st.session_state:
    st.session_state.monthly_amount = 50

if "lump_amount" not in st.session_state:
    st.session_state.lump_amount = 1000

def adjust_monthly(delta):
    st.session_state.monthly_amount = max(1, st.session_state.monthly_amount + delta)

def adjust_lump(delta):
    st.session_state.lump_amount = max(10, st.session_state.lump_amount + delta)

# ---------------------------------------------------------
# [데이터베이스] 국내 전체 종목 & ETF DB
# ---------------------------------------------------------
@st.cache_data(ttl=86400)
def load_all_market_data():
    equity_stocks = {}
    etf_stocks = {}
    headers = {'User-Agent': 'Mozilla/5.0'}

    # 1. 국내 ETF
    try:
        url_etf = "https://finance.naver.com/api/sise/etfItemList.nhn"
        res_etf = requests.get(url_etf, headers=headers, timeout=5).json()
        for item in res_etf.get('result', {}).get('etfItemList', []):
            code = item.get('itemcode')
            name = item.get('itemname')
            etf_stocks[f"[국내] {name} ({code})"] = f"{code}.KS"
    except Exception:
        pass

    # 2. 국내 주식
    try:
        df_krx = fdr.StockListing('KRX')
        for _, row in df_krx.iterrows():
            name = str(row['Name']).strip()
            code = str(row['Code']).zfill(6)
            equity_stocks[f"[국내] {name} ({code})"] = f"{code}.KS"
    except Exception:
        pass

    return equity_stocks, etf_stocks

EQUITY_DB, ETF_DB = load_all_market_data()

# ---------------------------------------------------------
# [검색 엔진] 해외 통합 검색 Engine
# ---------------------------------------------------------
US_POPULAR_MAPPING = {
    "s&p": [("SPY", "SPDR S&P 500"), ("IVV", "iShares Core S&P 500"), ("VOO", "Vanguard S&P 500"), ("SPLG", "SPDR Portfolio S&P 500")],
    "sp500": [("SPY", "SPDR S&P 500"), ("VOO", "Vanguard S&P 500"), ("IVV", "iShares Core S&P 500")],
    "나스닥": [("QQQ", "Invesco QQQ"), ("QQQM", "Invesco NASDAQ 100"), ("TQQQ", "ProShares UltraPro QQQ"), ("SQQQ", "ProShares Short QQQ")],
    "nasdaq": [("QQQ", "Invesco QQQ"), ("QQQM", "Invesco NASDAQ 100")],
    "다우": [("DIA", "SPDR Dow Jones")],
    "배당": [("SCHD", "Schwab U.S. Dividend"), ("VYM", "Vanguard High Dividend")],
    "반도체": [("SOXX", "iShares Semiconductor"), ("SOXL", "Direxion Daily Semi 3X"), ("SMH", "VanEck Semiconductor")],
    "애플": [("AAPL", "Apple Inc.")],
    "테슬라": [("TSLA", "Tesla Inc.")],
    "엔비디아": [("NVDA", "NVIDIA Corp.")],
    "마이크로소프트": [("MSFT", "Microsoft Corp.")],
    "알파벳": [("GOOGL", "Alphabet Inc.")],
    "구글": [("GOOGL", "Alphabet Inc.")],
    "아마존": [("AMZN", "Amazon.com Inc.")],
    "메타": [("META", "Meta Platforms")],
}

def search_us_stocks_and_etfs(query, target_type="EQUITY"):
    results = {}
    if not query or len(query.strip()) < 1:
        return results

    q_clean = query.strip().lower()

    for key, items in US_POPULAR_MAPPING.items():
        if key in q_clean:
            for symbol, desc in items:
                is_etf = any(tag in symbol or tag in desc.upper() for tag in ["ETF", "QQQ", "SPY", "VOO", "IVV", "SCHD", "DIA", "SOXL", "SOXX", "SPLG", "TQQQ", "SMH"])
                if (target_type == "ETF" and is_etf) or (target_type == "EQUITY" and not is_etf):
                    results[f"[해외] {desc} ({symbol})"] = symbol

    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        url = f"https://query2.finance.yahoo.com/v1/finance/search?q={query}&quotesCount=300&newsCount=0"
        res = requests.get(url, headers=headers, timeout=4).json()
        
        if 'quotes' in res:
            for item in res['quotes']:
                symbol = item.get('symbol', '')
                shortname = item.get('shortname') or item.get('longname') or symbol
                quote_type = item.get('quoteType', '')
                
                if target_type == "EQUITY" and quote_type in ["EQUITY"]:
                    results[f"[해외] {shortname} ({symbol})"] = symbol
                elif target_type == "ETF" and quote_type in ["ETF", "MUTUALFUND"]:
                    results[f"[해외] {shortname} ({symbol})"] = symbol
    except Exception:
        pass
    return results

# ---------------------------------------------------------
# 사이드바 설정
# ---------------------------------------------------------
st.sidebar.header("🔍 1. 종목 & ETF 검색")

search_category = st.sidebar.radio(
    "검색할 유형을 선택하세요",
    ["🏢 개별 주식 검색", "🧺 ETF 전용 검색"]
)

keyword_input = st.sidebar.text_input(
    "단어/글자 일부 입력 (예: 한, 삼, AAPL, S&P, QQQ)",
    value="한화" if "개별 주식" in search_category else "S&P"
)

clean_kw = keyword_input.strip().lower()
target_ticker = "005930.KS"
selected_name = ""

if "개별 주식" in search_category:
    matched_krx = {name: code for name, code in EQUITY_DB.items() if clean_kw in name.lower()}
    matched_us = search_us_stocks_and_etfs(keyword_input, target_type="EQUITY")
    combined_results = {**matched_krx, **matched_us}

    if combined_results:
        selected_name = st.sidebar.selectbox(
            f"🔍 검색 결과 ({len(combined_results)}개)",
            options=list(combined_results.keys())
        )
        target_ticker = combined_results[selected_name]
        st.sidebar.success(f"선택 티커: **{target_ticker}**")
    else:
        st.sidebar.warning("결과 없음. 티커를 직접 입력하세요.")
        target_ticker = st.sidebar.text_input("티커 직접 입력", value="005930.KS")

else:
    matched_krx = {name: code for name, code in ETF_DB.items() if clean_kw in name.lower()}
    matched_us = search_us_stocks_and_etfs(keyword_input, target_type="ETF")
    combined_results = {**matched_krx, **matched_us}

    if combined_results:
        selected_name = st.sidebar.selectbox(
            f"🔍 검색 결과 ({len(combined_results)}개)",
            options=list(combined_results.keys())
        )
        target_ticker = combined_results[selected_name]
        st.sidebar.success(f"선택 티커: **{target_ticker}**")
    else:
        st.sidebar.warning("결과 없음. 티커를 직접 입력하세요.")
        target_ticker = st.sidebar.text_input("티커 직접 입력", value="069500.KS")

st.sidebar.markdown("---")

st.sidebar.header("⚙️ 2. 투자 조건 설정")

investment_plan = st.sidebar.radio(
    "투자 방식",
    ["1안: 적립식 (매월 매수)", "2안: 거치식 (목돈 투자)"]
)

years = st.sidebar.number_input("투자 기간 (년)", min_value=1, max_value=30, value=3, step=1)

if "1안" in investment_plan:
    st.sidebar.subheader("매월 투자 금액 (만원)")
    st.sidebar.number_input("금액 입력 (만원)", min_value=1, key="monthly_amount", label_visibility="collapsed")
    
    col_p1, col_p5, col_p10, col_p50 = st.sidebar.columns(4)
    col_p1.button("+1만", on_click=adjust_monthly, args=(1,), use_container_width=True)
    col_p5.button("+5만", on_click=adjust_monthly, args=(5,), use_container_width=True)
    col_p10.button("+10만", on_click=adjust_monthly, args=(10,), use_container_width=True)
    col_p50.button("+50만", on_click=adjust_monthly, args=(50,), use_container_width=True)

    col_m1, col_m5, col_m10, col_m50 = st.sidebar.columns(4)
    col_m1.button("-1만", on_click=adjust_monthly, args=(-1,), use_container_width=True)
    col_m5.button("-5만", on_click=adjust_monthly, args=(-5,), use_container_width=True)
    col_m10.button("-10만", on_click=adjust_monthly, args=(-10,), use_container_width=True)
    col_m50.button("-50만", on_click=adjust_monthly, args=(-50,), use_container_width=True)

    monthly_amount_ten_thousand = st.session_state.monthly_amount
    lump_sum_ten_thousand = 0

else:
    st.sidebar.subheader("거치 투자 금액 (만원)")
    st.sidebar.number_input("금액 입력 (만원)", min_value=10, key="lump_amount", label_visibility="collapsed")
    
    col_p1, col_p5, col_p10, col_p50 = st.sidebar.columns(4)
    col_p1.button("+10만", on_click=adjust_lump, args=(10,), use_container_width=True)
    col_p5.button("+50만", on_click=adjust_lump, args=(50,), use_container_width=True)
    col_p10.button("+100만", on_click=adjust_lump, args=(100,), use_container_width=True)
    col_p50.button("+500만", on_click=adjust_lump, args=(500,), use_container_width=True)

    col_m1, col_m5, col_m10, col_m50 = st.sidebar.columns(4)
    col_m1.button("-10만", on_click=adjust_lump, args=(-10,), use_container_width=True)
    col_m5.button("-50만", on_click=adjust_lump, args=(-50,), use_container_width=True)
    col_m10.button("-100만", on_click=adjust_lump, args=(-100,), use_container_width=True)
    col_m50.button("-500만", on_click=adjust_lump, args=(-500,), use_container_width=True)

    lump_sum_ten_thousand = st.session_state.lump_amount
    monthly_amount_ten_thousand = 0

st.sidebar.markdown("---")
run_button = st.sidebar.button("🚀 수익률 계산하기", use_container_width=True)

# ---------------------------------------------------------
# 메인 분석 결과 출력
# ---------------------------------------------------------
if run_button:
    try:
        end_dt = datetime.today()
        start_dt = end_dt - timedelta(days=365 * years)
        start_str = start_dt.strftime('%Y-%m-%d')
        end_str = end_dt.strftime('%Y-%m-%d')

        st.info(f"⏳ **{selected_name or target_ticker}** 최근 **{years}년** 분석 중...")

        df = yf.download(target_ticker, start=start_str, end=end_str)

        if df.empty and target_ticker.endswith(".KS"):
            alt_ticker = target_ticker.replace(".KS", ".KQ")
            df = yf.download(alt_ticker, start=start_str, end=end_str)

        if df.empty:
            st.error("❌ 주가 데이터를 가져올 수 없습니다. 종목 코드를 확인해 주세요.")
        else:
            if 'Adj Close' in df.columns:
                price_series = df['Adj Close']
            else:
                price_series = df['Close']

            if isinstance(price_series, pd.DataFrame):
                price_series = price_series.iloc[:, 0]

            price_series = price_series.dropna()

            if price_series.empty:
                st.error("❌ 해당 기간의 주가 데이터가 존재하지 않습니다.")
            else:
                end_price = float(price_series.iloc[-1])
                dates = price_series.index

                # 화폐 단위 설정 (국내: 원 / 해외: 달러)
                if target_ticker.endswith(".KS") or target_ticker.endswith(".KQ"):
                    price_str = f"{end_price:,.0f} 원"
                else:
                    price_str = f"${end_price:,.2f}"

                invested_history = []
                value_history = []

                if "1안" in investment_plan:
                    monthly_krw = monthly_amount_ten_thousand * 10000
                    monthly_data = price_series.resample('MS').first().dropna()

                    current_shares = 0.0
                    cum_invested = 0.0

                    for date, price in price_series.items():
                        if date in monthly_data.index:
                            current_shares += monthly_krw / float(price)
                            cum_invested += monthly_krw
                        
                        invested_history.append(cum_invested)
                        value_history.append(current_shares * float(price))

                    total_invested = cum_invested
                    final_value = current_shares * end_price

                else:
                    lump_krw = lump_sum_ten_thousand * 10000
                    start_price = float(price_series.iloc[0])
                    shares = lump_krw / start_price

                    for price in price_series:
                        invested_history.append(lump_krw)
                        value_history.append(shares * float(price))

                    total_invested = lump_krw
                    final_value = shares * end_price

                profit_amount = final_value - total_invested
                return_rate = (profit_amount / total_invested) * 100 if total_invested > 0 else 0

                # 1. 성과 대시보드 (현재 1주당 가격 카드 포함 5개 카드 구성)
                color_code = "#28a745" if profit_amount >= 0 else "#dc3545"
                st.markdown(
                    f"""
                    <div style="direction: ltr; background-color: #f8f9fa; border-radius: 12px; padding: 20px; border-left: 6px solid {color_code}; margin-bottom: 20px;">
                        <div style="display: flex; flex-wrap: wrap; justify-content: space-around; text-align: center; gap: 12px;">
                            <div style="flex: 1 1 110px;">
                                <h5 style="color: #6c757d; margin-bottom: 3px; font-size: 0.85rem;">현재 1주당 가격</h5>
                                <h3 style="color: #0d6efd; font-size: 1.25rem; font-weight: 700;">{price_str}</h3>
                            </div>
                            <div style="flex: 1 1 110px;">
                                <h5 style="color: #6c757d; margin-bottom: 3px; font-size: 0.85rem;">총 투자 원금</h5>
                                <h3 style="color: #212529; font-size: 1.25rem; font-weight: 700;">{total_invested/10000:,.0f} 만원</h3>
                            </div>
                            <div style="flex: 1 1 110px;">
                                <h5 style="color: #6c757d; margin-bottom: 3px; font-size: 0.85rem;">최종 평가 금액</h5>
                                <h3 style="color: #212529; font-size: 1.25rem; font-weight: 700;">{final_value/10000:,.0f} 만원</h3>
                            </div>
                            <div style="flex: 1 1 110px;">
                                <h5 style="color: #6c757d; margin-bottom: 3px; font-size: 0.85rem;">총 수익금</h5>
                                <h3 style="color: {color_code}; font-size: 1.35rem; font-weight: 800;">{profit_amount/10000:+,.0f} 만원</h3>
                            </div>
                            <div style="flex: 1 1 110px;">
                                <h5 style="color: #6c757d; margin-bottom: 3px; font-size: 0.85rem;">최종 수익률</h5>
                                <h3 style="color: {color_code}; font-size: 1.35rem; font-weight: 800;">{return_rate:+.2f}%</h3>
                            </div>
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True
                )

                # 2. 대형 고정 이미지 그래프
                st.subheader("📈 자산 성장 추이")
                
                fig, ax = plt.subplots(figsize=(12, 6))
                
                inv_man = [v / 10000 for v in invested_history]
                val_man = [v / 10000 for v in value_history]

                ax.plot(dates, inv_man, label="투자 원금 (만원)", color="#1f77b4", linewidth=3)
                ax.plot(dates, val_man, label="평가 금액 (만원)", color="#ff7f0e", linewidth=3)

                ax.set_ylabel("금액 (만원)", fontsize=14, fontweight='bold', labelpad=10)
                ax.grid(True, linestyle="--", alpha=0.5)
                ax.legend(loc="upper left", fontsize=13)

                ax.tick_params(axis='x', labelsize=12)
                ax.tick_params(axis='y', labelsize=12)

                ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
                plt.xticks(rotation=0)
                plt.tight_layout()

                st.pyplot(fig, use_container_width=True)

    except Exception as e:
        st.error(f"계산 중 오류가 발생했습니다: {e}")
