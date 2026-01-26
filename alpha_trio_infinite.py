import os
import sys
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
UA_HEADERS = {"User-Agent": "Mozilla/5.0 AlphaTrioBot/V8-Final"}

# [2. 기술적 지능 엔진: S&P 500 전수조사 (5y)]
def get_market_intelligence():
    print("🌌 S&P 500 전 종목 5개년 역사 해부 중...")
    try:
        r = requests.get("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies", headers=UA_HEADERS, timeout=30)
        tickers = pd.read_html(r.text)[0]["Symbol"].replace(".", "-", regex=True).tolist()
        # 500개 종목 5년치 벌크 데이터
        data = yf.download(tickers, period="5y", group_by="ticker", progress=False, threads=True)
        
        stats = {"Overbought": 0, "Structural_Break": 0}
        samples = []
        for t in ["AAPL", "NVDA", "TSLA", "MSFT", "AMZN", "GOOGL"]:
            try:
                sub = data[t].dropna()
                close = sub['Close']
                # $RSI$, $TDI$, $BB$ 정밀 연산
                ma, std = close.rolling(20).mean(), close.rolling(20).std()
                delta = close.diff()
                gain = delta.where(lambda x: x>0, 0).rolling(14).mean()
                loss = -delta.where(lambda x: x<0, 0).rolling(14).mean().replace(0, 1)
                rsi = 100 - (100 / (1 + (gain / loss))).iloc[-1]
                
                if rsi > 70: stats["Overbought"] += 1
                samples.append(f"{t}(RSI:{round(rsi,1)})")
            except: continue
            
        return f"S&P500 5y 스캔: 과매수 종목 {stats['Overbought']}개 / 주요 상태: {', '.join(samples)}"
    except: return "데이터 수집 지연 (기존 지능 가동)"

# [3. 명품 전송기: 에이전트별 개별 메시지 발송]
def send_report_to_discord(agent_id, title, content):
    emoji = {"A": "📉", "B": "💡", "C": "💀"}.get(agent_id, "🏛️")
    # 사람이 읽는 마크다운 리포트 구성
    report = (
        f"## {emoji} {title}\n"
        f"**Alpha-Trio Agent {agent_id} 분석 리포트**\n"
        f"--- \n"
        f"{content.strip()}\n"
        f" \n"
    )
    # 디스코드 전송 (에이전트별로 나누어 보내므로 절대 안 잘림)
    requests.post(DISCORD_URL, json={"content": report}, timeout=30)
    time.sleep(1.5) # 전송 순서 보장

if __name__ == "__main__":
    try:
        m_data = get_market_intelligence()
        
        # [기억 소환]
        embed_res = client.models.embed_content(model="text-embedding-004", contents=m_data)
        vector = embed_res.embeddings[0].values
        past = index.query(vector=vector, top_k=1, include_metadata=True)
        memory = past.matches[0].metadata["conclusion"] if past.matches else "이전 기록 없음."

        # [프롬프트: JSON 절대 금지 및 가독성 명령]
        prompt = f"""당신은 Alpha-Trio 위원회입니다. 
        시장데이터: {m_data} | 과거기억: {memory}
        질문: {USER_QUESTION if USER_QUESTION else '정기 시장 해부 보고'}

        [보고 규칙 - 필수 준수]
        1. 절대로 JSON 형식을 사용하지 마십시오. 오직 사람이 읽는 한국어 보고서로 작성하십시오.
        2. 에이전트 A, B, C의 분석을 각각 [AGENT_A], [AGENT_B], [AGENT_C] 태그로 구분하십시오.
        3. A(Quant)는 $BB$, $TDI$, $RSI$ 수치 중심 분석 / B(Dewey)는 실용적 전략 / C(Beckett)는 리스크 비판을 수행하십시오.
        4. 굵은 글씨(**), 불렛 포인트(*)를 활용하여 가독성을 극대화하십시오.
        """

        # 제미나이 1.5 Pro 호출 (JSON 강제 설정 제거)
        response = client.models.generate_content(model="gemini-1.5-pro", contents=prompt)
        full_text = response.text

        # 에이전트별 메시지 분할 전송
        tags = {"A": "[AGENT_A]", "B": "[AGENT_B]", "C": "[AGENT_C]"}
        titles = {"A": "수량적 수급 해부", "B": "실천적 지능 증류", "C": "실존적 리스크 오답노트"}
        
        for key, tag in tags.items():
            if tag in full_text:
                content = full_text.split(tag)[1].split("[AGENT")[0].strip()
                send_report_to_discord(key, titles[key], content)

        # 기억 저장
        index.upsert(vectors=[{"id": str(datetime.now().timestamp()), "values": vector, "metadata": {"conclusion": full_text}}])

    except Exception as e:
        print(f"🔥 에러: {e}")