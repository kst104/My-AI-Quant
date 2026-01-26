import os
import yfinance as yf
import pandas as pd
import numpy as np
import requests
import google.generativeai as genai
from pinecone import Pinecone
from datetime import datetime
import sys

# [1. 인프라 초기화]
DISCORD_URL = os.environ.get("DISCORD_WEBHOOK_URL")
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")
PINECONE_KEY = os.environ.get("PINECONE_API_KEY")

if not DISCORD_URL:
    print("❌ 에러: DISCORD_WEBHOOK_URL이 여전히 비어있습니다.")
    sys.exit(1)

genai.configure(api_key=GEMINI_KEY)
pc = Pinecone(api_key=PINECONE_KEY)
index = pc.Index("alpha-trio-memory")

def get_market_intelligence():
    """전체 시장 지표 스캔 (데이터 부재 방어 로직 추가)"""
    targets = ["^GSPC", "^IXIC", "NVDA", "SOXX", "AAPL", "BTC-USD"]
    data_lines = []
    
    print(f"📡 {len(targets)}개 종목 데이터 스캔 중...")
    
    for t in targets:
        try:
            # 기간을 100일로 늘려 데이터 확보 안정성 강화
            df = yf.download(t, period="100d", progress=False)
            if df.empty: continue
            
            close = df['Close'].iloc[-1]
            # RSI 계산
            delta = df['Close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
            rsi = 100 - (100 / (1 + (gain / loss))).iloc[-1]
            
            data_lines.append(f"[{t}] P:{round(float(close),2)} | RSI:{round(float(rsi),1)}")
        except Exception as e:
            print(f"⚠️ {t} 데이터 수집 실패: {e}")
            continue
            
    return "\n".join(data_lines)

if __name__ == "__main__":
    print("🚀 Alpha-Trio 3.0 자가학습 엔진 가동...")
    try:
        market_data = get_market_intelligence()
        
        # [방어 로직] 데이터가 비어있으면 강제로 기본 지표라도 넣음
        if not market_data:
            print("⚠️ 시장 데이터를 가져오지 못해 기본 브리핑으로 대체합니다.")
            market_data = "현재 시장 실시간 데이터 수집 지연 중. 매크로 지표 중심 분석 필요."

        # [자가학습] Pinecone에서 어제의 기억 소환
        embed_res = genai.embed_content(model="models/text-embedding-004", content=market_data)
        embed = embed_res['embedding']
        
        past = index.query(vector=embed, top_k=1, include_metadata=True)
        yesterday_report = past['matches'][0]['metadata']['conclusion'] if past['matches'] else "최초 분석 단계. 가설 수립 필요."

        # [3인 에이전트 위원회]
        model = genai.GenerativeModel('gemini-1.5-pro')
        prompt = f"""당신은 Alpha-Trio 전략 위원회입니다.
        [어제의 가설]: {yesterday_report}
        [오늘의 데이터]: {market_data}

        1. 에이전트 A(Quant): 어제 예측 수치와 오늘 실제치의 '괴리'를 수학적으로 비판하라.
        2. 에이전트 B(Dewey): 시장의 경험적 흐름에서 '변하지 않는 지식'을 증류하라.
        3. 에이전트 C(Beckett): 위 두 명의 논리는 희망고문이다. 가장 비관적인 시나리오를 설계하라.

        결과를 JSON 형식으로 작성하고, 반드시 'Action'(매수/매도/관망)을 포함하십시오."""
        
        response = model.generate_content(prompt)
        verdict = response.text
        
        # Pinecone에 오늘 배운 지식 저장
        index.upsert(vectors=[{
            "id": str(datetime.now().timestamp()), 
            "values": embed, 
            "metadata": {"conclusion": verdict, "date": str(datetime.now())}
        }])
        
        # 디스코드 분할 보고
        chunks = [verdict[i:i+1800] for i in range(0, len(verdict), 1800)]
        for chunk in chunks:
            requests.post(DISCORD_URL, json={"content": f"🏛️ **Alpha-Trio 3.0 자가학습 보고**\n```json\n{chunk}\n```"})
        
        print("✅ 루프 완료 및 디스코드 전송 성공")
        
    except Exception as e:
        print(f"🔥 치명적 에러: {e}")
        sys.exit(1)