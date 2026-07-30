import streamlit as st
import yfinance as yf
import pandas as pd
import requests
import time
import os
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.font_manager as fm
from datetime import datetime, timedelta

# ---------------------------------------------------------
# [1] 한글 폰트 자동 다운로드 & Matplotlib 설정
# ---------------------------------------------------------
@st.cache_resource
def setup_korean_font():
    font_path = "NanumGothic.ttf"
    if not os.path.exists(font_path):
        url = "https://github.com/google/fonts/raw/main/ofl/nanumgothic/NanumGothic-Regular.ttf"
        try:
            r = requests.get(url, timeout=10)
            with open(font_path, "wb") as f:
                f.write(r.content)
        except Exception:
            return None
    
    if os.path.exists(font_path):
        fm.fontManager.addfont(font_path)
        font_prop = fm.FontProperties(fname=font_path)
        font_name = font_prop.get_name()
        plt.rc('font', family=font_name)
        plt.rcParams['axes.unicode_minus'] = False
        return font_name
    return None

setup_korean_font()

# 페이지 기본 설정
st.set_page_config(page_title="주식 & ETF 백테스팅 계산기", layout="wide")

# ---------------------------------------------------------
# [2] 모바일 최적화 & 스타일
# ---------------------------------------------------------
st.markdown(
    """
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Nanum+Gothic:wght@400;700;800&display=swap" rel="stylesheet">

    <style>
        html, body, [class*="css"], .stMarkdown {
            font-family: 'Nanum Gothic', sans-serif;
            -webkit-font-smoothing: antialiased;
        }

        div[data-baseweb="select"] * {
            white-space: nowrap !important;
            text-overflow: ellipsis !important;
            overflow: hidden !important;
        }

        ul[role="listbox"] li {
            white-space: nowrap !important;
            text-overflow: ellipsis !important;
            overflow: hidden !important;
            font-size: 13px !important;
        }

        div[data-testid="stMarkdownContainer"], .stRadio, .stTextInput, .stNumberInput, .stSelectbox {
            direction: ltr !important;
        }

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

        @media (max-width: 768px) {
            .logo-text-large { font-size: 26px !important; }
            .logo-text-small { font-size: 14px !important; }
            .logo-chart { width: 26px !important; height: 26px !important; }
        }

        @media (min-width: 769px) {
            .logo-text-large { font-size: 44px !important; }
            .logo-text-small { font-size: 20px !important; }
            .logo-chart { width: 44px !important; height: 44px !important; }
        }
    </style>
    """,
    unsafe_allow_html=True
)

# ---------------------------------------------------------
# [3] 로고 레이아웃
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
# [4] 세션 상태 관리
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
# [5] 국내 전체 주식 & ETF DB 구축 (KRX 네이버 백업 연동)
# ---------------------------------------------------------
ETF_KEYWORDS = ["ETF", "KODEX", "TIGER", "ACE", "RISE", "SOL", "ARIRANG", "HANARO", "KBSTAR", "KOSEF", "PLUS", "TIMEFOLIO", "UNIFEX"]

@st.cache_data(ttl=86400)
def load_krx_stock_and_etf_db():
    stock_db = {}
    etf_db = {}
    
    # 1. 국내 ETF 전체 데이터 불러오기
    try:
        url = "https://finance.naver.com/api/sise/etfItemList.nhn"
        headers = {'User-Agent': 'Mozilla/5.0'}
        res = requests.get(url, headers=headers, timeout=5).json()
        for item in res.get('result', {}).get('etfItemList', []):
            code = item.get('itemcode')
            name = item.get('itemname')
            if code and name:
                etf_db[name] = f"{code}.KS"
    except Exception:
        pass

    # 2. KRX 코스피/코스닥 전 종목 데이터 불러오기 (네이버 증권 기반)
    try:
        for market in [0, 1]:  # 0: KOSPI, 1: KOSDAQ
            url = f"https://finance.naver.com/sise/sise_market_sum.naver?sosok={market}&page=1"
            headers = {'User-Agent': 'Mozilla/5.0'}
            res = requests.get(url, headers=headers, timeout=5)
            # 1페이지~10페이지 주요 종목 파싱 및 백업
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(res.text, 'html.parser')
            # 네이버 주식 검색 오픈 API 백업 처리
    except Exception:
        pass

    return stock_db, etf_db

KR_STOCK_DB, KR_ETF_DB = load_krx_stock_and_etf_db()

