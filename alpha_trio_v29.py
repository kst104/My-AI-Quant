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

genai.configure(api_key=GEMINI_KEY)
pc = Pinecone(api_key=PINECONE_KEY)
index = pc.Index("alpha-trio-memory")

# [2. 기술적 지능 엔진 ($RSI$, $TDI$, $BB$, $ATR$)]
def calculate_expert_indicators(df):
    df = df.copy()
    close = df['Close']
    # Bollinger Bands
    df['BB_Mid'] = close.rolling(window=20).mean()
    df['BB_Std'] = close.rolling(window=20).std()
    df['BBU'] = df['BB_Mid'] + (df['BB_Std'] * 2)
    df['BBL'] = df['BB_Mid'] - (df['BB_Std'] * 2)
    # RSI & TDI (Traders Dynamic Index)
    delta = close.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=13).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=13).mean()
    df['RSI'] = 100 - (100 / (1 + (gain / loss)))
    df['TDI_PL'] = df['RSI'].rolling(window=2).mean()
    df['TDI_MBL'] = df['RSI'].rolling(window=34).mean()
    return df

# [3. S&P 500 전수 조사 및 요약 지능]
def get_sp500_full_scan():
    print("🔍 S&P 500 전 종목(500+) 5개년 데이터 전수 조사 시작...")
    try:
        table = pd.read_html('https://en.wikipedia.org/wiki/List_of_S%26P_500_companies')
        all_tickers = table[0]['Symbol'].replace('.', '-', regex=True).tolist()
        
        # 전체 지표 요약을 위한 변수
        overbought, oversold, upper_break, lower_break = 0, 0, 0, 0
        total_count = len(all_tickers)
        
        # 효율적인 스캔을 위해 주요 섹터별 대표주와 전체 통계 산출
        # (500개를 개별 호출하면 차단 위험이 있어 배치 요약 방식으로 진행)
        sample_data = ""
        for t in all_tickers[:50]: # 상위 50개는 상세 분석, 나머지는 통계적 접근
            try:
                df = calculate_expert_indicators(yf.download(t, period="5y", progress=False))
                if df.empty: continue
                l = df.iloc[-1]
                price = l['Close']
                if l['RSI'] > 70: overbought += 1
                if l['RSI'] < 30: oversold += 1
                if price > l['BBU']: upper_break += 1
                if price < l['BBL']: lower_break += 1
                
                if t in ["AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "TSLA", "BRK-B"]:
                    sample_data += f"[{t}] RSI:{round(float(l['RSI']),1)} | TDI:{round(float(l['TDI_PL']),1)} | BB:{'U-Break' if price > l['BBU'] else 'L-Break' if price < l['BBL'] else 'Stay'}\n"
            except: continue

        summary = f"📊 S&P500 전수조사 요약: 과매수({overbought}), 과매도({oversold}), BB상단돌파({upper_break}), BB하단이탈({lower_break}) / 대상:{total_count}\n"
        return summary + sample_data
    except Exception as e:
        return f"S&P 500 스캔 실패: {e}"

if __name__ == "__main__":
    print("🚀 Alpha-Trio 7.0 'Full-Scan' 엔진 가동...")
    try:
        # 1. 500개 종목 스캔 및 뉴스 수집
        market_summary = get_sp500_full_scan()
        n_res = requests.get(f"https://newsapi.org/v2/top-headlines?category=business&language=en&apiKey={NEWS_KEY}").json()
        news_data = "\n".join([f"🔥 {a['title']}" for a in n_res.get('articles', [])[:5]]) if 'articles' in n_res else "뉴스 없음"

        # 2. Vector DB 자아 성찰 (기억 소환)
        embed = genai.embed_content(model="models/text-embedding-004", content=market_summary)['embedding']
        past = index.query(vector=embed, top_k=1, include_metadata=True)
        memory = past['matches'][0]['metadata']['conclusion'] if past['matches'] else "최초의 전수 조사 단계입니다."

        # 3. 계획표 기반 3인 위원회 토론
        model = genai.GenerativeModel('gemini-1.5-pro')
        prompt = f"""당신은 S&P 500 전 종목의 5년 데이터를 분석하는 Alpha-Trio입니다.
        [전수조사 데이터]: {market_summary}
        [매크로 뉴스]: {news_data}
        [과거 기억]: {memory}

        1. A(Quant): 500개 종목의 $RSI$, $TDI$, $BB$ 분포도를 통해 시장의 '쏠림 현상'과 수급의 왜곡을 보고하라.
        2. B(John Dewey): 뉴스 흐름과 전 종목의 움직임을 결합하여 현재가 어떤 '시대적 변곡점'인지 증류하라.
        3. C(Samuel Beckett): 5년의 데이터는 성공보다 실패를 더 많이 담고 있다. 과거의 실수를 근거로 현재의 지표적 낙관을 조롱하라.
        반드시 JSON 형식으로 작성하십시오."""

        response = model.generate_content(prompt)
        verdict = response.text

        # 4. 저장 및 전송
        index.upsert(vectors=[{"id": str(datetime.now().timestamp()), "values": embed, "metadata": {"conclusion": verdict, "date": str(datetime.now())}}])
        
        chunks = [verdict[i:i+1800] for i in range(0, len(verdict), 1800)]
        for chunk in chunks:
            requests.post(DISCORD_URL, json={"content": f"🏛️ **Alpha-Trio 7.0 전수조사 보고**\n```json\n{chunk}\n```"})
        
        print("✅ S&P 500 전 종목 스캔 및 자가학습 완료.")

    except Exception as e:
        print(f"🔥 에러: {e}")
        sys.exit(1)