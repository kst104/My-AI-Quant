import os
import yfinance as yf
import pandas as pd
import numpy as np
import requests
from google import genai
from pinecone import Pinecone
from datetime import datetime
import sys

# [1. 인프라 초기화]
DISCORD_URL = os.environ.get("DISCORD_WEBHOOK_URL")
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")
PINECONE_KEY = os.environ.get("PINECONE_API_KEY")
NEWS_KEY = os.environ.get("NEWS_API_KEY")

if not all([DISCORD_URL, GEMINI_KEY, PINECONE_KEY]):
    print("❌ 에러: 필수 API 설정이 부족합니다.")
    sys.exit(1)

# 최신 SDK 클라이언트 설정
client = genai.Client(api_key=GEMINI_KEY)
pc = Pinecone(api_key=PINECONE_KEY)
index = pc.Index("alpha-trio-memory")

# [2. 기술적 지능 엔진: LaTeX 기반 정밀 연산]
def calculate_expert_indicators(df):
    if df.empty or len(df) < 40: return None
    df = df.copy()
    close = df['Close']
    
    # 볼린저 밴드 ($BB$)
    df['BB_Mid'] = close.rolling(window=20).mean()
    df['BB_Std'] = close.rolling(window=20).std()
    df['BBU'] = df['BB_Mid'] + (df['BB_Std'] * 2)
    df['BBL'] = df['BB_Mid'] - (df['BB_Std'] * 2)
    
    # RSI & TDI (Traders Dynamic Index)
    delta = close.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=13).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=13).mean()
    df['RSI'] = 100 - (100 / (1 + (gain / loss)))
    df['TDI_PL'] = df['RSI'].rolling(window=2).mean() # Price Line
    df['TDI_MBL'] = df['RSI'].rolling(window=34).mean() # Market Base Line
    
    return df.dropna()

# [3. S&P 500 전수 조사: 5개년 타임리스 스캔]
def explore_sp500_full_galaxy():
    print("🌌 S&P 500 전 종목 5개년 전수 조사 가동...")
    try:
        # Wikipedia에서 실시간 S&P 500 리스트 확보
        table = pd.read_html('https://en.wikipedia.org/wiki/List_of_S%26P_500_companies')
        tickers = table[0]['Symbol'].replace('.', '-', regex=True).tolist()
        
        # 5년($5y$) 전체 데이터 배치 다운로드 (속도 최적화)
        data = yf.download(tickers, period="5y", group_by='ticker', progress=False)
        
        stats = {"Overbought": 0, "Oversold": 0, "U-Break": 0, "L-Break": 0}
        market_sentiment_score = []

        for t in tickers:
            try:
                processed = calculate_expert_indicators(data[t])
                if processed is None: continue
                l = processed.iloc[-1]
                price = l['Close']
                
                # 통계 수집
                if l['RSI'] > 70: stats["Overbought"] += 1
                if price > l['BBU']: stats["U-Break"] += 1
                if price < l['BBL']: stats["L-Break"] += 1
                
                # 주요 지표주 상태 요약
                if t in ["AAPL", "NVDA", "MSFT", "TSLA", "GOOGL"]:
                    market_sentiment_score.append(f"[{t}] RSI:{round(float(l['RSI']),1)} | TDI:{round(float(l['TDI_PL']),1)} | BB:{'Upper' if price > l['BBU'] else 'Lower' if price < l['BBL'] else 'Neutral'}")
            except: continue
            
        summary = f"📊 S&P500 5개년 통계: 과매수({stats['Overbought']}), BB상단돌파({stats['U-Break']}), BB하단이탈({stats['L-Break']})\n"
        return summary + "\n".join(market_sentiment_score)
    except Exception as e:
        return f"데이터 스캔 중 부분적 지연 발생 (사유: {e})"

if __name__ == "__main__":
    print("🚀 Alpha-Trio Infinite V3 엔진 점화...")
    try:
        # 데이터 수집
        m_data = explore_sp500_full_galaxy()
        n_res = requests.get(f"https://newsapi.org/v2/top-headlines?category=business&language=en&apiKey={NEWS_KEY}").json()
        n_data = "\n".join([f"🔥 {a['title']}" for a in n_res.get('articles', [])[:5]]) if 'articles' in n_res else "실시간 뉴스 지연"

        brain_input = f"지표:\n{m_data}\n\n뉴스:\n{n_data}"
        
        # [방어] Empty Content 방지
        if len(brain_input.strip()) < 50:
            brain_input = "현재 시장 데이터 스트리밍 일시적 지연. 기존 5년의 역사적 패턴과 매크로 지식을 바탕으로 자가성장을 지속하라."

        # 최신 임베딩 모델 호출 (ID 수정)
        embed_res = client.models.embed_content(model="text-embedding-004", contents=brain_input)
        vector = embed_res.embeddings[0].values
        
        past = index.query(vector=vector, top_k=1, include_metadata=True)
        memory = past['matches'][0]['metadata']['conclusion'] if past['matches'] else "신규 분석 패러다임 시작."

        # [3인 위원회: 철학적 정예 분업]
        # 모델명을 'gemini-1.5-pro'로 정확히 지정 (prefix 제거)
        prompt = f"""당신은 Alpha-Trio Infinite 위원회입니다.
        데이터: {brain_input} / 기억: {memory}

        [에이전트 임무]
        1. A(Quant): 500개 종목의 $BB$, $TDI$, $RSI$ 분포를 분석하여 수급의 왜곡을 수학적으로 확정하라.
        2. B(John Dewey): 뉴스 흐름과 지표를 결합하여 현재가 어떤 '경험적 변곡점'인지 지식을 증류하라.
        3. C(Samuel Beckett): 과거의 기억을 소환하여 현재의 낙관론을 조롱하고 최악의 시나리오를 설계하라.

        JSON 형식으로 'Action', 'Strategy', 'Analysis(A,B,C)'를 포함하십시오."""

        # 최신 SDK 호출 규격 적용
        response = client.models.generate_content(
            model="gemini-1.5-pro",
            contents=prompt
        )
        verdict = response.text

        # 저장 및 보고
        index.upsert(vectors=[{"id": str(datetime.now().timestamp()), "values": vector, "metadata": {"conclusion": verdict, "date": str(datetime.now())}}])
        
        chunks = [verdict[i:i+1800] for i in range(0, len(verdict), 1800)]
        for chunk in chunks:
            requests.post(DISCORD_URL, json={"content": f"🏛️ **Alpha-Trio Infinite V3 보고**\n```json\n{chunk}\n```"})
        
        print("✅ 자가학습 루프 완료. 디스코드에서 에이전트들의 토론을 확인하세요.")

    except Exception as e:
        print(f"🔥 에러 발생 사유: {e}")
        sys.exit(1)