import os
import yfinance as yf
import pandas as pd
import pandas_ta as ta
import requests
import google.generativeai as genai
from pinecone import Pinecone
import json

# [환경 설정]
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")
NEWS_KEY = os.environ.get("NEWS_API_KEY")
PINECONE_KEY = os.environ.get("PINECONE_API_KEY")
DISCORD_URL = os.environ.get("DISCORD_WEBHOOK_URL")

genai.configure(api_key=GEMINI_KEY)
pc = Pinecone(api_key=PINECONE_KEY)
index = pc.Index("alpha-trio-memory")

def calculate_expert_indicators(df):
    """감독님 확정 5대 지표: RSI, BB, MACD, TDI, ATR"""
    # 데이터 정제: 인덱스가 중복되거나 빈 값이 있으면 지표 계산이 꼬입니다.
    df = df.copy()
    
    # 1. RSI (13) & ATR (14)
    df['RSI'] = ta.rsi(df['Close'], length=13)
    df['ATR'] = ta.atr(df['High'], df['Low'], df['Close'], length=14)
    
    # 2. Bollinger Bands (20, 2) & MACD (12, 26, 9)
    bb = ta.bbands(df['Close'], length=20, std=2)
    macd = ta.macd(df['Close'])
    df = pd.concat([df, bb, macd], axis=1)
    
    # 3. TDI 직접 구현 (RSI 기반의 심리 변동성 지표)
    df['TDI_P'] = ta.sma(df['RSI'], length=2) # Green Line
    df['TDI_S'] = ta.sma(df['RSI'], length=7) # Red Line
    df['TDI_M'] = ta.sma(df['RSI'], length=34) # Yellow Line
    return df

def get_intelligence():
    """시장 데이터 및 매크로 뉴스 수집"""
    targets = ["^GSPC", "^IXIC", "^TNX", "NVDA", "LLY", "SOXX"]
    market_summary = ""
    for t in targets:
        try:
            # 과거 복기를 위해 충분한 데이터를 가져옵니다.
            df = yf.download(t, period="100d", progress=False)
            df = calculate_expert_indicators(df)
            l = df.iloc[-1]
            p = df.iloc[-2]
            change = ((l['Close'] - p['Close']) / p['Close']) * 100
            
            market_summary += (f"[{t}] P:{round(float(l['Close']),2)}({round(float(change),2)}%) | "
                               f"RSI:{round(float(l['RSI']),1)} | ATR:{round(float(l['ATR']),2)} | "
                               f"TDI_P:{round(float(l['TDI_P']),1)}\n")
        except: continue
    
    # News API 데이터 (에이전트 B의 재료)
    news_res = requests.get(f"https://newsapi.org/v2/top-headlines?category=business&apiKey={NEWS_KEY}").json()
    news = "\n".join([f"- {a['title']}" for a in news_res.get('articles', [])[:5]])
    return market_summary, news

def recall_past_wisdom(market_context):
    """[Step 3] Vector DB에서 가장 유사한 과거 판단과 오답 소환"""
    try:
        embed = genai.embed_content(model="models/text-embedding-004", content=market_context)['embedding']
        results = index.query(vector=embed, top_k=2, include_metadata=True)
        memory_str = ""
        for match in results['matches']:
            date = match['metadata'].get('date', 'Unknown Date')
            memory_str += f"📍 {date}의 기록: {match['metadata']['conclusion']}\n"
        return memory_str if memory_str else "대조할 과거 기억이 없습니다."
    except: return "기억 저장소 일시 연결 불가."

def alpha_trio_debate():
    m, n = get_intelligence()
    past = recall_past_wisdom(m)
    
    model = genai.GenerativeModel('gemini-1.5-pro')
    prompt = f"""
    당신은 Alpha-Trio 2.1 위원회입니다. 24시간 자율 주행의 결과를 보고하십시오.
    
    [실시간 시장]\n{m}
    [매크로 뉴스]\n{n}
    [과거 오답노트/기록]\n{past}

    [에이전트 미션]
    - 에이전트 A (Quant): $RSI$, $MACD$, $TDI$ 지표로 수급의 탄력을 증명하라.
    - 에이전트 B (존 듀이): 과거와 현재를 교차검증하여 지식을 증류하라.
    - 에이전트 C (사무엘 베켓): 과거 오답을 근거로 비관적 리스크를 제안하라.

    반드시 아래 JSON 형식으로만 응답하십시오:
    {{
      "Verdict": "매수/매도/관망",
      "Confidence": "0-100%",
      "Debate_Log": {{ "A": "의견", "B": "의견", "C": "의견" }},
      "Self_Reflection": "과거 데이터 대비 오늘의 특이점 및 오답 분석",
      "Knowledge_Distilled": "오늘의 지식 증류 결과 (한 줄 원칙)",
      "Targets": {{ "Entry": "0", "TP": "0", "SL": "0" }}
    }}
    """
    return model.generate_content(prompt).text, m

def distill_and_save(verdict, market):
    try:
        # 오늘의 판단을 벡터화하여 영구 저장
        embed = genai.embed_content(model="models/text-embedding-004", content=market)['embedding']
        index.upsert(vectors=[{
            "id": str(pd.Timestamp.now().timestamp()),
            "values": embed,
            "metadata": {"conclusion": verdict, "date": str(pd.Timestamp.now())}
        }])
    except: pass

if __name__ == "__main__":
    print("🏛️ Alpha-Trio 2.1 위원회 가동...")
    try:
        final_verdict, market_data = alpha_trio_debate()
        distill_and_save(final_verdict, market_data)
        
        # 디스코드 보고
        requests.post(DISCORD_URL, json={"content": f"🏛️ **Alpha-Trio 2.1: 지식 증류 및 최종 판결**\n```json\n{final_verdict}\n```"})
        print("✅ 보고 완료")
    except Exception as e:
        print(f"❌ 가동 중 오류: {e}")