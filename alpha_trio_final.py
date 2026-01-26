import os
import re
import json
import time
import requests
import traceback
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta
from openai import OpenAI
from pinecone import Pinecone
from google import genai

# ---------------------------------------------------------
# [STAGE 1: 인프라 - 모든 부품의 총결집]
# ---------------------------------------------------------
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")
OPENAI_KEY = os.environ.get("OPENAI_API_KEY")
KIMI_KEY = os.environ.get("KIMI_API_KEY")
PINECONE_KEY = os.environ.get("PINECONE_API_KEY")
NEWS_KEY = os.environ.get("NEWS_API_KEY")
DISCORD_URL = os.environ.get("DISCORD_WEBHOOK_URL")

# 멀티-브레인 클라이언트 정밀 초기화
client_gemini = genai.Client(api_key=GEMINI_KEY)
client_gpt = OpenAI(api_key=OPENAI_KEY)
client_kimi = OpenAI(api_key=KIMI_KEY, base_url="https://api.moonshot.cn/v1")
pc = Pinecone(api_key=PINECONE_KEY)
index = pc.Index("alpha-trio-memory")

# ---------------------------------------------------------
# [STAGE 2: 하이퍼-퀀트 - 5년 시계열 및 복합 지표 연산]
# ---------------------------------------------------------
def run_high_precision_scan():
    """500개 종목의 5년 데이터를 훑으며 $VWAP, Beta, TDI, ATR, Z-score$를 산출합니다."""
    print("🌌 [Stage 2] S&P 500 전 종목 5개년 역사 전수 조사 시작...")
    
    # 2.1 종목 리스트 및 벤치마크 데이터 확보
    r = requests.get("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies", timeout=30)
    tickers = pd.read_html(r.text)[0]["Symbol"].replace(".", "-", regex=True).tolist()
    
    # 감독님의 명령: AAPL, MSFT, NVDA는 식상하므로 분석 대상에서 강제 제외
    excluded = ["AAPL", "MSFT", "NVDA"]
    target_tickers = [t for t in tickers if t not in excluded]
    
    # 5년치($5y$) 벌크 다운로드 (약 1,250영업일)
    raw_data = yf.download(target_tickers, period="5y", group_by="ticker", progress=False, threads=True)
    sp500_bench = yf.download("^GSPC", period="5y", progress=False)['Close']

    diagnostic_pool = []
    
    for t in target_tickers:
        try:
            df = raw_data[t].dropna()
            if len(df) < 500: continue
            close, vol, high, low = df['Close'], df['Volume'], df['High'], df['Low']
            
            # 2.2 수급 및 역사적 희소성 ($Z-score$)
            # $Z_{score} = \frac{x - \mu}{\sigma}$ (5년 RSI 분포 대비 현재 위치)
            delta = close.diff()
            gain = delta.where(lambda x: x>0, 0).rolling(14).mean()
            loss = -delta.where(lambda x: x<0, 0).rolling(14).mean().replace(0, 1)
            rsi = 100 - (100 / (1 + (gain / loss)))
            z_score = (rsi.iloc[-1] - rsi.mean()) / rsi.std()
            
            # 2.3 TDI (Traders Dynamic Index) 및 VWAP
            tdi_pl = rsi.rolling(2).mean().iloc[-1]   # Price Line
            tdi_mbl = rsi.rolling(34).mean().iloc[-1] # Market Base Line
            vwap = (vol * (high + low + close) / 3).cumsum() / vol.cumsum()
            
            # 2.4 ATR 변동성 응축 및 Beta
            atr = (pd.concat([high-low, abs(high-close.shift()), abs(low-close.shift())], axis=1).max(axis=1)).rolling(14).mean()
            atr_ratio = atr.iloc[-1] / atr.mean()
            
            returns = close.pct_change().dropna()
            mkt_returns = sp500_bench.pct_change().dropna()
            common_idx = returns.index.intersection(mkt_returns.index)
            beta = returns.loc[common_idx].cov(mkt_returns.loc[common_idx]) / mkt_returns.loc[common_idx].var()

            # 역사적 임계점(Z-score 2.3 이상) 발견 시 '아웃라이어'로 선별
            if abs(z_score) > 2.3:
                diagnostic_pool.append({
                    "ticker": t, "price": round(close.iloc[-1], 2),
                    "z_score": round(z_score, 2), "tdi_gap": round(tdi_pl - tdi_mbl, 2),
                    "vwap_dist": round((close.iloc[-1] / vwap.iloc[-1] - 1) * 100, 2),
                    "beta": round(beta, 2), "atr_ratio": round(atr_ratio, 2)
                })
        except: continue
            
    diagnostic_pool.sort(key=lambda x: abs(x['z_score']), reverse=True)
    return diagnostic_pool[:3] # 가장 기괴한 3종목만 정밀 해부

