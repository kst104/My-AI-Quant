import os, json, requests, pandas as pd, yfinance as yf
from openai import OpenAI
from google import genai
from datetime import datetime

# [API KEYS 통합] - 절대 빼먹지 않음
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")
OPENAI_KEY = os.environ.get("OPENAI_API_KEY")
KIMI_KEY = os.environ.get("KIMI_API_KEY")
NEWS_KEY = os.environ.get("NEWS_API_KEY")

client_gemini = genai.Client(api_key=GEMINI_KEY)
client_gpt = OpenAI(api_key=OPENAI_KEY)
client_kimi = OpenAI(api_key=KIMI_KEY, base_url="https://api.moonshot.cn/v1")

def run_full_diagnosis():
    """5년 데이터 기반 5대 지표 연산 및 뉴스 수집"""
    # 1. News API로 실시간 시장 맥락 파악
    n_url = f"https://newsapi.org/v2/top-headlines?category=business&language=en&apiKey={NEWS_KEY}"
    news_res = requests.get(n_url).json().get('articles', [])[:5]
    market_news = "\n".join([f"- {a['title']}" for a in news_res])

    # 2. S&P 500 전수 조사 (대형주 제외)
    r = requests.get("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies", timeout=30)
    tickers = pd.read_html(r.text)[0]["Symbol"].replace(".", "-", regex=True).tolist()
    targets = [t for t in tickers if t not in ["AAPL", "MSFT", "NVDA"]]
    
    raw = yf.download(targets, period="5y", group_by="ticker", progress=False, threads=True)
    mkt = yf.download("^GSPC", period="5y", progress=False)['Close']

    pool = []
    for t in targets:
        try:
            df = raw[t].dropna()
            if len(df) < 500: continue
            c, v, h, l = df['Close'], df['Volume'], df['High'], df['Low']
            
            # 지표 1: $Z\text{-score}$ (역사적 희소성)
            diff = c.diff()
            g, ls = diff.where(lambda x: x>0, 0).rolling(14).mean(), -diff.where(lambda x: x<0, 0).rolling(14).mean().replace(0, 1)
            rsi = 100 - (100 / (1 + (g / ls)))
            z = (rsi.iloc[-1] - rsi.mean()) / rsi.std()
            
            # 지표 2: $TDI$ (수급 밀도)
            tdi_pl, tdi_mbl = rsi.rolling(2).mean().iloc[-1], rsi.rolling(34).mean().iloc[-1]
            
            # 지표 3: $VWAP$ (중심가 괴리)
            vwap = (v * (h + l + c) / 3).cumsum() / v.cumsum()
            v_dist = (c.iloc[-1] / vwap.iloc[-1] - 1) * 100
            
            # 지표 4: $ATR$ (변동성 응축)
            tr = pd.concat([h-l, abs(h-c.shift()), abs(l-c.shift())], axis=1).max(axis=1)
            atr_r = tr.rolling(14).mean().iloc[-1] / tr.rolling(14).mean().mean()
            
            # 지표 5: $\beta$ (시장 민감도)
            ret, m_ret = c.pct_change().dropna(), mkt.pct_change().dropna()
            common = ret.index.intersection(m_ret.index)
            beta = ret.loc[common].cov(m_ret.loc[common]) / m_ret.loc[common].var()

            if abs(z) > 2.3:
                pool.append({"ticker": t, "z": round(z, 2), "tdi_gap": round(tdi_pl - tdi_mbl, 2), 
                             "beta": round(beta, 2), "vwap_dist": round(v_dist, 2), "atr_r": round(atr_r, 2)})
        except: continue
    return pool[:3], market_news

def get_adversarial_debate(stats, news):
    """에이전트 역할 고정 및 적대적 토론 (지능 복원)"""
    rule = "반드시 [REPORT_START]와 [REPORT_END] 태그를 써라. 지표 인과관계를 최소 500자 이상 상세히 써라. 서로를 무자비하게 비판하라."
    
    # A: 냉철한 퀀트 (Gemini)
    res_a = client_gemini.models.generate_content(model="gemini-1.5-pro", 
        contents=f"{rule}\n데이터: {json.dumps(stats)}\n뉴스: {news}").text
    
    # B: 공격적 전략가 (GPT-4o) - A의 데이터 만능주의 공격
    res_b = client_gpt.chat.completions.create(model="gpt-4o", 
        messages=[{"role": "user", "content": f"{rule}\nA의 분석을 비판하고 전략을 짜라: {res_a}"}]).choices[0].message.content
    
    # C: 허무주의 비평가 (Kimi) - 둘 다 조롱하며 과거 실패 사례 소환
    res_c = client_kimi.chat.completions.create(model="moonshot-v1-8k", 
        messages=[{"role": "user", "content": f"{rule}\n위의 헛소리들을 비웃으며 실패 가능성을 논하라: {res_b}"}]).choices[0].message.content
    
    return {"A": res_a, "B": res_b, "C": res_c}