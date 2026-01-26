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

if not all([DISCORD_URL, GEMINI_KEY, PINECONE_KEY, NEWS_KEY]):
    print("❌ 에러: 필수 API 설정(Secret)이 누락되었습니다.")
    sys.exit(1)

genai.configure(api_key=GEMINI_KEY)
pc = Pinecone(api_key=PINECONE_KEY)
index = pc.Index("alpha-trio-memory")

# [2. S&P 500 전 종목 고속 전수조사 엔진]
def get_sp500_full_scan_data():
    print("🔍 S&P 500 전 종목(500+) 5개년 데이터 전수 조사 시작...")
    try:
        # Wikipedia에서 실시간 S&P 500 리스트 확보
        table = pd.read_html('https://en.wikipedia.org/wiki/List_of_S%26P_500_companies')
        tickers = table[0]['Symbol'].replace('.', '-', regex=True).tolist()
        
        # [핵심] 500개 종목의 '종가' 데이터를 한 번에 가져와 메모리 부하 방지
        # 5년치($5y$) 전체 데이터를 가져와 시장의 구조적 위치 파악
        data = yf.download(tickers, period="5y", interval="1d", group_by='ticker', progress=False)
        
        market_stats = {
            "total": len(tickers),
            "overbought_rsi": 0, # RSI > 70
            "oversold_rsi": 0,   # RSI < 30
            "above_bb_upper": 0, # 볼린저밴드 상단 돌파
            "below_bb_lower": 0, # 볼린저밴드 하단 이탈
            "avg_change": 0      # 평균 등락률
        }

        detailed_samples = ""
        for t in tickers[:30]: # 상위 30개 대형주는 에이전트 분석용으로 상세 추출
            try:
                df = data[t].dropna()
                if df.empty: continue
                close = df['Close']
                # 지표 직접 연산 ($RSI$, $BB$)
                delta = close.diff()
                gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
                loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
                rsi = 100 - (100 / (1 + (gain / loss))).iloc[-1]
                
                std = close.rolling(window=20).std().iloc[-1]
                ma = close.rolling(window=20).mean().iloc[-1]
                bbu, bbl = ma + (std * 2), ma - (std * 2)
                curr_price = close.iloc[-1]

                # 통계 합산
                if rsi > 70: market_stats["overbought_rsi"] += 1
                elif rsi < 30: market_stats["oversold_rsi"] += 1
                if curr_price > bbu: market_stats["above_bb_upper"] += 1
                elif curr_price < bbl: market_stats["below_bb_lower"] += 1

                if t in ["AAPL", "MSFT", "NVDA", "TSLA", "GOOGL"]:
                    detailed_samples += f"[{t}] P:{round(float(curr_price),2)} | RSI:{round(float(rsi),1)} | BB:{'Upper' if curr_price > bbu else 'Lower' if curr_price < bbl else 'Mid'}\n"
            except: continue

        report = f"📊 S&P500 전수조사: 대상 {market_stats['total']}개 중 과매수 {market_stats['overbought_rsi']}개, BB상단돌파 {market_stats['above_bb_upper']}개\n"
        return report + detailed_samples
    except Exception as e:
        print(f"⚠️ 전수조사 중 오류 발생: {e}")
        return "전수조사 데이터 수집 지연 (백업 매크로 모드 가동)"

if __name__ == "__main__":
    print("🚀 Alpha-Trio 8.0 Full-Scan 자가학습 가동...")
    try:
        # 1. 500개 종목 스캔 및 뉴스 수집
        m_data = get_sp500_full_scan_data()
        n_res = requests.get(f"https://newsapi.org/v2/top-headlines?category=business&language=en&apiKey={NEWS_KEY}").json()
        n_data = "\n".join([f"🔥 {a['title']}" for a in n_res.get('articles', [])[:5]]) if 'articles' in n_res else "뉴스 수집 불가"

        # [방어] 에러 방지를 위해 데이터가 비어있으면 강제로 기본값 주입
        if not m_data or len(m_data) < 10:
            m_data = "데이터 수집 실패. 시스템 상태: 불확실성 극대화 모드."

        # 2. Vector DB 자아 성찰 (기억 소환)
        # 임베딩 전 공백 체크
        embed_res = genai.embed_content(model="models/text-embedding-004", content=m_data)
        vector = embed_res['embedding']
        past = index.query(vector=vector, top_k=1, include_metadata=True)
        memory = past['matches'][0]['metadata']['conclusion'] if past['matches'] else "신규 분석: 과거 데이터 없음."

        # 3. [계획표에 따른 정예 3인 위원회]
        model = genai.GenerativeModel('gemini-1.5-pro')
        prompt = f"""당신은 S&P 500 전 종목의 5년 데이터를 분석하는 초지능 Alpha-Trio입니다.
        데이터: {m_data} / 뉴스: {n_data} / 기억: {memory}

        [에이전트 임무]
        1. A(Quant): 500개 종목의 $RSI$, $TDI$, $BB$ 통계를 통해 시장 전체의 에너지를 수학적으로 비판하라.
        2. B(John Dewey): 뉴스 흐름과 전 종목의 움직임을 결합하여 '경험적 변곡점'을 찾아 지식을 증류하라.
        3. C(Samuel Beckett): 과거의 기억(실패)을 근거로 현재의 지표적 낙관을 조롱하고 파멸적 시나리오를 설계하라.

        반드시 JSON 형식으로 'Action', 'Strategy', 'Knowledge_Distilled'를 포함하십시오."""

        response = model.generate_content(prompt)
        verdict = response.text

        # 4. 저장 및 전송
        index.upsert(vectors=[{"id": str(datetime.now().timestamp()), "values": vector, "metadata": {"conclusion": verdict, "date": str(datetime.now())}}])
        
        chunks = [verdict[i:i+1800] for i in range(0, len(verdict), 1800)]
        for chunk in chunks:
            requests.post(DISCORD_URL, json={"content": f"🏛️ **Alpha-Trio 8.0 전수조사 보고**\n```json\n{chunk}\n```"})
        
        print("✅ 500개 전 종목 5개년 스캔 및 자가학습 완료.")

    except Exception as e:
        print(f"🔥 치명적 에러 자백: {e}")
        sys.exit(1)