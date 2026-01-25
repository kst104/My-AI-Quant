import os
import yfinance as yf
import pandas as pd
import numpy as np
import requests
import google.generativeai as genai
from pinecone import Pinecone
import json
from datetime import datetime
import sys

# [환경 설정]
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")
NEWS_KEY = os.environ.get("NEWS_API_KEY")
PINECONE_KEY = os.environ.get("PINECONE_API_KEY")
DISCORD_URL = os.environ.get("DISCORD_WEBHOOK_URL")

# 로그를 통해 주소 유효성 확인 (주소 끝 5자리만 노출)
if DISCORD_URL:
    print(f"📡 디스코드 연결 시도 중... (URL 끝자리: ...{DISCORD_URL[-5:]})")
else:
    print("❌ 에러: DISCORD_WEBHOOK_URL이 비어있습니다!")
    sys.exit(1)

genai.configure(api_key=GEMINI_KEY)
pc = Pinecone(api_key=PINECONE_KEY)
index = pc.Index("alpha-trio-memory")

def calculate_simple(df):
    close = df['Close']
    delta = close.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=13).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=13).mean()
    df['RSI'] = 100 - (100 / (1 + (gain / loss)))
    return df

def alpha_trio_final():
    print("🧠 제미나이가 시장을 분석 중입니다...")
    df = yf.download("^GSPC", period="60d", progress=False)
    df = calculate_simple(df)
    rsi = round(float(df['RSI'].iloc[-1]), 2)
    
    prompt = f"현재 S&P500 RSI는 {rsi}입니다. 에이전트 A, B, C의 분석을 JSON 형식으로 짧고 굵게 작성하세요."
    response = genai.GenerativeModel('gemini-1.5-pro').generate_content(prompt).text
    return response

if __name__ == "__main__":
    try:
        verdict = alpha_trio_final()
        msg = f"🏛️ **Alpha-Trio 2.5 최종 보고**\n```json\n{verdict}\n```"
        
        print(f"📦 메시지 길이: {len(msg)}자")
        
        # 실제 전송 및 결과 강제 확인
        res = requests.post(DISCORD_URL, json={"content": msg})
        
        if res.status_code == 204:
            print("✅ 디스코드 전송 성공!")
        else:
            print(f"❌ 디스코드 전송 실패! 상태 코드: {res.status_code}")
            print(f"❌ 응답 내용: {res.text}")
            # 전송 실패 시 강제로 에러를 발생시켜 GitHub Actions를 빨간색으로 만듭니다.
            sys.exit(1) 

    except Exception as e:
        print(f"🔥 치명적 에러 발생: {e}")
        sys.exit(1)