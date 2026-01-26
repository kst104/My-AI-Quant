import os
import sys
import json
import time
import traceback
from datetime import datetime

import requests
import pandas as pd
import yfinance as yf
from pinecone import Pinecone
from google import genai

# [STAGE 1: 인프라 및 환경 변수 정밀 세팅]
# 모든 API 키는 GitHub Secrets에서 안전하게 가져오며, 하나라도 누락 시 즉시 중단합니다.
DISCORD_URL = os.environ.get("DISCORD_WEBHOOK_URL")
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")
PINECONE_KEY = os.environ.get("PINECONE_API_KEY")
NEWS_KEY = os.environ.get("NEWS_API_KEY")
USER_QUESTION = os.environ.get("USER_QUESTION", "").replace("/ask", "").strip()

if not all([DISCORD_URL, GEMINI_KEY, PINECONE_KEY, NEWS_KEY]):
    print("❌ Critical Error: Essential API keys are missing.")
    sys.exit(1)

# 하이엔드 AI 클라이언트 및 메모리(Pinecone) 초기화
client = genai.Client(api_key=GEMINI_KEY)
pc = Pinecone(api_key=PINECONE_KEY)
index = pc.Index("alpha-trio-memory")
UA_HEADERS = {"User-Agent": "Mozilla/5.0 AlphaTrioBot/Ultimate-V11"}

# ---------------------------------------------------------
# [STAGE 2: 하이퍼-퀀트 엔진 (500+ Stocks, 5-Year Deep Scan)]
# ---------------------------------------------------------
def run_quantitative_diagnosis():
    """
    S&P 500 전 종목의 5년 데이터를 훑으며 단순 지표가 아닌 '역사적 희소성'을 계산합니다.
    """
    print("🌌 [Step 2.1] S&P 500 티커 목록 확보 중...")
    try:
        r = requests.get("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies", timeout=30)
        tickers = pd.read_html(r.text)[0]["Symbol"].replace(".", "-", regex=True).tolist()
        
        print(f"🌌 [Step 2.2] {len(tickers)}개 종목의 5개년($5y$) 데이터 벌크 다운로드 시작...")
        # 고성능 병렬 다운로드 (Threads=True)
        raw_data = yf.download(tickers, period="5y", group_by="ticker", progress=False, threads=True)
        
        stats_db = []
        # 감독님이 말씀하신 '매분 매초의 공부'를 위해 핵심 리딩주 및 변동성 상위주를 정밀 해부합니다.
        for ticker in tickers:
            try:
                df = raw_data[ticker].dropna()
                if len(df) < 250: continue # 데이터 부족 종목 제외
                
                close = df['Close']
                # 1. RSI 정밀 연산 ($RSI = 100 - \frac{100}{1 + RS}$)
                delta = close.diff()
                gain = delta.where(delta > 0, 0).rolling(14).mean()
                loss = -delta.where(delta < 0, 0).rolling(14).mean().replace(0, 1)
                rsi_series = 100 - (100 / (1 + (gain / loss)))
                
                # 2. TDI (Traders Dynamic Index) 복구
                # $TDI_{PL} = SMA(RSI, 2)$ / $TDI_{MBL} = SMA(RSI, 34)$
                tdi_pl = rsi_series.rolling(2).mean()
                tdi_mbl = rsi_series.rolling(34).mean()
                
                # 3. 역사적 희소성 ($Z-score$) 분석
                # 현재 RSI가 지난 5년의 분포 중 어디에 위치하는지 계산
                mean_rsi = rsi_series.mean()
                std_rsi = rsi_series.std()
                z_score = (rsi_series.iloc[-1] - mean_rsi) / std_rsi if std_rsi != 0 else 0
                
                # 4. 볼린저 밴드 ($BB$) 및 변동성 ($ATR$)
                ma20 = close.rolling(20).mean()
                std20 = close.rolling(20).std()
                bbu = ma20 + (std20 * 2)
                atr = (pd.concat([df['High']-df['Low'], abs(df['High']-close.shift()), abs(df['Low']-close.shift())], axis=1).max(axis=1)).rolling(14).mean()

                # 특이점 감지 (Z-score 2.0 이상 혹은 BB 상단 돌파)
                if abs(z_score) > 2.0 or close.iloc[-1] > bbu.iloc[-1]:
                    stats_db.append({
                        "ticker": ticker,
                        "price": round(close.iloc[-1], 2),
                        "z_score": round(z_score, 2),
                        "tdi_diff": round(tdi_pl.iloc[-1] - tdi_mbl.iloc[-1], 2),
                        "atr_ratio": round(atr.iloc[-1] / atr.mean(), 2)
                    })
            except: continue
            
        # 데이터가 너무 방대하면 AI의 컨텍스트를 초과하므로 최상위 특이점 15개로 압축
        stats_db.sort(key=lambda x: abs(x['z_score']), reverse=True)
        return stats_db[:15]
    except Exception as e:
        print(f"🔥 Step 2 Error: {e}")
        return []

