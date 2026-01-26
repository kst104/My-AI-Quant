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

# [STAGE 1: 인프라 정밀 세팅]
DISCORD_URL = os.environ.get("DISCORD_WEBHOOK_URL")
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")
PINECONE_KEY = os.environ.get("PINECONE_API_KEY")
NEWS_KEY = os.environ.get("NEWS_API_KEY")
USER_QUESTION = os.environ.get("USER_QUESTION", "").replace("/ask", "").strip()

client = genai.Client(api_key=GEMINI_KEY)
pc = Pinecone(api_key=PINECONE_KEY)
index = pc.Index("alpha-trio-memory")
UA_HEADERS = {"User-Agent": "Mozilla/5.0 AlphaTrioBot/V12-Final"}

# ---------------------------------------------------------
# [STAGE 2: 시계열 인과관계 엔진 (5-Year Causal Scan)]
# ---------------------------------------------------------
def run_temporal_scan():
    """500개 종목의 5년 데이터를 훑으며 단순 수치가 아닌 '희소성'을 계산합니다."""
    try:
        r = requests.get("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies", timeout=30)
        tickers = pd.read_html(r.text)[0]["Symbol"].replace(".", "-", regex=True).tolist()
        
        # 5년치($5y$) 벌크 데이터 (1250영업일 분량)
        raw_data = yf.download(tickers, period="5y", group_by="ticker", progress=False, threads=True)
        
        diagnostic_pool = []
        for t in tickers:
            try:
                df = raw_data[t].dropna()
                if len(df) < 500: continue
                close = df['Close']
                
                # 역사적 희소성 분석 ($Z-score$)
                # $RSI = 100 - \frac{100}{1 + RS}$
                delta = close.diff()
                gain = delta.where(lambda x: x>0, 0).rolling(14).mean()
                loss = -delta.where(lambda x: x<0, 0).rolling(14).mean().replace(0, 1)
                rsi_series = 100 - (100 / (1 + (gain / loss)))
                
                curr_rsi = rsi_series.iloc[-1]
                z_score = (curr_rsi - rsi_series.mean()) / rsi_series.std()
                
                # 변동성($ATR$)과 볼린저 밴드($BB$) 위치
                ma20 = close.rolling(20).mean()
                std20 = close.rolling(20).std()
                bbu = ma20 + (std20 * 2)
                
                if abs(z_score) > 2.2 or close.iloc[-1] > bbu.iloc[-1]:
                    diagnostic_pool.append({
                        "ticker": t, "price": round(close.iloc[-1], 2),
                        "z_score": round(z_score, 2), "rsi": round(curr_rsi, 1)
                    })
            except: continue
            
        diagnostic_pool.sort(key=lambda x: abs(x['z_score']), reverse=True)
        return diagnostic_pool[:15]
    except Exception: return []

# [STAGE 3: 명품 가독성 배송 엔진]
def deliver_refined_report(agent_id, title, content):
    emoji = {"A": "📉", "B": "💡", "C": "💀"}.get(agent_id, "🏛️")
    # 사람이 읽는 가독성 높은 마크다운 리포트 구성
    report = (
        f"## {emoji} {title}\n"
        f"**Alpha-Trio Agent {agent_id} 심층 진단**\n"
        f"--- \n"
        f"{content.strip()}\n"
    )
    requests.post(DISCORD_URL, json={"content": report}, timeout=30)
    time.sleep(1.2)

# ---------------------------------------------------------
# [STAGE 4: 메인 루프 (공정 분리 로직)]
# ---------------------------------------------------------
if __name__ == "__main__":
    try:
        m_data = run_temporal_scan()
        n_res = requests.get(f"https://newsapi.org/v2/top-headlines?category=business&language=en&apiKey={NEWS_KEY}").json()
        n_data = "\n".join([f"🔥 {a['title']}" for a in n_res.get('articles', [])[:5]])

        # 1. 기억 소환
        input_str = json.dumps(m_data)
        embed_res = client.models.embed_content(model="text-embedding-004", contents=input_str)
        vector = embed_res.embeddings[0].values
        past = index.query(vector=vector, top_k=1, include_metadata=True)
        yesterday_note = past.matches[0].metadata["conclusion"] if past.matches else "{}"

        # 2. 2중 공정 프롬프트 (JSON 강제 설정 해제)
        prompt = f"""당신은 5년의 데이터를 매 순간 분석하며 예측-검증-오답노트를 작성하는 위원회입니다.
        데이터: {input_str} | 뉴스: {n_data} | 기억: {yesterday_note}
        질문: {USER_QUESTION if USER_QUESTION else '정기 리스크 진단'}

        [필수 지침: 공정 분리]
        - 절대로 답변 전체를 JSON으로 감싸지 마십시오.
        - [AGENT_A], [AGENT_B], [AGENT_C] 태그를 사용하여 가독성 높은 보고서를 작성하십시오.
        - 수치 나열은 지양하고, "왜 이 지표가 역사적 맥락에서 위험한/좋은 신호인지" 인과관계를 설명하십시오.
        - 마지막에 [INTERNAL_JSON] 태그 뒤에만 기계 학습용 데이터를 JSON으로 첨부하십시오.
        """

        # IMPORTANT: 'response_mime_type'을 설정하지 않아 자유로운 텍스트 출력을 허용합니다.
        response = client.models.generate_content(model="gemini-1.5-pro", contents=prompt)
        full_text = response.text

        # 3. 인간용 리포트 정제 및 전송
        tags = {"A": "[AGENT_A]", "B": "[AGENT_B]", "C": "[AGENT_C]"}
        titles = {"A": "수량적 수급 인과 분석", "B": "역사적 전략 증류", "C": "기억 기반 오답노트"}
        
        for key, tag in tags.items():
            if tag in full_text:
                # 다음 에이전트 태그나 내부 JSON 태그 전까지의 내용을 추출
                content = full_text.split(tag)[1].split("[AGENT")[0].split("[INTERNAL")[0].strip()
                deliver_refined_report(key, titles[key], content)

        # 4. 기계용 JSON 자가학습 (Pinecone 저장)
        if "[INTERNAL_JSON]" in full_text:
            json_part = full_text.split("[INTERNAL_JSON]")[1].strip()
            # JSON 유효성 검사 후 저장
            try:
                json.loads(json_part)
                index.upsert(vectors=[{"id": str(datetime.now().timestamp()), "values": vector, "metadata": {"conclusion": json_part}}])
            except: pass

    except Exception as e:
        print(f"🔥 Critical Failure: {e}")