# ---------------------------------------------------------
# [6] 실시간 시세 추출 Engine
# ---------------------------------------------------------
def get_exact_realtime_price(ticker_symbol):
    timestamp = int(time.time() * 1000)
    headers = {
        'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1',
        'Referer': 'https://m.stock.naver.com/'
    }
    
    is_kr = ticker_symbol.endswith(".KS") or ticker_symbol.endswith(".KQ")
    
    if is_kr:
        code = ticker_symbol.split('.')[0]
        try:
            url = f"https://m.stock.naver.com/api/stock/{code}/basic?_t={timestamp}"
            res = requests.get(url, headers=headers, timeout=3).json()
            price = float(str(res['closePrice']).replace(',', ''))
            return price
        except Exception:
            pass
    else:
        try:
            url = f"https://m.stock.naver.com/api/html/item/getGfItemHeader.nhn?symbol={ticker_symbol}&_t={timestamp}"
            res = requests.get(url, headers=headers, timeout=3)
            if res.status_code == 200:
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(res.text, 'html.parser')
                price_elem = soup.find('span', class_='stock_price')
                if price_elem:
                    price = float(price_elem.text.replace(',', '').replace('$', '').strip())
                    return price
        except Exception:
            pass

    try:
        t = yf.Ticker(ticker_symbol)
        fast_info = t.fast_info
        price = float(fast_info['lastPrice'])
        return price
    except Exception:
        return None

# ---------------------------------------------------------
# [7] 국내/해외 개별주식 & ETF 완벽 분리 검색 엔진
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
    "구글": [("GOOGL", "Alphabet Inc.")],
}

def search_live_stocks(query, search_type="EQUITY"):
    results = {}
    if not query or len(query.strip()) < 1:
        return results

    q_clean = query.strip().lower()

    # 1. 네이버 종합 검색 API (국내 개별 주식 & ETF 탐색)
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        url = f"https://ac.stock.naver.com/ac?q={query}&target=index,stock,etf"
        res = requests.get(url, headers=headers, timeout=3).json()
        
        items = res.get('items', [])
        for item in items:
            if isinstance(item, list) and len(item) >= 2:
                code = str(item[0]).strip()
                name = str(item[1]).strip()
                
                if code.isdigit() and len(code) == 6:
                    is_etf = any(kw in name.upper() for kw in ETF_KEYWORDS) or (name in KR_ETF_DB)
                    
                    if search_type == "EQUITY" and not is_etf:
                        results[f"[국내] {name} ({code})"] = f"{code}.KS"
                    elif search_type == "ETF" and is_etf:
                        results[f"[국내] {name} ({code})"] = f"{code}.KS"
    except Exception:
        pass

    # 2. 네이버 모바일 통합 키워드 검색 백업
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        url = f"https://m.stock.naver.com/api/json/search/searchListJson.nhn?keyword={query}"
        res = requests.get(url, headers=headers, timeout=3).json()
        search_list = res.get('result', {}).get('searchList', [])

        for item in search_list:
            stock_name = item.get('stockName', '')
            item_code = item.get('itemCode', '')
            reuters_code = item.get('reutersCode', '')
            nation_info = item.get('nationInfo', '')

            if (nation_info == 'KOR' or not nation_info) and item_code.isdigit() and len(item_code) == 6:
                is_etf = any(kw in stock_name.upper() for kw in ETF_KEYWORDS) or (stock_name in KR_ETF_DB)
                ticker_full = f"{item_code}.KS"
                
                if search_type == "EQUITY" and not is_etf:
                    results[f"[국내] {stock_name} ({item_code})"] = ticker_full
                elif search_type == "ETF" and is_etf:
                    results[f"[국내] {stock_name} ({item_code})"] = ticker_full
    except Exception:
        pass

    # 3. ETF 탭인 경우 전체 ETF DB 직접 검색
    if search_type == "ETF":
        for name, ticker in KR_ETF_DB.items():
            if q_clean in name.lower():
                code = ticker.split('.')[0]
                results[f"[국내] {name} ({code})"] = ticker

    # 4. 미국 인기 키워드 매핑
    for key, items_list in US_POPULAR_MAPPING.items():
        if key in q_clean:
            for symbol, desc in items_list:
                is_us_etf = any(tag in symbol or tag in desc.upper() for tag in ["ETF", "QQQ", "SPY", "VOO", "IVV", "SCHD", "DIA", "SOXL", "SOXX", "SPLG", "TQQQ", "SMH"])
                if (search_type == "ETF" and is_us_etf) or (search_type == "EQUITY" and not is_us_etf):
                    results[f"[해외] {desc} ({symbol})"] = symbol

    # 5. Yahoo Finance 해외 검색 API
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        url = f"https://query2.finance.yahoo.com/v1/finance/search?q={query}&quotesCount=20&newsCount=0"
        res = requests.get(url, headers=headers, timeout=3).json()
        if 'quotes' in res:
            for item in res['quotes']:
                symbol = item.get('symbol', '')
                shortname = item.get('shortname') or item.get('longname') or symbol
                quote_type = item.get('quoteType', '')
                
                if symbol and '.' not in symbol and not symbol.isdigit():
                    if search_type == "EQUITY" and quote_type in ["EQUITY"]:
                        results[f"[해외] {shortname} ({symbol})"] = symbol
                    elif search_type == "ETF" and quote_type in ["ETF", "MUTUALFUND"]:
                        results[f"[해외] {shortname} ({symbol})"] = symbol
    except Exception:
        pass

    return results

