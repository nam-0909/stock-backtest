import streamlit as st
import yfinance as yf
import pandas as pd
import requests
import FinanceDataReader as fdr
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime, timedelta

# 한글 폰트 설정 (깨짐 방지)
plt.rcParams['font.family'] = 'Malgun Gothic'
plt.rcParams['axes.unicode_minus'] = False

# 페이지 기본 설정
st.set_page_config(page_title="주식 & ETF 백테스팅 계산기", layout="wide")
st.title("📈 주식 & ETF 적립식 / 거치식 수익률 계산기")

# ---------------------------------------------------------
# [세션 상태 관리] 금액 조절 버튼용 변수
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
# [1] 국내 전체 개별 주식 & ETF DB 실시간 탑재 (최대 수량)
# ---------------------------------------------------------
@st.cache_data(ttl=86400)
def load_krx_all_stocks():
    equity_stocks = {}
    etf_stocks = {}
    
    # 1. 코스피/코스닥/코넥스 전체 상장 기업 실시간 로드
    try:
        df_krx = fdr.StockListing('KRX')
        for _, row in df_krx.iterrows():
            name = str(row['Name']).strip()
            code = str(row['Code']).zfill(6)
            market = str(row.get('Market', ''))
            suffix = ".KQ" if "KOSDAQ" in market else ".KS"
            
            equity_stocks[f"[국내 주식] {name} ({code})"] = f"{code}{suffix}"
    except Exception as e:
        st.warning(f"국내 주식 목록 로딩 중 알림: {e}")

    # 2. 국내 전체 상장 ETF 실시간 로드
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        url_etf = "https://finance.naver.com/api/sise/etfItemList.nhn"
        res_etf = requests.get(url_etf, headers=headers, timeout=5).json()
        for item in res_etf.get('result', {}).get('etfItemList', []):
            code = item.get('itemcode')
            name = item.get('itemname')
            etf_stocks[f"[국내 ETF] {name} ({code})"] = f"{code}.KS"
    except Exception:
        pass

    return equity_stocks, etf_stocks

EQUITY_DB, ETF_DB = load_krx_all_stocks()

# ---------------------------------------------------------
# [2] 해외(미국/전세계) 개별 주식 & ETF 최대 수량 검색 엔진
# ---------------------------------------------------------
US_POPULAR_MAPPING = {
    # 해외 인기 ETF 한글 키워드 매핑
    "s&p": [("SPY", "SPDR S&P 500 ETF Trust"), ("IVV", "iShares Core S&P 500 ETF"), ("VOO", "Vanguard S&P 500 ETF"), ("SPLG", "SPDR Portfolio S&P 500 ETF")],
    "sp500": [("SPY", "SPDR S&P 500 ETF Trust"), ("VOO", "Vanguard S&P 500 ETF"), ("IVV", "iShares Core S&P 500 ETF")],
    "나스닥": [("QQQ", "Invesco QQQ Trust"), ("QQQM", "Invesco NASDAQ 100 ETF"), ("TQQQ", "ProShares UltraPro QQQ"), ("SQQQ", "ProShares Short QQQ")],
    "nasdaq": [("QQQ", "Invesco QQQ Trust"), ("QQQM", "Invesco NASDAQ 100 ETF")],
    "다우": [("DIA", "SPDR Dow Jones Industrial Average ETF")],
    "배당": [("SCHD", "Schwab U.S. Dividend Equity ETF"), ("VYM", "Vanguard High Dividend Yield ETF"), ("DGRO", "iShares Core Dividend Growth ETF")],
    "반도체": [("SOXX", "iShares Semiconductor ETF"), ("SOXL", "Direxion Daily Semiconductor Bull 3X"), ("SMH", "VanEck Semiconductor ETF")],
    
    # 주요 해외 개별 주식 한글 매핑
    "애플": [("AAPL", "Apple Inc.")],
    "테슬라": [("TSLA", "Tesla Inc.")],
    "엔비디아": [("NVDA", "NVIDIA Corporation")],
    "마이크로소프트": [("MSFT", "Microsoft Corporation")],
    "알파벳": [("GOOGL", "Alphabet Inc. Class A")],
    "구글": [("GOOGL", "Alphabet Inc. Class A")],
    "아마존": [("AMZN", "Amazon.com Inc.")],
    "메타": [("META", "Meta Platforms Inc.")],
}

