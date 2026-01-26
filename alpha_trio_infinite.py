import os
import yfinance as yf
import pandas as pd
import numpy as np
import requests
import google.generativeai as genai
from pinecone import Pinecone
from datetime import datetime
import sys

# [1. 하이엔드 인프라 로드]
DISCORD_URL = os.environ.get("DISCORD_WEBHOOK_URL")
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")
PINECONE_KEY = os.environ.get("PINECONE_API_KEY")
NEWS_KEY = os.environ.get("NEWS_API_KEY")

if not all([DISCORD_URL, GEMINI_KEY, PINECONE_KEY]):
    print("❌ 필수 API 설정이 누락되었습니다.")
    sys.exit(1)

genai.configure(api_key=GEMINI_KEY)
pc = Pinecone(api_key=PINECONE_KEY)
index = pc.Index("alpha-trio-memory")

# [2. 초지능 기술 지표 연산 ($LaTeX$)]
def calculate_expert_indicators(df):
    if df.empty or len(df) < 35: return None
    df = df.copy()
    close = df['Close']
    
    # Bollinger Bands ($BB$)
    df['BB_Mid'] = close.rolling(window=20).mean()
    df['BB_Std'] = close.rolling(window=20).std()
    df['BBU'] = df['BB_Mid'] + (df['BB_Std'] * 2)
    df['BBL'] = df['BB_Mid'] - (df['BB_Std'] * 2)
    
    # RSI & TDI
    delta = close.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=13).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=13).mean()
    df['RSI'] = 100 - (100 / (1 + (gain / loss)))
    df['TDI_PL'] = df['RSI'].rolling(window=2).mean()
    df['TDI_MBL'] = df['RSI'].rolling(window=34).mean()
    
    # ATR ($ATR$)
    tr = pd.concat([df['High']-df['Low'], abs(df['High']-close.shift()), abs(df['Low']-close.shift())], axis=1).max(axis=1)
    df['ATR'] = tr.rolling(window=14).mean()
    
    return df.dropna()

# [3. S&P 500 전 종목 5개년 전수 조사]
def get_sp500_full_exploration():
    print("🔍 S&P 500 전 종목(500+) 5개년 데이터 전수 조사 가동...")
    try:
        # Wikipedia에서 S&P 500 리스트 확보
        table = pd.read_html('https://en.wikipedia.org/wiki/List_of_S%26P_500_companies')
        tickers = table[0]['Symbol'].replace('.', '-', regex=True).tolist()
        
        # 500개 종목을 5년치($5y$) 한꺼번에 다운로드
        data = yf.download(tickers, period="5y", group_by='ticker', progress=False)
        
        stats = {"U-Break": 0, "L-Break": 0, "Overbought": 0, "Oversold": 0}
        highlights = []

        for t in tickers:
            try:
                stock_df = data[t]
                processed = calculate_expert_indicators(stock_df)
                if processed is None: continue
                
                l = processed.iloc[-1]
                price = l['Close']
                
                # 통계 수집
                if price > l['BBU']: stats["U-Break"] += 1
                if price < l['BBL']: stats["L-Break"] += 1
                if l['RSI'] > 70: stats["Overbought"] += 1
                if l['RSI'] < 30: stats["Oversold"] += 1
                
                # 주요 지표주 상세 샘플링
                if t in ["AAPL", "NVDA", "MSFT", "TSLA", "AMZN"]:
                    highlights.append(f"[{t}] P:{round(float(price),2)} | RSI:{round(float(l['RSI']),1)} | TDI_PL:{round(float(l['TDI_PL']),1)}")
            except: continue
            
        summary = f"📊 S&P500 5y 스캔: BB상단돌파({stats['U-Break']}), BB하단이탈({stats['L-Break']}), 과매수({stats['Overbought']}), 과매도({stats['Oversold']})\n"
        return summary + "\n".join(highlights)
    except Exception as e:
        return f"전수 조사 시스템 일시적 부재 (원인: {e})"

if __name__ == "__main__":
    print("🚀 Alpha-Trio 9.0 Infinity 엔진 시동...")
    try:
        # 데이터 수집 (절대로 비어있지 않게 보장)
        m_data = get_sp500_full_exploration()
        n_res = requests.get(f"https://newsapi.org/v2/top-headlines?category=business&language=en&apiKey={NEWS_KEY}").json()
        n_data = "\n".join([f"🔥 {a['title']}" for a in n_res.get('articles', [])[:5]]) if 'articles' in n_res else "뉴스 지연"

        # [방어] 질문지가 비어있으면 강제로 채움
        market_context = f"시장 지표:\n{m_data}\n\n뉴스 흐름:\n{n_data}"
        if len(market_context.strip()) < 20:
            market_context = "현재 시장 데이터 노이즈로 인해 기술적 지표 확보 지연. 거시적 관점에서 분석을 강행하라."

        # Vector DB 기억 소환
        embed = genai.embed_content(model="models/text-embedding-004", content=market_context)['embedding']
        past = index.query(vector=embed, top_k=1, include_metadata=True)
        memory = past['matches'][0]['metadata']['conclusion'] if past['matches'] else "신규 세대 학습 시작."

        # [감독님 계획표에 따른 3인 위원회 정밀 가동]
        model = genai.GenerativeModel('gemini-1.5-pro')
        prompt = f"""당신은 S&P 500 전 종목의 5년 역사를 관통하는 Alpha-Trio 위원회입니다.
        데이터: {market_context} / 기억: {memory}

        [임무 분배]
        1. 에이전트 A (Quant): 500개 종목의 $BB$, $TDI$, $RSI$ 분포를 통해 시장 전체의 에너지를 수학적으로 확정하라.
        2. 에이전트 B (John Dewey): 현재의 뉴스 흐름과 500개 종목의 집단 움직임을 결합하여 '경험적 지식'을 증류하라.
        3. 에이전트 C (Samuel Beckett): 과거의 실패(기억)를 근거로 현재의 지표적 낙관을 잔인하게 조롱하고 파멸적 시나리오를 설계하라.

        반드시 JSON 형식으로만 답하십시오."""

        response = model.generate_content(prompt)
        verdict = response.text

        # 저장 및 전송
        index.upsert(vectors=[{"id": str(datetime.now().timestamp()), "values": embed, "metadata": {"conclusion": verdict, "date": str(datetime.now())}}])
        
        chunks = [verdict[i:i+1800] for i in range(0, len(verdict), 1800)]
        for chunk in chunks:
            requests.post(DISCORD_URL, json={"content": f"🏛️ **Alpha-Trio 9.0 전수조사 보고**\n```json\n{chunk}\n```"})
        
        print("✅ 500개 종목 전수조사 및 자가학습 완료.")

    except Exception as e:
        print(f"🔥 치명적 에러: {e}")
        sys.exit(1)