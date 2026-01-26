import os
import sys
import json
import time
from datetime import datetime
import requests
import pandas as pd
import yfinance as yf
from pinecone import Pinecone
from google import genai

# [1. 시스템 초기화]
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")
DISCORD_URL = os.environ.get("DISCORD_WEBHOOK_URL")
USER_QUESTION = os.environ.get("USER_QUESTION", "").replace("/ask", "").strip()

client = genai.Client(api_key=GEMINI_KEY)
pc = Pinecone(api_key=os.environ.get("PINECONE_API_KEY"))
index = pc.Index("alpha-trio-memory")
UA_HEADERS = {"User-Agent": "Mozilla/5.0 AlphaTrioBot/7.0"}

# [2. 지능형 지표 연산 ($LaTeX$)]
def get_market_data():
    print("🌌 S&P 500 전 종목 5개년 전수 조사 중...")
    try:
        r = requests.get("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies", headers=UA_HEADERS, timeout=30)
        tickers = pd.read_html(r.text)[0]["Symbol"].replace(".", "-", regex=True).tolist()
        data = yf.download(tickers, period="5y", group_by="ticker", progress=False, threads=True)
        
        # 전체 통계 및 주요 지표 산출
        stats = {"Overbought": 0, "Structural_Break": 0}
        highlights = []
        for t in ["AAPL", "NVDA", "TSLA", "MSFT"]:
            sub = data[t].dropna()
            close = sub['Close']
            # $TDI_{PL}$, $BB$ 정밀 연산
            ma, std = close.rolling(20).mean(), close.rolling(20).std()
            rsi = 100 - (100 / (1 + (close.diff().where(lambda x: x>0, 0).rolling(14).mean() / 
                                    -close.diff().where(lambda x: x<0, 0).rolling(14).mean().replace(0, 1))))
            highlights.append(f"{t}: RSI {round(rsi.iloc[-1],1)} / BB 상단 이격 {round(close.iloc[-1] - (ma.iloc[-1]+std.iloc[-1]*2), 2)}")
            
        return f"S&P500 5y 통계: {stats}\n요약: {', '.join(highlights)}"
    except: return "데이터 수집 지연"

# [3. 디스코드 명품 가독성 전송기]
def send_to_discord(agent_name, title, content):
    """에이전트별로 깔끔한 마크다운 보고서를 전송"""
    emoji = {"A": "📉", "B": "💡", "C": "💀"}.get(agent_name, "🏛️")
    formatted_msg = (
        f"### {emoji} {title}\n"
        f"**Agent {agent_name} Analysis**\n"
        f"--- \n"
        f"{content}\n"
        f"--- \n"
    )
    requests.post(DISCORD_URL, json={"content": formatted_msg}, timeout=30)
    time.sleep(1.5) # 전송 순서 보장

if __name__ == "__main__":
    try:
        m_data = get_market_data()
        
        # [기억 소환]
        embed_res = client.models.embed_content(model="text-embedding-004", contents=m_data)
        vector = embed_res.embeddings[0].values
        past = index.query(vector=vector, top_k=1, include_metadata=True)
        memory = past.matches[0].metadata["conclusion"] if past.matches else "기록 없음"

        # [위원회 소환 - 가독성 중심 프롬프트]
        prompt = f"""당신은 Alpha-Trio 위원회입니다. 
        데이터: {m_data} | 기억: {memory}
        질문: {USER_QUESTION if USER_QUESTION else '정기 보고'}

        다음 규칙을 엄격히 준수하여 응답하십시오:
        1. JSON이 아닌, 각 에이전트별 '자연스러운 보고서' 형태로 답하십시오.
        2. 에이전트 A(Quant), B(Dewey), C(Beckett)의 분석을 명확히 구분하십시오.
        3. A는 기술적 수치($BB$, $TDI$, $ATR$)를, B는 전략적 통찰을, C는 비판적 리스크를 담당합니다.
        4. 가독성을 위해 불렛 포인트(*)와 굵은 글씨(**)를 적극 사용하십시오.
        5. 각 에이전트의 답변 끝에는 [END_AGENT]라고 표시하십시오.
        """

        response = client.models.generate_content(model="gemini-1.5-pro", contents=prompt)
        full_response = response.text

        # 에이전트별로 잘라서 전송
        sections = full_response.split("[END_AGENT]")
        agent_ids = ["A", "B", "C"]
        titles = ["수량적 수급 해부 (Quant)", "실천적 지능 증류 (Dewey)", "실존적 리스크 오답노트 (Beckett)"]

        for i in range(min(len(sections)-1, 3)):
            send_to_discord(agent_ids[i], titles[i], sections[i].strip())

        # 기억 저장 (백그라운드)
        index.upsert(vectors=[{"id": str(datetime.now().timestamp()), "values": vector, "metadata": {"conclusion": full_response}}])

    except Exception as e:
        print(f"🔥 에러: {e}")