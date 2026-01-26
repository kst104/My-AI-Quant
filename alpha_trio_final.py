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

# [STAGE 1: 인프라 및 환경 정렬]
DISCORD_URL = os.environ.get("DISCORD_WEBHOOK_URL")
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")
PINECONE_KEY = os.environ.get("PINECONE_API_KEY")
NEWS_KEY = os.environ.get("NEWS_API_KEY")
USER_QUESTION = os.environ.get("USER_QUESTION", "").replace("/ask", "").strip()

client = genai.Client(api_key=GEMINI_KEY)
pc = Pinecone(api_key=PINECONE_KEY)
index = pc.Index("alpha-trio-memory")
UA_HEADERS = {"User-Agent": "Mozilla/5.0 AlphaTrioBot/V14-Causal"}

# ---------------------------------------------------------
# [STAGE 2: 시계열 인과관계 엔진 (5-Year Historical Context)]
# ---------------------------------------------------------
def run_causal_diagnosis():
    """
    S&P 500 전 종목의 5년 데이터를 분석하여 단순 수치가 아닌 '역사적 희소성'을 산출합니다.
    """
    print("🌌 [Step 2] 500개 종목의 5개년 역사적 수급 균열 탐색 중...")
    try:
        r = requests.get("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies", timeout=30)
        tickers = pd.read_html(r.text)[0]["Symbol"].replace(".", "-", regex=True).tolist()
        
        # 5년($5y$) 전체 데이터 다운로드
        data = yf.download(tickers, period="5y", group_by="ticker", progress=False, threads=True)
        
        diagnostic_pool = []
        for t in tickers:
            try:
                sub = data[t].dropna()
                if len(sub) < 500: continue
                close = sub['Close']
                
                # 1. 수급 인과관계 ($RSI$ 및 $Z-score$ 계산)
                # $Z_{score} = \frac{x - \mu}{\sigma}$
                delta = close.diff()
                gain = delta.where(lambda x: x>0, 0).rolling(14).mean()
                loss = -delta.where(lambda x: x<0, 0).rolling(14).mean().replace(0, 1)
                rsi_series = 100 - (100 / (1 + (gain / loss)))
                
                curr_rsi = rsi_series.iloc[-1]
                z_score = (curr_rsi - rsi_series.mean()) / rsi_series.std()
                
                # 2. 거래량 및 변동성($ATR$) 연산
                vol_ratio = sub['Volume'].iloc[-1] / sub['Volume'].rolling(20).mean().iloc[-1]
                
                # 역사적 특이점(Z-score 2.0 이상)이 발견된 종목 위주로 에이전트에게 전달
                if abs(z_score) > 2.0:
                    diagnostic_pool.append({
                        "ticker": t, "z_score": round(z_score, 2),
                        "rsi": round(curr_rsi, 1), "vol_ratio": round(vol_ratio, 2),
                        "price": round(close.iloc[-1], 2)
                    })
            except: continue
            
        diagnostic_pool.sort(key=lambda x: abs(x['z_score']), reverse=True)
        return diagnostic_pool[:20] # 상위 20개 특이점 추출
    except Exception as e:
        print(f"🔥 Data Error: {e}")
        return []

# [STAGE 3: 명품 개별 배송 엔진]
def deliver_refined_report(agent_id, title, content):
    """에이전트별로 별도의 메시지를 발송하여 2,000자 제한을 물리적으로 회피합니다."""
    emoji = {"A": "📉", "B": "💡", "C": "💀"}.get(agent_id, "🏛️")
    msg = f"## {emoji} {title}\n**Alpha-Trio Agent {agent_id} 심층 진단**\n---\n{content.strip()}\n"
    
    # 디스코드 전송
    requests.post(DISCORD_URL, json={"content": msg}, timeout=30)
    time.sleep(1.5) # 전송 순서 보장을 위한 지연

