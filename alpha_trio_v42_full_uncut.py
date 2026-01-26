import os
import re
import json
import time
import requests
import traceback
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta
from openai import OpenAI
from pinecone import Pinecone
from google import genai
# [STAGE 1: 하이퍼-인프라 통합 초기화]
# 네가 강조한 모든 API 키와 클라이언트를 단 한 줄의 생략 없이 로드한다.
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")
OPENAI_KEY = os.environ.get("OPENAI_API_KEY")
KIMI_KEY = os.environ.get("KIMI_API_KEY")
NEWS_KEY = os.environ.get("NEWS_API_KEY")
PINECONE_KEY = os.environ.get("PINECONE_API_KEY")
DISCORD_URL = os.environ.get("DISCORD_WEBHOOK_URL")
client_gemini = genai.Client(api_key=GEMINI_KEY)
client_gpt = OpenAI(api_key=OPENAI_KEY)
client_kimi = OpenAI(api_key=KIMI_KEY, base_url="https://api.moonshot.cn/v1")
pc = Pinecone(api_key=PINECONE_KEY)
index = pc.Index("alpha-trio-memory")
# ---------------------------------------------------------
# [STAGE 2: 하이퍼-퀀트 - 5년 시계열 및 뉴스 맥락 연산]
# ---------------------------------------------------------
def run_full_diagnosis():
    """500개 종목의 5년 데이터를 훑으며 VWAP, Beta, TDI, ATR, Z-score 산출 및 뉴스 통합"""
    print("🌌 [Stage 2] S&P 500 전 종목 5개년 역사 및 뉴스 전수 조사 시작...")
    
    # 2.1 News API를 통한 시장 맥락 확보 (복구 완료)
    n_url = f"https://newsapi.org/v2/top-headlines?category=business&language=en&apiKey={NEWS_KEY}"
    news_res = requests.get(n_url).json().get('articles', [])[:5]
    market_news = "\n".join([f"- {a['title']}" for a in news_res])
    # 2.2 종목 리스트 확보 (AAPL, MSFT, NVDA 제외 필터링)
    r = requests.get("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies", timeout=30)
    tickers = pd.read_html(r.text)[0]["Symbol"].replace(".", "-", regex=True).tolist()
    targets = [t for t in tickers if t not in ["AAPL", "MSFT", "NVDA"]]
    
    # 5년($5y$) 벌크 데이터 확보 (약 1,250영업일)
    raw = yf.download(targets, period="5y", group_by="ticker", progress=False, threads=True)
    mkt = yf.download("^GSPC", period="5y", progress=False)['Close']
    pool = []
    for t in targets:
        try:
            df = raw[t].dropna()
            if len(df) < 500: continue
            c, v, h, l = df['Close'], df['Volume'], df['High'], df['Low']
            
            # 지표 1: $Z-score$ (RSI 기반 5년 역사적 희소성)
            diff = c.diff()
            gain = diff.where(lambda x: x>0, 0).rolling(14).mean()
            loss = -diff.where(lambda x: x<0, 0).rolling(14).mean().replace(0, 1)
            rsi = 100 - (100 / (1 + (gain / loss)))
            z = (rsi.iloc[-1] - rsi.mean()) / rsi.std()
            
            # 지표 2: $TDI$ (Traders Dynamic Index - 수급 밀도)
            tdi_pl = rsi.rolling(2).mean().iloc[-1]
            tdi_mbl = rsi.rolling(34).mean().iloc[-1]
            
            # 지표 3: $VWAP$ (Volume Weighted Average Price - 수급 평균가)
            vwap = (v * (h + l + c) / 3).cumsum() / v.cumsum()
            v_dist = (c.iloc[-1] / vwap.iloc[-1] - 1) * 100
            
            # 지표 4: $ATR$ Ratio (Average True Range - 변동성 응축 에너지)
            tr = pd.concat([h-l, abs(h-c.shift()), abs(l-c.shift())], axis=1).max(axis=1)
            atr_r = tr.rolling(14).mean().iloc[-1] / tr.rolling(14).mean().mean()
            
            # 지표 5: $\beta$ (Beta - 시장 대비 민감도)
            ret = c.pct_change().dropna()
            m_ret = mkt.pct_change().dropna()
            common = ret.index.intersection(m_ret.index)
            beta = ret.loc[common].cov(m_ret.loc[common]) / m_ret.loc[common].var()
            if abs(z) > 2.3: # 역사적 특이점 발견 시 수집
                pool.append({
                    "ticker": t, "price": round(c.iloc[-1], 2), "z": round(z, 2),
                    "tdi_gap": round(tdi_pl - tdi_mbl, 2), "beta": round(beta, 2),
                    "vwap_dist": round(v_dist, 2), "atr_r": round(atr_r, 2)
                })
        except: continue
    
    pool.sort(key=lambda x: abs(x['z']), reverse=True)
    return pool[:3], market_news
