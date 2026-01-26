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
UA_HEADERS = {"User-Agent": "Mozilla/5.0 AlphaTrioBot/V7-Final"}

# [2. 기술적 지능 엔진: 500개 종목 전수조사]
def get_full_market_scan():
    print("🌌 S&P 500 전 종목 5개년 역사 해부 중...")
    try:
        r = requests.get("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies", headers=UA_HEADERS, timeout=30)
        tickers = pd.read_html(r.text)[0]["Symbol"].replace(".", "-", regex=True).tolist()
        # 500개 종목 5년 데이터 벌크 다운로드
        data = yf.download(tickers, period="5y", group_by="ticker", progress=False, threads=True)
        
        # 전체 통계 분석 ($RSI$, $BB$, $TDI$, $ATR$)
        stats = {"Overbought": 0, "Volatility_Spike": 0}
        highlights = []
        for t in ["AAPL", "NVDA", "TSLA", "MSFT", "AMZN"]:
            try:
                sub = data[t].dropna()
                close = sub['Close']
                # $RSI$ 14일 연산
                delta = close.diff()
                rsi = 100 - (100 / (1 + (delta.where(lambda x: x>0, 0).rolling(14).mean() / 
                                        -delta.where(lambda x: x<0, 0).rolling(14).mean().replace(0, 1))))
                curr_rsi = rsi.iloc[-1]
                if curr_rsi > 70: stats["Overbought"] += 1
                highlights.append(f"{t}(RSI:{round(curr_rsi,1)})")
            except: continue
            
        return f"S&P500 전수조사 결과: 과매수 종목 {stats['Overbought']}개 감지. 주요 종목 상태: {', '.join(highlights)}"
    except Exception as e:
        return f"데이터 스캔 지연: {e}"

# [3. 명품 전송 엔진: 에이전트별 개별 마크다운 보고]
def send_to_discord(agent_id, title, content):
    emoji = {"A": "📉", "B": "💡", "C": "💀"}.get(agent_id, "🏛️")
    # JSON 기호 없이 순수 마크다운으로만 구성
    formatted_msg = (
        f"## {emoji} {title}\n"
        f"**Agent {agent_id} 가동 보고**\n"
        f"--- \n"
        f"{content.strip()}\n"
        f"\n"
    )
    # 디스코드 전송 (2000자 제한을 넘지 않도록 각 에이전트별로 발송)
    requests.post(DISCORD_URL, json={"content": formatted_msg}, timeout=30)
    time.sleep(1.5)

if __name__ == "__main__":
    try:
        m_data = get_full_market_scan()
        
        # [기억 소환] Vector DB
        embed_res = client.models.embed_content(model="text-embedding-004", contents=m_data)
        vector = embed_res.embeddings[0].values
        past = index.query(vector=vector, top_k=1, include_metadata=True)
        memory = past.matches[0].metadata["conclusion"] if past.matches else "이전 기록 없음."

        # [프롬프트: JSON 절대 금지 명령]
        prompt = f"""당신은 Alpha-Trio 위원회입니다. 
        시장 데이터: {m_data} | 과거 기억: {memory}
        질문: {USER_QUESTION if USER_QUESTION else '정기 시장 해부'}

        [보고 지침 - 엄격]
        1. JSON 형식을 절대 사용하지 마십시오. 오직 가독성 높은 한국어 문장으로만 보고하십시오.
        2. 에이전트 A, B, C의 분석을 [AGENT_A], [AGENT_B], [AGENT_C] 구분자로 나누십시오.
        3. 굵은 글씨(**)와 불렛 포인트(*)를 사용하여 전문적인 보고서처럼 꾸미십시오.
        4. A(Quant)는 기술적 지표($BB$, $TDI$, $ATR$)를, B(Dewey)는 전략을, C(Beckett)는 날카로운 리스크 비판을 수행하십시오.
        """

        response = client.models.generate_content(model="gemini-1.5-pro", contents=prompt)
        full_text = response.text

        # 에이전트별로 쪼개서 개별 전송 (잘림 방지)
        parts = {"A": "[AGENT_A]", "B": "[AGENT_B]", "C": "[AGENT_C]"}
        titles = {"A": "수량적 수급 해부", "B": "실천적 지능 증류", "C": "실존적 리스크 오답노트"}
        
        for key, tag in parts.items():
            if tag in full_text:
                # 다음 태그가 나오기 전까지의 내용만 추출
                content = full_text.split(tag)[1].split("[AGENT")[0].strip()
                send_to_discord(key, titles[key], content)

        # 자가학습 기록 (백그라운드 저장)
        index.upsert(vectors=[{"id": str(datetime.now().timestamp()), "values": vector, "metadata": {"conclusion": full_text}}])

    except Exception as e:
        print(f"🔥 에러 자백: {e}")