# ---------------------------------------------------------
# [STAGE 4: 메인 2중 공정 (Refining Loop)]
# ---------------------------------------------------------
if __name__ == "__main__":
    try:
        m_data = run_causal_diagnosis()
        n_res = requests.get(f"https://newsapi.org/v2/top-headlines?category=business&language=en&apiKey={NEWS_KEY}").json()
        n_data = "\n".join([f"🔥 {a['title']}" for a in n_res.get('articles', [])[:5]])

        # 1. 기억(JSON) 소환
        input_str = json.dumps(m_data)
        embed_res = client.models.embed_content(model="text-embedding-004", contents=input_str)
        vector = embed_res.embeddings[0].values
        past = index.query(vector=vector, top_k=1, include_metadata=True)
        yesterday_memory = past.matches[0].metadata["conclusion"] if past.matches else "{}"

        # 2. 인과관계 진단 프롬프트 (JSON 강제 설정은 없습니다)
        prompt = f"""당신은 5년의 역사적 데이터를 매 순간 공부하며 예측-검증-오답노트를 작성하는 초지능 위원회입니다.
        현시점 특이데이터: {input_str}
        어제의 학습기록(JSON): {yesterday_memory}
        현재 뉴스: {n_data}
        질문: {USER_QUESTION if USER_QUESTION else '정기 자가학습 보고'}

        [분석 명령 - 뭉뚱그린 답변은 폐기됨]
        1. 단순 수치 나열 금지. "왜 이 지표가 역사적 맥락($Z-score$ 등)에서 위험한/좋은 신호인지" 인과관계를 설명하십시오.
        2. [AGENT_A](Quant): 현재 수급의 질을 분석하고, 이것이 과거 어떤 국면(가짜 돌파 vs 진짜 상승)과 닮았는지 진단하십시오.
        3. [AGENT_B](Dewey): 오늘의 뉴스{n_data}와 지표가 결합되었을 때, 과거에 반복되었던 '성공의 공식'을 추출하십시오.
        4. [AGENT_C](Beckett): 어제의 예측({yesterday_memory})과 오늘의 결과를 대조하여 '오답노트'를 작성하십시오. 왜 우리가 틀렸고, 어떤 허점을 놓쳤는지 무자비하게 비판하십시오.

        [공정 가이드라인]
        - 인간용 보고서: [AGENT_A], [AGENT_B], [AGENT_C] 태그를 사용하여 가독성 높은 리포트로 작성. (JSON 금지)
        - 자가학습용 데이터: 모든 분석이 끝난 뒤 마지막에만 [INTERNAL_JSON] 태그 뒤에 기계 학습용 JSON을 첨부.
        """

        # IMPORTANT: 'response_mime_type'을 설정하지 않아 자유로운 리포트 형식을 허용합니다.
        response = client.models.generate_content(model="gemini-1.5-pro", contents=prompt)
        full_text = response.text

        # 3. 인간용 리포트 정제 및 개별 전송
        tags = {"A": "[AGENT_A]", "B": "[AGENT_B]", "C": "[AGENT_C]"}
        titles = {"A": "수량적 수급 인과 해부", "B": "역사적 지능 증류", "C": "기억 기반 오답노트"}
        
        for key, tag in tags.items():
            if tag in full_text:
                content = full_text.split(tag)[1].split("[AGENT")[0].split("[INTERNAL")[0].strip()
                deliver_refined_report(key, titles[key], content)

        # 4. 기계용 JSON 자가학습 (Pinecone 저장)
        if "[INTERNAL_JSON]" in full_text:
            json_part = full_text.split("[INTERNAL_JSON]")[1].strip()
            try:
                json.loads(json_part) # 유효성 검사
                index.upsert(vectors=[{"id": str(datetime.now().timestamp()), "values": vector, "metadata": {"conclusion": json_part}}])
            except: pass

    except Exception as e:
        print(f"🔥 Critical Failure: {e}")