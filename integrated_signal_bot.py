import os
import yfinance as yf
import pandas as pd
import pandas_ta as ta
import requests
import google.generativeai as genai
from pinecone import Pinecone
import json

# [환경 설정] GitHub Secrets로부터 보안 열쇠 소환
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")
NEWS_KEY = os.environ.get("NEWS_API_KEY")
PINECONE_KEY = os.environ.get("PINECONE_API_KEY")
DISCORD_URL = os.environ.get("DISCORD_WEBHOOK_URL")

# Gemini 및 Pinecone 인프라 동기화
genai.configure(api_key=GEMINI_KEY)
model = genai.GenerativeModel('gemini-1.5-pro')
pc = Pinecone(api_key=PINECONE_KEY)
index = pc.Index("alpha-trio-memory") # 감독님이 만드신 인덱스 이름

def calculate_expert_indicators(df):
    """감독님 확정 5대 지표: RSI, BB, MACD, TDI, ATR"""
    # 1. RSI (13) & ATR (14)
    df['RSI'] = ta.rsi(df['Close'], length=13)
    df['ATR'] = ta.atr(df['High'], df['Low'], df['Close'], length=14)
    
    # 2. Bollinger Bands (20, 2) & MACD (12, 26, 9)
    df = pd.concat([df, ta.bbands(df['Close'], length=20), ta.macd(df['Close'])], axis=1)
    
    # 3. TDI (Traders Dynamic Index) 직접 수식 구현
    # RSI의 SMA를 이용한 Price Line(Green)과 Signal Line(Red)
    df['TDI_P'] = ta.sma(df['RSI'], length=2)
    df['TDI_S'] = ta.sma(df['RSI'], length=7)
    df['TDI_M'] = ta.sma(df['RSI'], length=34) # Market Base Line (Yellow)
    return df

def get_total_intelligence():
    """시장 데이터 및 매크로 뉴스 수집"""
    # S&P500, 나스닥, 금리, 엔비디아, 일라이릴리 전수 조사
    targets = ["^GSPC", "^IXIC", "^TNX", "NVDA", "LLY", "SOXX"]
    market_summary = ""
    
    for t in targets:
        try:
            data = calculate_expert_indicators(yf.download(t, period="60d", progress=False))
            l = data.iloc[-1]
            market_summary += (f"[{t}] 현재가:{round(l['Close'],2)} | RSI:{round(l['RSI'],1)} | "
                               f"ATR:{round(l['ATR'],2)} | TDI_P:{round(l['TDI_P'],1)} | "
                               f"BB_Upper:{round(l['BBU_20_2.0'],2)}\n")
        except Exception as e:
            continue

    # News API를 통한 매크로 헤드라인 수집
    news_url = f"https://newsapi.org/v2/top-headlines?category=business&apiKey={NEWS_KEY}"
    news_res = requests.get(news_url).json()
    news_headlines = "\n".join([a['title'] for a in news_res.get('articles', [])[:5]])
    
    return market_summary, news_headlines

def get_past_memory(current_market):
    """[Step 3] Vector DB에서 과거 오답 노트 소환"""
    try:
        embed = genai.embed_content(model="models/text-embedding-004", content=current_market)['embedding']
        past_data = index.query(vector=embed, top_k=1, include_metadata=True)
        return past_data['matches'][0]['metadata']['conclusion'] if past_search['matches'] else "유사한 과거 사례 없음."
    except:
        return "장기 기억 장치 연결 중..."

def alpha_trio_council():
    market, news = get_total_intelligence()
    memory = get_past_memory(market)
    
    # [Step 2 & 4] 3인 에이전트 끝장 토론 및 확정적 판결
    prompt = f"""
    당신은 Alpha-Trio 2.1 위원회입니다. 아래 데이터를 기반으로 판결을 내리십시오.
    
    [실시간 시장 데이터]\n{market}
    [매크로 뉴스]\n{news}
    [장기 기억(오답 노트)]\n{memory}
    
    [에이전트 역할]
    1. 에이전트 A (현대 퀀트): RSI, MACD, TDI를 분석하여 현재 자금의 흐름과 탄력을 진단하라.
    2. 에이전트 B (존 듀이 - 실용주의): 금리와 뉴스 심리가 기업 가치를 지지하는지 경험론적으로 분석하라.
    3. 에이전트 C (사무엘 베켓 - 리스크 관리): ATR과 볼린저 밴드를 근거로 '기다림'의 가치를 역설하며 리스크를 점검하라.
    
    [제약 조건]
    - 반드시 JSON 형식으로만 답변할 것.
    - 과거 오답 노트를 반드시 참조하여 가중치를 둘 것.

    JSON 출력 규격:
    {{
      "Action": "매수/매도/관망/보유",
      "Targets": {{"Entry": "가격", "Target": "가격", "StopLoss": "가격"}},
      "Confidence": "0-100%",
      "Debate": "에이전트 간의 핵심 논쟁 요약 (인과관계 포함)",
      "Knowledge_Distilled": "오늘의 학습을 통한 한 줄 로직 요약"
    }}
    """
    
    response = model.generate_content(prompt)
    return response.text, market

def distillate_knowledge(verdict_json, market_data):
    """[Step 3] 지식 증류 및 Pinecone 저장"""
    try:
        embed = genai.embed_content(model="models/text-embedding-004", content=market_data)['embedding']
        index.upsert(vectors=[{
            "id": str(pd.Timestamp.now().timestamp()),
            "values": embed,
            "metadata": {"conclusion": verdict_json, "date": str(pd.Timestamp.now())}
        }])
    except Exception as e:
        print(f"기억 저장 실패: {e}")

if __name__ == "__main__":
    print("🏛️ Alpha-Trio 2.1 위원회 소집 중...")
    try:
        verdict, raw_market = alpha_trio_council()
        distillate_knowledge(verdict, raw_market)
        
        # 디스코드 보고서 전송
        report = f"🏛️ **Alpha-Trio 2.1 최종 판결 보고서**\n```json\n{verdict}\n```"
        requests.post(DISCORD_URL, json={"content": report})
        print("✅ 지식 증류 및 디스코드 보고 완료")
    except Exception as e:
        print(f"❌ 가동 중 오류 발생: {e}")