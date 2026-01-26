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

# [STAGE 1: 모든 API 인프라 복구 및 정렬]
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")
PINECONE_KEY = os.environ.get("PINECONE_API_KEY")
NEWS_KEY = os.environ.get("NEWS_API_KEY")
DISCORD_URL = os.environ.get("DISCORD_WEBHOOK_URL")
USER_QUESTION = os.environ.get("USER_QUESTION", "").replace("/ask", "").strip()

if not all([GEMINI_KEY, PINECONE_KEY, NEWS_KEY, DISCORD_URL]):
    print("❌ Critical Error: 감독님, 누락된 API 키가 있습니다. Secrets 설정을 확인해주세요.")
    sys.exit(1)

client = genai.Client(api_key=GEMINI_KEY)
pc = Pinecone(api_key=PINECONE_KEY)
index = pc.Index("alpha-trio-memory")
UA_HEADERS = {"User-Agent": "Mozilla/5.0 AlphaTrioBot/V17-Ultimate"}

# ---------------------------------------------------------
# [STAGE 2: 하이퍼-퀀트 엔진]
# ---------------------------------------------------------
def run_temporal_causal_scan():
    """500개 종목의 5년 세월을 훑어 역사적 희소성을 산출합니다."""
    print("🌌 [Step 2] S&P 500 전 종목 5개년 역사를 인과적으로 해부 중...")
    try:
        r = requests.get("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies", timeout=30)
        tickers = pd.read_html(r.text)[0]["Symbol"].replace(".", "-", regex=True).tolist()
        
        data = yf.download(tickers, period="5y", group_by="ticker", progress=False, threads=True)
        
        diagnostic_pool = []
        for t in tickers:
            try:
                sub = data[t].dropna()
                if len(sub) < 500: 
                    continue
                close = sub['Close']
                
                # RSI 및 Z-score 계산
                delta = close.diff()
                gain = delta.where(lambda x: x > 0, 0).rolling(14).mean()
                loss = -delta.where(lambda x: x < 0, 0).rolling(14).mean().replace(0, 1)
                rsi_series = 100 - (100 / (1 + (gain / loss)))
                
                z_score = (rsi_series.iloc[-1] - rsi_series.mean()) / rsi_series.std()
                
                # TDI 및 ATR
                tdi_pl = rsi_series.rolling(2).mean().iloc[-1]
                tdi_mbl = rsi_series.rolling(34).mean().iloc[-1]
                
                atr = (pd.concat([sub['High']-sub['Low'], abs(sub['High']-close.shift()), abs(sub['Low']-close.shift())], axis=1).max(axis=1)).rolling(14).mean()
                atr_ratio = atr.iloc[-1] / atr.mean()

                # Z-score 2.2 이상인 종목 선별
                if abs(z_score) > 2.2:
                    # 중요: 자연어 형식으로 저장
                    diagnostic_pool.append(
                        f"{t}: 현재가 {close.iloc[-1]:.2f}달러, Z-점수 {z_score:.2f} (역사적 이상치), "
                        f"TDI 차이 {tdi_pl - tdi_mbl:.2f}, ATR 비율 {atr_ratio:.2f}"
                    )
            except: 
                continue
            
        # 중요: 리스트를 자연어 문장으로 변환
        return " | ".join(diagnostic_pool[:15]) if diagnostic_pool else "현재 역사적 이상치를 보이는 종목 없음"
    except Exception: 
        return "데이터 스캔 지연"

# [STAGE 3: 명품 개별 배송 엔진]
def deliver_refined_report(agent_id, title, content):
    emoji = {"A": "📉", "B": "💡", "C": "💀"}.get(agent_id, "🏛️")
    msg = f"## {emoji} {title}\n**Alpha-Trio Agent {agent_id} 심층 진단**\n---\n{content.strip()}\n"
    
    # 중요: data= 사용 (json= 사용 금지)
    for i in range(0, len(msg), 1900):
        requests.post(DISCORD_URL, data={"content": msg[i:i+1900]}, timeout=30)
    time.sleep(1.2)

