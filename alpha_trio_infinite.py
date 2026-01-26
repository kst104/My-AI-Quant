import os
import yfinance as yf
import pandas as pd
import numpy as np
import requests
from google import genai
from pinecone import Pinecone
from datetime import datetime
import sys

# [1. 시스템 상수 - 404 방지용 절대 경로]
MODEL_ID = "gemini-1.5-pro"
EMBED_ID = "text-embedding-004"

# [2. 인프라 초기화]
DISCORD_URL = os.environ.get("DISCORD_WEBHOOK_URL")
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")
PINECONE_KEY = os.environ.get("PINECONE_API_KEY")
NEWS_KEY = os.environ.get("NEWS_API_KEY")

if not all([DISCORD_URL, GEMINI_KEY, PINECONE_KEY]):
    print("❌ 에러: 필수 API 설정이 누락되었습니다. Secrets를 확인하세요.")
    sys.exit(1)

client = genai.Client(api_key=GEMINI_KEY)
pc = Pinecone(api_key=PINECONE_KEY)
index = pc.Index("alpha-trio-memory")

# [3. 고지능 지표 엔진: TDI, BB, RSI 연산]
def calculate_expert_indicators(df):
    if df.empty or len(df) < 40: return None
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
    
    return df.dropna()

# [4. S&P 500 전수 조사: 5년($5y$) 타임리스 스캔]
def explore_sp500_full_galaxy():
    print(f"🌌 S&P 500 전 종목 5개년 전수 조사 시작... (대상: 500+)")
    try:
        table = pd.read_html('https://en.wikipedia.org/wiki/List_of_S%26P_500_companies')
        tickers = table[0]['Symbol'].replace('.', '-', regex=True).tolist()
        
        # 5년치 전체 데이터 병렬 다운로드
        data = yf.download(tickers, period="5y", group_by='ticker', progress=False, threads=True)
        
        stats = {"Overbought": 0, "U-Break": 0, "L-Break": 0}
        highlights = []

        for t in tickers:
            try:
                processed = calculate_expert_indicators(data[t])
                if processed is None: continue
                l = processed.iloc[-1]
                price = l['Close']
                
                if l['RSI'] > 70: stats["Overbought"] += 1
                if price > l['BBU']: stats["U-Break"] += 1
                if price < l['BBL']: stats["L-Break"] += 1
                
                if t in ["AAPL", "NVDA", "MSFT", "TSLA", "GOOGL"]:
                    highlights.append(f"[{t}] RSI:{round(float(l['RSI']),1)} | TDI:{round(float(l['TDI_PL']),1)} | BB:{'Upper' if price > l['BBU'] else 'Neutral'}")
            except: continue
            
        summary = f"📊 S&P500 5y 통계: 과매수({stats['Overbought']}), BB상단돌파({stats['U-Break']}), BB하단이탈({stats['L-Break']})\n"
        return summary + "\n".join(highlights)
    except Exception as e:
        return f"데이터 스캔 지연 (원인: {e})"

if __name__ == "__main__":
    print(f"🚀 Alpha-Trio Infinite V5 엔진 점화... (Target Model: {MODEL_ID})")
    try:
        # 1. 데이터 수집
        m_data = explore_sp500_full_galaxy()
        n_res = requests.get(f"https://newsapi.org/v2/top-headlines?category=business&language=en&apiKey={NEWS_KEY}").json()
        n_data = "\n".join([f"🔥 {a['title']}" for a in n_res.get('articles', [])[:5]]) if 'articles' in n_res else "뉴스 지연"

        # 2. 질문지 구성 및 보장
        brain_input = f"지표:\n{m_data}\n\n뉴스:\n{n_data}"
        if len(brain_input.strip()) < 50:
            brain_input = "데이터 수집 지연 상태. 500개 종목의 역사적 변동성과 불확실성을 자가학습하라."

        # 3. 임베딩 및 기억 소환 (접두사 제거 확인)
        print(f"📡 임베딩 모델 호출: {EMBED_ID}")
        embed_res = client.models.embed_content(model=EMBED_ID, contents=brain_input)
        vector = embed_res.embeddings[0].values
        
        past = index.query(vector=vector, top_k=1, include_metadata=True)
        memory = past['matches'][0]['metadata']['conclusion'] if past['matches'] else "신규 분석 패러다임 시작."

        # 4. [수정] 제미나이 위원회 가동 (모델 ID 강제 세팅)
        prompt = f"""당신은 Alpha-Trio 위원회입니다. 
        데이터: {brain_input} / 기억: {memory}

        1. A(Quant): 500개 종목의 $BB$, $TDI$, $RSI$ 분포를 분석하여 수급 함정을 수학적으로 비판하라.
        2. B(John Dewey): 뉴스와 지표를 결합하여 '경험적 변곡점'을 찾아 지식을 증류하라.
        3. C(Samuel Beckett): 과거의 실수를 근거로 낙관론을 조롱하고 최악의 시나리오를 설계하라.
        JSON 형식으로만 답하십시오."""

        print(f"⚖️ 지능형 판결 요청 중... (Model: {MODEL_ID})")
        response = client.models.generate_content(
            model=MODEL_ID, 
            contents=prompt
        )
        verdict = response.text

        # 5. 저장 및 보고
        index.upsert(vectors=[{"id": str(datetime.now().timestamp()), "values": vector, "metadata": {"conclusion": verdict, "date": str(datetime.now())}}])
        
        chunks = [verdict[i:i+1800] for i in range(0, len(verdict), 1800)]
        for chunk in chunks:
            requests.post(DISCORD_URL, json={"content": f"🏛️ **Alpha-Trio Infinite 보고**\n```json\n{chunk}\n```"})
        
        print("✅ 자가학습 루프 완료. 디스코드를 확인하세요!")

    except Exception as e:
        print(f"🔥 치명적 에러 자백: {e}")
        sys.exit(1)