# ---------------------------------------------------------
# [STAGE 3: 24h 인큐베이션 - 오답노트 및 그림자 학습]
# ---------------------------------------------------------
def process_shadow_learning(current_stats):
    """메시지 전송 전, 24시간 동안의 과오를 복기하여 지능을 보정합니다."""
    print("🧠 [Stage 3] Pinecone에서 어제의 기억을 소환 중...")
    input_str = json.dumps(current_stats)
    embed_res = client_gemini.models.embed_content(model="text-embedding-004", contents=input_str)
    vector = embed_res.embeddings[0].values
    
    # 3.1 어제의 나를 소환
    past = index.query(vector=vector, top_k=1, include_metadata=True)
    yesterday_logic = past.matches[0].metadata["conclusion"] if past.matches else "이전 데이터 없음"
    
    # 3.2 Kimi(베켓)가 어제의 오답을 무자비하게 해부
    note_prompt = f"어제의 예측: {yesterday_logic}\n오늘의 실제: {input_str}\n틀린 이유를 인과관계로 비판하라."
    error_note = client_kimi.chat.completions.create(model="moonshot-v1-8k", messages=[{"role": "user", "content": note_prompt}]).choices[0].message.content
    return yesterday_logic, error_note

# ---------------------------------------------------------
# [STAGE 4: 3인 위원회 - 가변적 전조 기간 끝장 토론]
# ---------------------------------------------------------
def conduct_final_debate(stats_str, error_note):
    """Gemini-GPT-Kimi가 종목별 최적의 '입질' 기간을 놓고 토론합니다."""
    print("💡 [Stage 4] 3국 연합군이 역사적 사례와 전조를 놓고 격론 중...")
    
    common_instr = "분석 내용은 반드시 [REPORT_START]와 [REPORT_END] 태그 사이에만 써라. JSON은 절대 금지다."

    # 4.1 Agent A: 인과적 해부
    prompt_a = f"{common_instr}\n데이터: {stats_str}\n오답노트: {error_note}\n5년 역사를 뒤져 입질 기간을 해부하라."
    res_a = client_gemini.models.generate_content(model="gemini-1.5-pro", contents=prompt_a).text
    
    # 4.2 Agent B: 전략 증류
    prompt_b = f"{common_instr}\nGemini의 분석을 기반으로 실전 전략을 증류하라: {res_a}"
    res_b = client_gpt.chat.completions.create(model="gpt-4o", messages=[{"role": "user", "content": prompt_b}]).choices[0].message.content
    
    # 4.3 Agent C: 최종 비판
    prompt_c = f"{common_instr}\n위 모든 내용을 비웃고 어제의 실패를 소환하라: {res_b}"
    res_c = client_kimi.chat.completions.create(model="moonshot-v1-8k", messages=[{"role": "user", "content": prompt_c}]).choices[0].message.content
    
    return res_a, res_b, res_c

# ---------------------------------------------------------
# [STAGE 5: 최종 보고서 - 망령 단두대 및 명품 배송]
# ---------------------------------------------------------
def stage_5_guillotine_delivery(agent_id, model_name, raw_content, m_summary=""):
    """[REPORT_START] 태그 사이의 통찰만 추출하여 JSON을 물리적으로 박멸합니다."""
    pattern = r"\[REPORT_START\](.*?)\[REPORT_END\]"
    match = re.search(pattern, raw_content, re.DOTALL)
    
    # 5.1 태그 추출 (실패 시 JSON 기호 강제 삭제 필터)
    clean_text = match.group(1).strip() if match else re.sub(r'[\{\}\[\]""]', '', raw_content).strip()
    
    emoji = {"A": "📉", "B": "💡", "C": "💀"}.get(agent_id, "🏛️")
    title = {"A": "수량적 수급 인과 해부", "B": "역사적 지능 기반 전략", "C": "실존적 리스크 오답노트"}.get(agent_id)
    
    # 5.2 감독님이 주신 Market Summary 헤더 (Agent A만 포함)
    header = f"### 📊 [Market Summary]\n{m_summary}\n\n" if agent_id == "A" else ""
    msg = f"{header}## {emoji} {title}\n**Agent {agent_id} ({model_name})**\n---\n{clean_text}\n"
    
    for i in range(0, len(msg), 1900):
        requests.post(DISCORD_URL, json={"content": msg[i:i+1900]}, timeout=30)
    time.sleep(1.5)

# ---------------------------------------------------------
# [STAGE 6: 메인 루프 가동]
# ---------------------------------------------------------
if __name__ == "__main__":
    try:
        # 1. 감독님이 주신 시장 상황 요약
        m_summary = "S&P500 Top50 내 과매수 종목은 3개... 볼린저밴드 상단 돌파 종목 전무하여 강력한 상승 동력 부재."
        
        # 2. 5년 시계열 전수 스캔 (AAPL/MSFT/NVDA 제외)
        outlier_stats = run_high_precision_scan()
        stats_str = json.dumps(outlier_stats)
        
        # 3. 24시간 자가학습 및 오답노트 복기
        yesterday, error_report = process_shadow_learning(outlier_stats)
        
        # 4. 3인 위원회 격론 및 전조 판단
        rep_a, rep_b, rep_c = conduct_final_debate(stats_str, error_report)
        
        # 5. Stage 5: 최종 보고서 물리적 정제 및 배송
        stage_5_guillotine_delivery("A", "Gemini 1.5 Pro", rep_a, m_summary)
        stage_5_guillotine_delivery("B", "GPT-4o", rep_b)
        stage_5_guillotine_delivery("C", "Kimi-Moonshot", rep_c)

    except Exception as e:
        print(f"🔥 Critical Failure: {e}")
        traceback.print_exc()