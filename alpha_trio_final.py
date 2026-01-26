import os
import sys
import time
import traceback
from datetime import datetime

import requests
import pandas as pd
import yfinance as yf
from pinecone import Pinecone
from google import genai

# [STAGE 1: 인프라]
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")
PINECONE_KEY = os.environ.get("PINECONE_API_KEY")
NEWS_KEY = os.environ.get("NEWS_API_KEY")
DISCORD_URL = os.environ.get("DISCORD_WEBHOOK_URL")
USER_QUESTION = os.environ.get("USER_QUESTION", "").replace("/ask", "").strip()

if not all([GEMINI_KEY, PINECONE_KEY, NEWS_KEY, DISCORD_URL]):
    print("❌ API 키 누락")
    sys.exit(1)

client = genai.Client(api_key=GEMINI_KEY)
pc = Pinecone(api_key=PINECONE_KEY)
index = pc.Index("alpha-trio-memory")

# ---------------------------------------------------------
# [STAGE 2: 데이터 수집]
# ---------------------------------------------------------
def run_scan():
    print("🌌 S&P 500 스캔 중...")
    try:
        r = requests.get("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies", timeout=30)
        tickers = pd.read_html(r.text)[0]["Symbol"].replace(".", "-", regex=True).tolist()
        data = yf.download(tickers, period="5y", group_by="ticker", progress=False, threads=True)
        
        results = []
        for t in tickers[:50]:  # 상위 50개만 (속도)
            try:
                sub = data[t].dropna()
                if len(sub) < 500: 
                    continue
                close = sub['Close']
                
                delta = close.diff()
                gain = delta.where(lambda x: x > 0, 0).rolling(14).mean()
                loss = -delta.where(lambda x: x < 0, 0).rolling(14).mean().replace(0, 1)
                rsi = 100 - (100 / (1 + (gain / loss)))
                
                z_score = (rsi.iloc[-1] - rsi.mean()) / rsi.std()
                
                if abs(z_score) > 2.0:
                    results.append(f"{t}: RSI {rsi.iloc[-1]:.1f}, Z-score {z_score:.2f}")
            except: 
                continue
                
        return " | ".join(results[:10]) if results else "이상치 없음"
    except: 
        return "스캔 실패"

# ---------------------------------------------------------
# [STAGE 3: 디스코드 전송]
# ---------------------------------------------------------
def send_report(agent_id, title, content):
    emoji = {"A": "📉", "B": "💡", "C": "💀"}.get(agent_id, "🏛️")
    msg = f"## {emoji} {title}\n**Agent {agent_id} 분석**\n---\n{content.strip()}\n"
    
    # data= 사용 (json= 금지)
    for i in range(0, len(msg), 1900):
        requests.post(DISCORD_URL, data={"content": msg[i:i+1900]}, timeout=30)
    time.sleep(1)

# ---------------------------------------------------------
# [STAGE 4: 메인]
# ---------------------------------------------------------
if __name__ == "__main__":
    try:
        # 데이터 수집
        market_data = run_scan()
        
        news_res = requests.get(
            f"https://newsapi.org/v2/top-headlines?category=business&language=en&apiKey={NEWS_KEY}"
        ).json()
        news_data = " | ".join([a['title'] for a in news_res.get('articles', [])[:3]])

        # 기억 소환
        embed_res = client.models.embed_content(model="text-embedding-004", contents=market_data)
        vector = embed_res.embeddings[0].values
        past = index.query(vector=vector, top_k=1, include_metadata=True)
        memory = past.matches[0].metadata.get("text", "없음") if past.matches else "없음"

        # -------------------------------------------------
        # 핵심: 샷 프롬프팅 (예시를 직접 보여줌)
        # -------------------------------------------------
        prompt = f"""다음 데이터를 분석하여 세 명의 전문가가 대화하듯이 작성하세요.

시장 데이터: {market_data}
뉴스: {news_data}
과거 기록: {memory}
질문: {USER_QUESTION if USER_QUESTION else '시장 분석'}

--- 아래 형식을 정확히 따르세요 ---

<<A의 분석 시작>>
여기에 A의 분석을 작성합니다.
- 불렛 포인트 사용
- **굵은 글씨** 사용
- 자연스러운 문장
<<A의 분석 끝>>

<<B의 분석 시작>>
여기에 B의 분석을 작성합니다.
<<B의 분석 끝>>

<<C의 분석 시작>>
여기에 C의 분석을 작성합니다.
<<C의 분석 끝>>

중요: 위 형식 외의 다른 형식(코드, 표, 중괄호 등)은 사용하지 마세요.
"""

        response = client.models.generate_content(model="gemini-1.5-pro", contents=prompt)
        text = response.text

        # -------------------------------------------------
        # 강력한 후처리 (JSON 완전 제거)
        # -------------------------------------------------
        import re
        
        # 1. 코드 블록 제거
        text = re.sub(r'```[\s\S]*?```', '', text)
        text = re.sub(r'`[\s\S]*?`', '', text)
        
        # 2. JSON 객체 제거 (중괄호 내용)
        text = re.sub(r'\{[\s\S]*?\}', '', text)
        
        # 3. JSON 배열 제거 (대괄호 내용)
        text = re.sub(r'\[[\s\S]*?\]', '', text)
        
        # 4. 남은 특수문자 제거
        text = text.replace('"', '').replace("'", "")
        
        # 5. 연속된 공백/줄바꿈 정리
        text = re.sub(r'\n+', '\n', text)
        text = re.sub(r' +', ' ', text)

        # -------------------------------------------------
        # 에이전트별 추출
        # -------------------------------------------------
        agents = {
            "A": ("<<A의 분석 시작>>", "<<A의 분석 끝>>", "수량적 분석"),
            "B": ("<<B의 분석 시작>>", "<<B의 분석 끝>>", "전략 분석"),
            "C": ("<<C의 분석 시작>>", "<<C의 분석 끝>>", "리스크 분석")
        }
        
        for key, (start, end, title) in agents.items():
            if start in text:
                try:
                    content = text.split(start)[1].split(end)[0].strip()
                    if len(content) > 20:  # 의미 있는 내용만
                        send_report(key, title, content)
                except:
                    pass

        # 기억 저장
        summary = f"분석 완료: {datetime.now().strftime('%m-%d %H:%M')}"
        index.upsert(vectors=[{
            "id": str(datetime.now().timestamp()), 
            "values": vector, 
            "metadata": {"text": summary}
        }])

        print("✅ 완료")

    except Exception as e:
        print(f"🔥 오류: {e}")
        traceback.print_exc()