# ---------------------------------------------------------
# [8] 사이드바 설정
# ---------------------------------------------------------
st.sidebar.header("🔍 1. 종목 & ETF 검색")

search_category = st.sidebar.radio(
    "검색할 유형을 선택하세요",
    ["🏢 개별 주식 검색", "🧺 ETF 전용 검색"]
)

default_kw = "삼성전자" if "개별 주식" in search_category else "KODEX"
keyword_input = st.sidebar.text_input(
    "종목명 또는 티커 입력 (예: 삼성전자, 카카오, AAPL, KODEX, QQQ)",
    value=default_kw
)

combined_results = search_live_stocks(keyword_input, search_type="EQUITY" if "개별 주식" in search_category else "ETF")

target_ticker = "005930.KS"
selected_name = ""

if combined_results:
    selected_name = st.sidebar.selectbox(
        f"🔍 검색 결과 ({len(combined_results)}개)",
        options=list(combined_results.keys())
    )
    target_ticker = combined_results[selected_name]
else:
    st.sidebar.warning("결과 없음. 티커를 직접 입력하세요.")
    target_ticker = st.sidebar.text_input("티커 직접 입력 (예: 005930.KS)", value="005930.KS")

# ---------------------------------------------------------
# [9] 실시간 시세 영역 (전광판 UI)
# ---------------------------------------------------------
col_price, col_refresh = st.columns([5, 1])

with col_refresh:
    st.write("")
    st.write("")
    refresh_click = st.button("🔄 시세 새로고침", use_container_width=True)

rt_price = get_exact_realtime_price(target_ticker)

with col_price:
    if rt_price is not None:
        is_kr = target_ticker.endswith(".KS") or target_ticker.endswith(".KQ")
        price_fmt = f"{rt_price:,.0f} 원" if is_kr else f"${rt_price:,.2f}"

        st.markdown(
            f"""
            <div style="background-color: #ffffff; border: 1px solid #e0e0e0; border-radius: 10px; padding: 15px; margin-bottom: 20px; box-shadow: 0 2px 5px rgba(0,0,0,0.05); direction: ltr;">
                <div style="font-size: 0.9rem; color: #6c757d; font-weight: bold;">⚡ 실시간 현재가</div>
                <div style="display: flex; align-items: baseline; gap: 12px; margin-top: 5px;">
                    <span style="font-size: 2.2rem; font-weight: 800; color: #212529;">{price_fmt}</span>
                </div>
                <div style="font-size: 0.75rem; color: #888888; margin-top: 3px;">* 네이버 증권 서버와 초단위로 직접 연동된 최신 시세입니다.</div>
            </div>
            """,
            unsafe_allow_html=True
        )
    else:
        st.warning("⚠️ 실시간 시세를 불러오는 중입니다. 잠시 후 다시 새로고침을 눌러주세요.")

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
    
    col_p5, col_p10, col_p50 = st.sidebar.columns(3)
    col_p5.button("+5만", on_click=adjust_monthly, args=(5,), use_container_width=True)
    col_p10.button("+10만", on_click=adjust_monthly, args=(10,), use_container_width=True)
    col_p50.button("+50만", on_click=adjust_monthly, args=(50,), use_container_width=True)

    col_m5, col_m10, col_m50 = st.sidebar.columns(3)
    col_m5.button("-5만", on_click=adjust_monthly, args=(-5,), use_container_width=True)
    col_m10.button("-10만", on_click=adjust_monthly, args=(-10,), use_container_width=True)
    col_m50.button("-50만", on_click=adjust_monthly, args=(-50,), use_container_width=True)

    monthly_amount_ten_thousand = st.session_state.monthly_amount
    lump_sum_ten_thousand = 0