# ---------------------------------------------------------
# [STAGE 4: 메인 루프]
# ---------------------------------------------------------
if __name__ == "__main__":
    try:
        # 1. 5년 역사 스캔
        m_data = run_temporal_causal_scan()
        
        # 2. 뉴스 데이터 수집 (자연어 형식)
        n_res = requests.get(
            f"https://newsapi.org/v2/top-headlines?category=business&language=en&apiKey={NEWS_KEY}"
        ).json()
        n_data = " | ".join([a['title'] for a in n_res.get('articles', [])[:5]])

        # 3. 기억 소환
        embed_res = client.models.embed_content(model="text-embedding-004", contents=m_data)
        vector = embed_res.embeddings[0].values
        past = index.query(vector=vector, top_k=1, include_metadata=True)
        # 중요: 기본값을 자연어로 설정
        memory_note = past.matches[0].metadata.get("conclusion", "이전 분석 기록 없음") if past.matches else "이전 분석 기록 없음"

        # 4. 프롬프트 (JSON 단어 완전 제거)
        prompt = f"""당신은 5년의 주식 데이터를 분석하는 전문가 위원회입니다.

분석할 시장 데이터:
{m_data}

최신 비즈니스 뉴스:
{n_data}

과거 분석 기록:
{memory_note}

사용자 질문:
{USER_QUESTION if USER_QUESTION else '정기 리스크 진단'}

--- 분석 요구사항 ---

에이전트 A (수량적 분석가):
Z-score, TDI, ATR 등 수치를 바탕으로 현재 시장의 수급 상태를 분석하세요. 5년 역사적 맥락에서 현재 상황이 얼마나 특이한지 설명하세요. 굵은 글씨와 불렛 포인트를 사용하세요.

에이전트 B (전략가):
현재 시장 지표와 뉴스를 결합하여 실전 투자 전략을 제시하세요. 과거 유사한 국면과 비교하며 구체적인 매매 방향을 제시하세요.

에이전트 C (리스크 관리자):
과거 분석 기록과 현재 상황을 비교하여 잠재적 위험 요소를 경고하세요. 비판적 관점에서 오늘의 시장에 대한 조언을 작성하세요.

--- 출력 형식 ---

에이전트 A의 분석을 먼저 작성하고, 그 다음에 에이전트 B, 마지막으로 에이전트 C를 작성하세요.

각 에이전트 분석의 시작과 끝을 다음 태그로 표시하세요:
AGENT_A_START (내용) AGENT_A_END
AGENT_B_START (내용) AGENT_B_END  
AGENT_C_START (내용) AGENT_C_END

순수 텍스트와 마크다운 문법만 사용하세요. 코드 블록이나 특수 형식은 사용하지 마세요.
"""

        response = client.models.generate_content(model="gemini-1.5-pro", contents=prompt)
        full_text = response.text

        # 5. 후처리: JSON/코드 블록 제거
        import re
        # 코드 블록 제거
        full_text = re.sub(r'```[\s\S]*?```', '', full_text)
        # JSON 객체 제거 (중괄호로 둘러싸인 내용)
        full_text = re.sub(r'\{[\s\S]*?\}', '', full_text)
        # 남은 백틱 제거
        full_text = full_text.replace('`', '')

        # 6. 에이전트별로 나누어 배송
        agents = {
            "A": ("AGENT_A_START", "AGENT_A_END", "수량적 수급 인과 해부"),
            "B": ("AGENT_B_START", "AGENT_B_END", "역사적 지능 증류"),
            "C": ("AGENT_C_START", "AGENT_C_END", "기억 기반 오답노트")
        }
        
        for key, (start_tag, end_tag, title) in agents.items():
            if start_tag in full_text:
                try:
                    content = full_text.split(start_tag)[1].split(end_tag)[0].strip()
                    if content and len(content) > 10:
                        deliver_refined_report(key, title, content)
                except:
                    continue

        # 7. 자가학습용 저장 (간단한 요약만)
        summary = f"Analysis completed at {datetime.now().strftime('%Y-%m-%d %H:%M')}. Scanned data length: {len(m_data)} characters."
        index.upsert(vectors=[{
            "id": str(datetime.now().timestamp()), 
            "values": vector, 
            "metadata": {"conclusion": summary}
        }])

        print("✅ [V17] 자가학습 및 인과적 보고 완료.")

    except Exception as e:
        print(f"🔥 Critical Failure: {e}")
        traceback.print_exc()