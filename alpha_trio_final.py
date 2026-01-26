import os
import re
import json
import time
import traceback
from datetime import datetime

import requests
import pandas as pd
import yfinance as yf
from openai import OpenAI
from pinecone import Pinecone
from google import genai

# ---------------------------------------------------------
# [STAGE 1: 모든 API 인프라 및 핵심 파라미터 정밀 세팅]
# ---------------------------------------------------------
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")
OPENAI_KEY = os.environ.get("OPENAI_API_KEY")
KIMI_KEY = os.environ.get("KIMI_API_KEY")       # Moonshot AI Key
PINECONE_KEY = os.environ.get("PINECONE_API_KEY")
NEWS_KEY = os.environ.get("NEWS_API_KEY")
DISCORD_URL = os.environ.get("DISCORD_WEBHOOK_URL")
USER_QUESTION = os.environ.get("USER_QUESTION", "").replace("/ask", "").strip()

# 하이엔드 멀티-브레인 클라이언트 초기화
client_gemini = genai.Client(api_key=GEMINI_KEY)
client_gpt = OpenAI(api_key=OPENAI_KEY)
client_kimi = OpenAI(api_key=KIMI_KEY, base_url="https://api.moonshot.cn/v1")
pc = Pinecone(api_key=PINECONE_KEY)
index = pc.Index("alpha-trio-memory")

UA_HEADERS = {"User-Agent": "Mozilla/5.0 AlphaTrioBot/V21-Ultimate"}

# ---------------------------------------------------------
# [STAGE 2: 하이퍼-퀀트 엔진 (5-Year Causal Diagnosis)]
# ---------------------------------------------------------
def run_temporal_causal_scan():
    """
    S&P 500 전 종목의 5년 데이터를 훑으며 단순 수치가 아닌 '역사적 희소성'을 산출합니다.
    """
    print("🌌 [Step 2.1] S&P 500 전 종목 리스트 및 5년 데이터 확보 중...")
    try:
        r = requests.get("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies", timeout=30)
        tickers = pd.read_html(r.text)[0]["Symbol"].replace(".", "-", regex=True).tolist()
        
        # 5년치($5y$) 벌크 다운로드 (매일의 역사적 맥락 확보)
        data = yf.download(tickers, period="5y", group_by="ticker", progress=False, threads=True)
        
        diagnostic_pool = []
        for t in tickers:
            try:
                sub = data[t].dropna()
                if len(sub) < 500: continue
                close = sub['Close']
                
                # 2.2 수급 인과관계 ($RSI$ 및 $Z-score$)
                # $Z_{score} = \frac{Current - \mu}{\sigma}$ (5년 전체 분포 대비 현재 위치)
                delta = close.diff()
                gain = delta.where(lambda x: x>0, 0).rolling(14).mean()
                loss = -delta.where(lambda x: x<0, 0).rolling(14).mean().replace(0, 1)
                rsi_s = 100 - (100 / (1 + (gain / loss)))
                z_score = (rsi_s.iloc[-1] - rsi_s.mean()) / rsi_s.std()
                
                # 2.3 TDI (Traders Dynamic Index) 및 변동성($ATR$) 왜곡
                tdi_pl = rsi_s.rolling(2).mean().iloc[-1]
                tdi_mbl = rsi_s.rolling(34).mean().iloc[-1]
                atr = (pd.concat([sub['High']-sub['Low'], abs(sub['High']-close.shift()), abs(sub['Low']-close.shift())], axis=1).max(axis=1)).rolling(14).mean()
                atr_ratio = atr.iloc[-1] / atr.mean()

                # 역사적 임계점(Z-score 2.3 이상) 발견 시 수집
                if abs(z_score) > 2.3:
                    diagnostic_pool.append({
                        "ticker": t, "z_score": round(z_score, 2),
                        "tdi_gap": round(tdi_pl - tdi_mbl, 2), "atr_vol": round(atr_ratio, 2)
                    })
            except: continue
            
        diagnostic_pool.sort(key=lambda x: abs(x['z_score']), reverse=True)
        return diagnostic_pool[:15]
    except Exception as e:
        print(f"🔥 Step 2 Error: {e}")
        return []

