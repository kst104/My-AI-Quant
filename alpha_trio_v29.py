import os
import yfinance as yf
import pandas as pd
import numpy as np
import requests
import google.generativeai as genai
from pinecone import Pinecone
from datetime import datetime
import sys

# [1. 시스템 초기화]
DISCORD_URL = os.environ.get("DISCORD_WEBHOOK_URL")
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")
PINECONE_KEY = os.environ.get("PINECONE_API_KEY")

if not DISCORD_URL:
    print("❌ 에러: DISCORD_WEBHOOK_URL이 감지되지 않습니다.")
    sys.exit(1)

genai.configure(api_key=GEMINI_KEY)
pc = Pinecone(api_key=PINECONE_KEY)
index = pc.Index("alpha-trio-memory")

def get_market_intelligence():
    """시차와 휴장을 무시하고 가장 최근의 유효 데이터를 가져오는 로직"""
    targets = ["^GSPC", "^IXIC", "NVDA", "SOXX", "BTC-USD"]
    data_lines = []
    
    print(f"📡 {len(targets)}개 종목의 '최근 유효 데이터' 스캔 중...")
    
    for t in targets:
        try:
            # period를 7일로 늘려 주말이나 시차 문제를 완전히 회피합니다.
            df = yf.download(t, period="7d", progress=False)
            if df.empty or len(df) < 2: continue
            
            # 결측치 제거 후 가장 마지막 유효 데이터 선택
            df = df.dropna()
            last_row = df.iloc[-1]
            prev_row = df.iloc[-2]
            
            price = round(float(last_row['Close']), 2)
            change = round(((price - float(prev_row['Close'])) / float(prev_row['Close'])) * 100, 2)
            
            # RSI 계산 (지능형 지표)
            delta = df['Close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
            rsi = 100 - (100 / (1 + (gain / loss))).iloc[-1]
            
            data_lines.append(f"[{t}] P:{price} ({change}%) | RSI:{round(float(rsi), 1)}")
        except Exception as e:
            print(f"⚠️ {t} 데이터 스캔 실패: {e}")
            continue
            
    final_data = "\n".join(data_lines)
    
    # [강력한 가드레일] 만약 수집된 데이터가 전혀 없다면?
    if not final_data:
        return "현재 시장 데이터 스트리밍 지연 중. 매크로 추세(금리, 지정학 리스크)를 기반으로 분석을 진행하라."
    return final_data

if __name__ == "__main__":
    print("🚀 Alpha-Trio 3.1 자가학습 루프 시동...")
    try:
        # [STEP 1] 데이터 확보 (빈 종이가 될 수 없게 설계됨)
        market_data = get_market_intelligence()
        print(f"📊 분석 대상 데이터:\n{market_data}")

        # [STEP 2] 임베딩 및 기억 소환
        embed = genai.embed_content(model="models/text-embedding-004", content=market_data)['embedding']
        past = index.query(vector=embed, top_k=1, include_metadata=True)
        memory = past['matches'][0]['metadata']['conclusion'] if past['matches'] else "신규 시장 패턴 분석 시작."

        # [STEP 3] 제미나이 위원회 가동
        model = genai.GenerativeModel('gemini-1.5-pro')
        
        # 질문지가 절대로 비어있지 않도록 강제 구조화
        prompt = f"""당신은 지능형 투자 에이전트 Alpha-Trio입니다.
        데이터가 비어있다면 현재 시장의 불확실성에 대해 논하십시오.

        [어제의 가설]: {memory}
        [오늘의 시장 데이터]: 
        {market_data}

        미션:
        1. 에이전트 A(Quant): 지표의 괴리를 수치로 비판하라.
        2. 에이전트 B(Dewey): 현재 상황에서 도출할 수 있는 철학적 지식을 증류하라.
        3. 에이전트 C(Beckett): 모든 낙관을 버리고 파멸적인 시나리오를 설계하라.

        결과를 JSON 형식으로 작성하고 'Action'(매수/매도/관망)을 반드시 포함하십시오."""
        
        response = model.generate_content(prompt)
        verdict = response.text

        # [STEP 4] 지식 저장 및 보고
        index.upsert(vectors=[{"id": str(datetime.now().timestamp()), "values": embed, "metadata": {"conclusion": verdict, "date": str(datetime.now())}}])
        
        # 분할 전송
        chunks = [verdict[i:i+1800] for i in range(0, len(verdict), 1800)]
        for chunk in chunks:
            requests.post(DISCORD_URL, json={"content": f"🏛️ **Alpha-Trio 3.1 자가학습 보고**\n```json\n{chunk}\n```"})
        
        print("✅ 루프 완료 및 전송 성공")

    except Exception as e:
        print(f"🔥 치명적 에러: {e}")
        sys.exit(1)