def search_us_stocks_and_etfs(query, target_type="EQUITY"):
    results = {}
    if not query or len(query.strip()) < 1:
        return results

    q_clean = query.strip().lower()

    # 1) 한글 매핑 우선 추가
    for key, items in US_POPULAR_MAPPING.items():
        if key in q_clean:
            for symbol, desc in items:
                is_etf = any(tag in symbol or tag in desc.upper() for tag in ["ETF", "QQQ", "SPY", "VOO", "IVV", "SCHD", "DIA", "SOXL", "SOXX", "SPLG", "TQQQ", "SMH", "VYM", "DGRO"])
                if (target_type == "ETF" and is_etf) or (target_type == "EQUITY" and not is_etf):
                    label = "[해외 ETF]" if target_type == "ETF" else "[해외 주식]"
                    results[f"{label} {desc} ({symbol})"] = symbol

    # 2) 야후 파이낸스 대용량 실시간 API 검색 (최대 300개 검색 결과 요청)
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
                    results[f"[해외 주식] {shortname} ({symbol})"] = symbol
                elif target_type == "ETF" and quote_type in ["ETF", "MUTUALFUND"]:
                    results[f"[해외 ETF] {shortname} ({symbol})"] = symbol
    except Exception:
        pass
    return results

# ---------------------------------------------------------
# 사이드바 - 검색 모드 및 실시간 자동완성
# ---------------------------------------------------------
st.sidebar.header("🔍 1. 종목 & ETF 검색")

search_category = st.sidebar.radio(
    "검색할 유형을 선택하세요",
    ["🏢 개별 주식 검색 (국내/해외 모든 상장 기업)", "🧺 ETF 전용 검색 (국내/해외 모든 ETF)"]
)

keyword_input = st.sidebar.text_input(
    "단어/글자 일부 입력 (예: 한, 삼, 현대, AAPL, S&P, QQQ)",
    value="한화" if "개별 주식" in search_category else "S&P"
)

clean_kw = keyword_input.strip().lower()
target_ticker = "005930.KS"
selected_name = ""

# 검색 필터링 로직
if "개별 주식" in search_category:
    matched_krx = {name: code for name, code in EQUITY_DB.items() if clean_kw in name.lower()}
    matched_us = search_us_stocks_and_etfs(keyword_input, target_type="EQUITY")
    combined_results = {**matched_krx, **matched_us}

    if combined_results:
        selected_name = st.sidebar.selectbox(
            f"🔍 개별 주식 검색 결과 ({len(combined_results)}개 발견)",
            options=list(combined_results.keys())
        )
        target_ticker = combined_results[selected_name]
        st.sidebar.success(f"선택 종목 티커: **{target_ticker}**")
    else:
        st.sidebar.warning("일치하는 검색 결과가 없습니다. 아래에 티커를 직접 입력하세요.")
        target_ticker = st.sidebar.text_input("티커 직접 입력 (예: 005930.KS, AAPL)", value="005930.KS")

else:
    matched_krx = {name: code for name, code in ETF_DB.items() if clean_kw in name.lower()}
    matched_us = search_us_stocks_and_etfs(keyword_input, target_type="ETF")
    combined_results = {**matched_krx, **matched_us}

    if combined_results:
        selected_name = st.sidebar.selectbox(
            f"🔍 ETF 검색 결과 ({len(combined_results)}개 발견)",
            options=list(combined_results.keys())
        )
        target_ticker = combined_results[selected_name]
        st.sidebar.success(f"선택 ETF 티커: **{target_ticker}**")
    else:
        st.sidebar.warning("일치하는 검색 결과가 없습니다. 아래에 티커를 직접 입력하세요.")
        target_ticker = st.sidebar.text_input("티커 직접 입력 (예: 069500.KS, SPY)", value="069500.KS")

