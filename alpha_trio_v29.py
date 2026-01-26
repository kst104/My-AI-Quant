import os
import yfinance as yf
import pandas as pd
import numpy as np
import requests
import google.generativeai as genai
from pinecone import Pinecone
from datetime import datetime
import sys

# 1. 인프라 로드 및 주소 검증
DISCORD_URL = os.environ.get("DISCORD_WEBHOOK_URL")
if not DISCORD_URL:
    print("❌ 에러: GitHub Secrets에 DISCORD_WEBHOOK_URL이 등록되지 않았습니다!")
    sys.exit(1)

genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))
pc = Pinecone(api_key=os.environ.get("PINECONE_API_KEY"))
index = pc.Index("alpha-trio-memory")

def get_market_intelligence():
    """전체 시장 지표 스캔 (S&P500, 나스닥, 변동성, 주요 섹터)"""
    targets = ["^GSPC", "^IXIC", "^VIX", "NVDA", "SOXX", "BTC-USD"]
    data = ""
    for t in targets:
        try:
            df = yf.download(t, period="60d", progress=False)
            close = df['Close'].iloc[-1]
            # RSI 직접 계산 (지능형 지표)
            delta = df['Close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
            rsi = 100 - (100 / (1 + (gain / loss))).iloc[-1]
            data += f"[{t}] P:{round(float(close),2)} | RSI:{round(float(rsi),1)}\n"
        except: continue
    return data

if __name__ == "__main__":
    print("🚀 Alpha-Trio 2.9 자가학습 루프 시작...")
    try:
        market_data = get_market_intelligence()
        
        # [자가학습] Pinecone에서 가장 유사한 어제의 가설 소환
        embed = genai.embed_content(model="models/text-embedding-004", content=market_data)['embedding']
        past = index.query(vector=embed, top_k=1, include_metadata=True)
        yesterday_report = past['matches'][0]['metadata']['conclusion'] if past['matches'] else "최초 분석 단계입니다."

        # [3인 에이전트 위원회 가동]
        model = genai.GenerativeModel('gemini-1.5-pro')
        prompt = f"""당신은 자산 운용사 Alpha-Trio의 수석 전략 위원회입니다.
        [어제의 가설]: {yesterday_report}
        [오늘의 시장 데이터]: {market_data}

        에이전트 A(Quant): 어제의 예측 수치와 오늘의 실제치를 대조하여 오차를 정밀하게 비판하라.
        에이전트 B(Dewey): 오늘의 데이터에서 '새로운 경험적 질서'를 발견하고 지식을 증류하라.
        에이전트 C(Beckett): 모든 희망을 버리고 최악의 폭락 시나리오를 설계하라.

        반드시 JSON 형식으로만 답하십시오."""
        
        verdict = model.generate_content(prompt).text
        
        # 지식 증류 저장 및 디스코드 보고
        index.upsert(vectors=[{"id": str(datetime.now().timestamp()), "values": embed, "metadata": {"conclusion": verdict, "date": str(datetime.now())}}])
        
        # 분할 전송 (2,000자 제한 돌파)
        chunks = [verdict[i:i+1800] for i in range(0, len(verdict), 1800)]
        for chunk in chunks:
            requests.post(DISCORD_URL, json={"content": f"🏛️ **Alpha-Trio 2.9 자가학습 보고**\n```json\n{chunk}\n```"})
        
        print("✅ 자가학습 및 보고 완료")
        
    except Exception as e:
        print(f"🔥 에러: {e}")
        sys.exit(1)