# ---------------------------------------------------------
# [STAGE 3: 지능형 보고 및 자가학습 루프]
# ---------------------------------------------------------
def deliver_ultimate_report(agent_id, title, content):
    """감독님이 만족하셨던 명품 마크다운 가독성을 에이전트별로 개별 전송합니다."""
    emoji = {"A": "📉", "B": "💡", "C": "💀"}.get(agent_id, "🏛️")
    msg = f"## {emoji} {title}\n**Alpha-Trio {agent_id} 시계열 심층 분석**\n---\n{content.strip()}\n"
    # 글자수 제한(2000자)을 넘지 않도록 안전하게 분할 전송
    for i in range(0, len(msg), 1900):
        requests.post(DISCORD_URL, json={"content": msg[i:i+1900]}, timeout=30)
    time.sleep(1.2)

if __name__ == "__main__":
    try:
        print("🚀 [Step 1] Alpha-Trio V11 엔진 점화...")
        # 1. 시장 인과관계 데이터 수집
        market_stats = run_quantitative_diagnosis()
        n_res = requests.get(f"https://newsapi.org/v2/top-headlines?category=business&language=en&apiKey={NEWS_KEY}").json()
        n_data = "\n".join([f"🔥 {a['title']}" for a in n_res.get('articles', [])[:5]])

        # 2. 기억 소환 (Pinecone Vector DB)
        # 오늘의 시장 데이터를 벡터화하여 어제의 오답노트를 찾아냅니다.
        input_str = json.dumps(market_stats)
        embed_res = client.models.embed_content(model="text-embedding-004", contents=input_str)
        vector = embed_res.embeddings[0].values
        past_query = index.query(vector=vector, top_k=1, include_metadata=True)
        memory_note = past_query.matches[0].metadata["conclusion"] if past_query.matches else "이전 학습 데이터 없음."

        # 3. 3인 위원회 '끝장 토론' 소환 (Hyper-Detailed Prompt)
        # 감독님이 말씀하신 '왜?'에 대한 인과적 해답을 강제합니다.
        prompt = f"""당신은 5년의 데이터를 매 순간 분석하며 예측-검증-오답노트를 반복하는 초지능 위원회입니다.
        [Current Market Stats]: {input_str}
        [Market News]: {n_data}
        [Previous Error Note]: {memory_note}
        [User Interrogation]: {USER_QUESTION if USER_QUESTION else '정기 자가학습 보고'}

        [분석 가이드라인 - 뭉뚱그린 답변은 즉시 폐기됨]
        1. A(Quant): 수치 뒤에 숨은 수급의 질을 역사적 분포($Z-score$)로 해부하고, 현재의 지표가 왜 '좋은 신호가 아닌지' 인과적으로 증명하라.
        2. B(Dewey): 현재 뉴스와 지표의 결합이 과거 5년 중 어떤 역사적 국면과 90% 이상 일치하는지 찾아내고, 실천적 전략을 증류하라.
        3. C(Beckett): 어제의 오답노트({memory_note})를 소환하라. 우리의 예측이 왜 빗나갔는지, 인간의 낙관이 데이터를 어떻게 오염시켰는지 무자비하게 비판하라.

        [Output 공정]
        - 인간용 리포트: [AGENT_A], [AGENT_B], [AGENT_C] 태그로 나누어 줄글과 마크다운으로 작성.
        - 자가학습용 데이터: [INTERNAL_JSON] 태그 뒤에 수치 기반의 미래 예측치를 JSON으로 남길 것.
        """

        response = client.models.generate_content(model="gemini-1.5-pro", contents=prompt)
        full_text = response.text

        # 4. 명품 배달 및 자가학습 기록
        tags = {"A": "[AGENT_A]", "B": "[AGENT_B]", "C": "[AGENT_C]"}
        titles = {"A": "수량적 수급 인과 분석", "B": "역사적 지능 증류", "C": "기억 기반 오답노트"}
        
        for key, tag in tags.items():
            if tag in full_text:
                content = full_text.split(tag)[1].split("[AGENT")[0].split("[INTERNAL")[0].strip()
                deliver_ultimate_report(key, titles[key], content)

        if "[INTERNAL_JSON]" in full_text:
            json_part = full_text.split("[INTERNAL_JSON]")[1].strip()
            index.upsert(vectors=[{"id": str(datetime.now().timestamp()), "values": vector, "metadata": {"conclusion": json_part}}])

        print("✅ [Step 4] 시계열 자가학습 루프 완결.")

    except Exception as e:
        print(f"🔥 Critical Failure: {e}")
        traceback.print_exc()