# ---------------------------------------------------------
# [STAGE 5: 아토믹 딜리버리 - 내용 보존 필터]
# ---------------------------------------------------------
def deliver_stage_5(agent_id, model, raw, m_summary=""):
    """
    [REPORT_START] 태그를 기준으로 통찰을 추출합니다.
    태그가 없으면 원본 전체를 사용하여 자연스러운 흐름을 유지합니다.
    """
    pattern = r"\[REPORT_START\](.*?)\[REPORT_END\]"
    match = re.search(pattern, raw, re.DOTALL)
    
    if match:
        clean = match.group(1).strip()
    else:
        # 태그가 없으면 원본 그대로 사용하되, 앞뒤 공백만 정리
        clean = raw.strip()
    if not clean or len(clean) < 50:
        clean = "⚠️ 분석 내용 생성 실패: 인과관계 데이터 인큐베이팅 부족."
    
    emoji = {"A": "📉", "B": "💡", "C": "💀"}.get(agent_id, "🏛️")
    title = {"A": "수량적 수급 인과 분석", "B": "역사적 지능 전략 증류", "C": "실존적 리스크 오답노트"}.get(agent_id)
    
    header = f"### 📊 [Market Summary]\n{m_summary}\n\n" if agent_id == "A" else ""
    msg = f"{header}## {emoji} {title} ({model})\n---\n{clean}\n"
    
    # 2000자 초과 방지 분할 전송
    for i in range(0, len(msg), 1900):
        requests.post(DISCORD_URL, json={"content": msg[i:i+1900]})
        time.sleep(1)
if __name__ == "__main__":
    try:
        # 감독님이 고정해주신 시장 상황 요약
        m_sum = "S&P500 Top50 내 과매수 종목은 3개... 강력한 상승 모멘텀 부재 및 관망세 짙음."
        
        # 1-2. 5년 시계열 전수 해부
        res_stats, res_news = run_full_diagnosis()
        
        # [핵심 수정] JSON 형식을 모델에게 보여주지 않기 위해, 데이터를 텍스트로 1차 변환
        context_str = "\n".join([
            f"- 종목: {item['ticker']}, 현재가: ${item['price']}, "
            f"Z-Score(희소성): {item['z']}, 이격도(VWAP): {item['vwap_dist']}%, "
            f"변동성(ATR): {item['atr_r']}배, 베타: {item['beta']}, "
            f"TDI Gap: {item['tdi_gap']}"
            for item in res_stats
        ])
        
        # 3. 3인 위원회 적대적 토론 (지능 복원 및 유려한 문장 강제)
        rule = (
            "당신은 월가의 전설적인 펀드매니저다. 아래 제공된 종목 데이터를 바탕으로 투자자들에게 보낼 '긴급 매매 전략 보고서'를 작성하라.\n"
            "**절대 규칙**:\n"
            "1. JSON, 딕셔너리, 코드 형식을 절대 출력하지 마라. 오직 줄글(텍스트)로만 작성하라.\n"
            "2. [REPORT_START] 와 [REPORT_END] 태그로 보고서 본문을 감싸라.\n"
            "3. 각 종목의 수치(Z-score, VWAP 등)를 인용하되, 나열하지 말고 문장 속에 자연스럽게 녹여라. (예: 'AAPL의 Z-score가 2.5에 달해 과매수 구간에 진입했습니다.')\n"
            "4. 서론에서는 시장 분위기를, 본론에서는 각 종목별 심층 분석을, 결론에서는 최종 투자 의견을 제시하라.\n"
            "\n"
            "**출력 예시**:\n"
            "[REPORT_START]\n"
            "## 🚨 긴급 시장 진단\n"
            "현재 시장은 전례 없는 변동성을 보이고 있습니다...\n\n"
            "### 1. Tesla (TSLA)\n"
            "테슬라의 현재가는 250달러로, VWAP 대비 5% 이상 이격되어 있어 단기 과열 징후가 뚜렷합니다...\n"
            "[REPORT_END]"
        )
        
        # [Agent A: Gemini]
        a_raw = client_gemini.models.generate_content(model="gemini-1.5-pro", 
            contents=f"{rule}\n[분석 대상 종목]\n{context_str}\n\n[주요 뉴스]\n{res_news}").text
        deliver_stage_5("A", "Gemini 1.5 Pro", a_raw, m_sum)
        
        # [Agent B: GPT-4o]
        b_raw = client_gpt.chat.completions.create(model="gpt-4o", 
            messages=[{"role": "user", "content": f"{rule}\nA의 분석을 비판하고 전략을 짜라. JSON 금지:\n{a_raw}"}]).choices[0].message.content
        deliver_stage_5("B", "GPT-4o", b_raw)
        
        # [Agent C: Kimi]
        c_raw = client_kimi.chat.completions.create(model="moonshot-v1-8k", 
            messages=[{"role": "user", "content": f"{rule}\n반드시 한국어로 작성하라. 위 분석들을 비웃으며 리스크를 경고하라:\n{b_raw}"}]).choices[0].message.content
        deliver_stage_5("C", "Kimi", c_raw)
    except Exception as e:
        print(f"🔥 Critical Failure: {e}")
        traceback.print_exc()