# ---------------------------------------------------------
# [STAGE 3: 명품 개별 배송 & JSON 망령 퇴치 (Ghost-Buster)]
# ---------------------------------------------------------
def deliver_refined_report(agent_id, model_name, title, content):
    """물리적 검열: 만약 AI가 JSON 파편을 섞었다면 이를 제거하고 순수 텍스트만 전송합니다."""
    # 정규표현식으로 { } 및 [ ] 기계 언어 강제 삭제
    clean_text = re.sub(r'\{.*\}', '', content, flags=re.DOTALL)
    clean_text = re.sub(r'\[.*\]', '', clean_text, flags=re.DOTALL).strip()
    
    emoji = {"A": "📉", "B": "💡", "C": "💀"}.get(agent_id, "🏛️")
    msg = f"## {emoji} {title}\n**Agent {agent_id} ({model_name}) 심층 리포트**\n---\n{clean_text}\n"
    
    # 2000자 제한 방지 및 개별 전송
    for i in range(0, len(msg), 1900):
        requests.post(DISCORD_URL, json={"content": msg[i:i+1900]}, timeout=30)
    time.sleep(1.5)

# ---------------------------------------------------------
# [STAGE 4: 메인 융합 루프 (The Multi-Brain Loop)]
# ---------------------------------------------------------
if __name__ == "__main__":
    try:
        print("🚀 [Step 1] Alpha-Trio V21 엔진 점화...")
        # 1. 5년 시계열 인과관계 데이터 및 뉴스 수집
        m_stats = run_temporal_causal_scan()
        n_res = requests.get(f"https://newsapi.org/v2/top-headlines?category=business&language=en&apiKey={NEWS_KEY}").json()
        n_data = "\n".join([f"🔥 {a['title']}" for a in n_res.get('articles', [])[:5]])

        # 2. 기억(JSON) 소환 (Pinecone)
        input_str = json.dumps(m_stats)
        embed_res = client_gemini.models.embed_content(model="text-embedding-004", contents=input_str)
        vector = embed_res.embeddings[0].values
        past = index.query(vector=vector, top_k=1, include_metadata=True)
        memory_note = past.matches[0].metadata["conclusion"] if past.matches else "{}"

        # ---------------------------------------------------------
        # [STEP 3] 연쇄적 멀티 모델 추론 (공정 분리)
        # ---------------------------------------------------------
        
        # 3.1 Agent A: Gemini 1.5 Pro (수량적 인과 해부)
        # 500개 종목의 방대한 컨텍스트를 가장 잘 처리합니다.
        prompt_a = f"""너는 500개 종목의 5년 데이터를 학습하는 퀀트다.
        데이터: {input_str} | 뉴스: {n_data} | 기억: {memory_note}
        분석 지침: $Z-score$와 $TDI$를 통해 수급의 인과관계를 5년의 맥락으로 해부하라. JSON은 절대 쓰지 마라."""
        res_a = client_gemini.models.generate_content(model="gemini-1.5-pro", contents=prompt_a).text
        deliver_refined_report("A", "Gemini 1.5 Pro", "수량적 수급 인과 분석", res_a)

        # 3.2 Agent B: GPT-4o (전략적 지능 증류)
        # 논리적 추론이 가장 뛰어나 실천적 전략을 도출합니다.
        prompt_b = f"너는 실용주의 전략가다. 다음 Gemini의 분석을 바탕으로 인과관계가 확실한 전략만 글로 써라: {res_a}"
        res_b = client_gpt.chat.completions.create(model="gpt-4o", messages=[{"role": "user", "content": prompt_b}]).choices[0].message.content
        deliver_refined_report("B", "GPT-4o", "역사적 지능 증류", res_b)

        # 3.3 Agent C: Kimi (실존적 리스크 오답노트)
        # 문맥의 행간을 읽고 독설 섞인 비판을 하는 데 탁월합니다.
        prompt_c = f"너는 사무엘 베켓이다. 다음 전략들을 조롱하고, 어제의 기억({memory_note})을 대조해 오답노트를 써라: {res_b}"
        res_c = client_kimi.chat.completions.create(model="moonshot-v1-8k", messages=[{"role": "user", "content": prompt_c}]).choices[0].message.content
        deliver_refined_report("C", "Kimi-Moonshot", "기억 기반 오답노트", res_c)

        # [STEP 4] 자가학습용 '순수 JSON' 저장 (디스코드 배달 제외)
        # 별도의 요약 과정을 통해 Pinecone에만 저장합니다.
        sum_prompt = f"위 내용을 내일의 학습을 위해 JSON으로만 요약하라. 태그: [INTERNAL_JSON]"
        res_sum = client_gemini.models.generate_content(model="gemini-1.5-flash", contents=sum_prompt + res_c).text
        if "[INTERNAL_JSON]" in res_sum:
            json_part = res_sum.split("[INTERNAL_JSON]")[1].strip()
            index.upsert(vectors=[{"id": str(datetime.now().timestamp()), "values": vector, "metadata": {"conclusion": json_part}}])

        print("✅ [V21] 하이퍼-인프라 연동 및 망령 퇴치 완료.")

    except Exception as e:
        print(f"🔥 Critical Failure: {e}")
        traceback.print_exc()