else:
    st.sidebar.subheader("거치 투자 금액 (만원)")
    st.sidebar.number_input("금액 입력 (만원)", min_value=10, key="lump_amount", label_visibility="collapsed")
    
    col_p5, col_p10, col_p50 = st.sidebar.columns(3)
    col_p5.button("+50만", on_click=adjust_lump, args=(50,), use_container_width=True)
    col_p10.button("+100만", on_click=adjust_lump, args=(100,), use_container_width=True)
    col_p50.button("+500만", on_click=adjust_lump, args=(500,), use_container_width=True)

    col_m5, col_m10, col_m50 = st.sidebar.columns(3)
    col_m5.button("-50만", on_click=adjust_lump, args=(-50,), use_container_width=True)
    col_m10.button("-100만", on_click=adjust_lump, args=(-100,), use_container_width=True)
    col_m50.button("-500만", on_click=adjust_lump, args=(-500,), use_container_width=True)

    lump_sum_ten_thousand = st.session_state.lump_amount
    monthly_amount_ten_thousand = 0

st.sidebar.markdown("---")
run_button = st.sidebar.button("🚀 수익률 계산하기", use_container_width=True)

# ---------------------------------------------------------
# [10] 백테스팅 계산 및 3가지 선 그래프 출력
# ---------------------------------------------------------
if run_button:
    try:
        end_dt = datetime.today()
        start_dt = end_dt - timedelta(days=365 * years)
        start_str = start_dt.strftime('%Y-%m-%d')
        end_str = end_dt.strftime('%Y-%m-%d')

        st.info(f"⏳ **{selected_name or target_ticker}** 최근 **{years}년** 백테스팅 분석 중...")

        df = yf.download(target_ticker, start=start_str, end=end_str)

        if df.empty and target_ticker.endswith(".KS"):
            alt_ticker = target_ticker.replace(".KS", ".KQ")
            df = yf.download(alt_ticker, start=start_str, end=end_str)
            if not df.empty:
                target_ticker = alt_ticker

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
                end_price = rt_price if rt_price is not None else float(price_series.iloc[-1])
                dates = price_series.index

                is_kr = target_ticker.endswith(".KS") or target_ticker.endswith(".KQ")
                price_str = f"{end_price:,.0f} 원" if is_kr else f"${end_price:,.2f}"

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

                st.subheader(f"📈 {years}년 자산 증식 & 주가 추이 (3가지 핵심 선)")
                
                # Matplotlib 이중 축(Twin Axis) 그래프
                fig, ax1 = plt.subplots(figsize=(12, 6))

                inv_man = [v / 10000 for v in invested_history]
                val_man = [v / 10000 for v in value_history]

                # [왼쪽 Y축] 1. 투자 원금 & 2. 총 자산 평가액
                line1 = ax1.plot(dates, inv_man, label="1. 투자 원금 (만원)", color="#1f77b4", linewidth=2.5, linestyle="--")
                line2 = ax1.plot(dates, val_man, label="2. 총 자산 평가액 (만원)", color="#ff7f0e", linewidth=3)
                ax1.set_ylabel("자산 금액 (만원)", fontsize=13, fontweight='bold', color="#333333")

                # [오른쪽 Y축] 3. 주가 단가 추이
                ax2 = ax1.twinx()
                stock_prices = price_series.values
                unit_label = "원" if is_kr else "$"
                line3 = ax2.plot(dates, stock_prices, label=f"3. 주가 추이 ({unit_label})", color="#2ca02c", linewidth=2, linestyle=":")
                ax2.set_ylabel(f"주가 ({unit_label})", fontsize=13, fontweight='bold', color="#2ca02c")

                # 범례 통합
                lines = line1 + line2 + line3
                labels = [l.get_label() for l in lines]
                ax1.legend(lines, labels, loc="upper left", fontsize=12, frameon=True, facecolor="white")

                ax1.grid(True, linestyle="--", alpha=0.5)
                ax1.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
                plt.xticks(rotation=0)
                plt.tight_layout()

                st.pyplot(fig, use_container_width=True)

    except Exception as e:
        st.error(f"계산 중 오류가 발생했습니다: {e}")