st.sidebar.markdown("---")

# ---------------------------------------------------------
# 사이드바 - 투자 조건 설정 (증감 버튼 유지)
# ---------------------------------------------------------
st.sidebar.header("⚙️ 2. 투자 조건 설정")

investment_plan = st.sidebar.radio(
    "투자 방식",
    ["1안: 적립식 투자 (매월 일정액 매수)", "2안: 거치식 투자 (목돈 한 번에 투자)"]
)

years = st.sidebar.number_input("투자 기간 (년)", min_value=1, max_value=30, value=3, step=1)

if "1안" in investment_plan:
    st.sidebar.subheader("매월 투자 금액 (만원)")
    st.sidebar.number_input("금액 직접 입력 (만원)", min_value=1, key="monthly_amount", label_visibility="collapsed")
    
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
    st.sidebar.number_input("금액 직접 입력 (만원)", min_value=10, key="lump_amount", label_visibility="collapsed")
    
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
# 메인 화면 - 백테스팅 및 대형 고정 그래프 출력
# ---------------------------------------------------------
if run_button:
    try:
        end_dt = datetime.today()
        start_dt = end_dt - timedelta(days=365 * years)
        
        start_str = start_dt.strftime('%Y-%m-%d')
        end_str = end_dt.strftime('%Y-%m-%d')

        st.info(f"⏳ **{selected_name or target_ticker}** 종목의 최근 **{years}년** 데이터를 분석 중입니다...")

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

                # 1. 성과 대시보드
                color_code = "#28a745" if profit_amount >= 0 else "#dc3545"
                st.markdown(
                    f"""
                    <div style="background-color: #f8f9fa; border-radius: 12px; padding: 25px; border-left: 8px solid {color_code}; margin-bottom: 25px;">
                        <div style="display: flex; justify-content: space-around; text-align: center;">
                            <div>
                                <h4 style="color: #6c757d; margin-bottom: 5px;">총 투자 원금</h4>
                                <h2 style="color: #212529; font-size: 30px;">{total_invested/10000:,.0f} 만원</h2>
                            </div>
                            <div>
                                <h4 style="color: #6c757d; margin-bottom: 5px;">최종 평가 금액</h4>
                                <h2 style="color: #212529; font-size: 30px;">{final_value/10000:,.0f} 만원</h2>
                            </div>
                            <div>
                                <h4 style="color: #6c757d; margin-bottom: 5px;">총 수익금</h4>
                                <h2 style="color: {color_code}; font-size: 36px; font-weight: bold;">{profit_amount/10000:+,.0f} 만원</h2>
                            </div>
                            <div>
                                <h4 style="color: #6c757d; margin-bottom: 5px;">최종 수익률</h4>
                                <h2 style="color: {color_code}; font-size: 36px; font-weight: bold;">{return_rate:+.2f}%</h2>
                            </div>
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True
                )

                # 2. 대형 고정 이미지 그래프
                st.subheader("📈 자산 성장 추이 (고정 이미지 그래프)")
                
                fig, ax = plt.subplots(figsize=(14, 6.5))
                
                inv_man = [v / 10000 for v in invested_history]
                val_man = [v / 10000 for v in value_history]

                ax.plot(dates, inv_man, label="투자 원금 (만원)", color="#1f77b4", linewidth=3)
                ax.plot(dates, val_man, label="평가 금액 (만원)", color="#ff7f0e", linewidth=3)

                ax.set_ylabel("금액 (만원)", fontsize=15, fontweight='bold')
                ax.grid(True, linestyle="--", alpha=0.5)
                ax.legend(loc="upper left", fontsize=14)

                ax.tick_params(axis='x', labelsize=13)
                ax.tick_params(axis='y', labelsize=13)

                ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
                plt.xticks(rotation=0)
                plt.tight_layout()

                st.pyplot(fig)

    except Exception as e:
        st.error(f"계산 중 오류가 발생했습니다: {e}")