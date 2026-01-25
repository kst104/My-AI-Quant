import os
import yfinance as yf
import pandas as pd
import pandas_ta as ta
import requests
import google.generativeai as genai
from pinecone import Pinecone

# [인프라 설정] GitHub Secrets로부터 열쇠 소환
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")
NEWS_KEY = os.environ.get("NEWS_API_KEY")
PINECONE_KEY = os.environ.get("PINECONE_API_KEY")
DISCORD_URL = os.environ.get("DISCORD_WEBHOOK_URL")

# Gemini 1.5 Pro 설정
genai.configure(api_key=GEMINI_KEY)
model = genai.GenerativeModel('gemini-1.5-pro')

# Pinecone 장기 기억 장치 연결
pc = Pinecone(api_key=PINECONE_KEY)
# 인덱스가 없다면 미리 생성해두어야 합니다 (Dimension: 1536 등 모델에 맞춰 설정)
index = pc.Index("alpha-trio-memory") 

def get_market_data():
    """시세 및 기술적 지표(RSI, BB, MACD, TDI, ATR) 수집"""
    targets = ["^GSPC", "^IXIC", "^TNX", "DX-Y.NYB", "NVDA", "LLY"]
    combined_report = ""
    
    for t in targets:
        df = yf.download(t, period="60d", progress=False)
        # 지표 계산 로직 (Step 2에서 페르소나들이 사용할 재료)
        df['RSI'] = ta.rsi(df['Close'], length=13)
        df['ATR'] = ta.atr(df['High'], df['Low'], df['Close'], length=14)
        bb = ta.bbands(df['Close'], length=20)
        macd = ta.macd(df['Close'])
        df = pd.concat([df, bb, macd], axis=1)
        
        latest = df.iloc[-1]
        combined_report += f"[{t}] 종가:{round(latest['Close'],2)} RSI:{round(latest['RSI'],1)} ATR:{round(latest['ATR'],2)}\n"
    
    return combined_report

def get_news_data():
    """News API를 통한 매크로 헤드라인 수집"""
    url = f"https://newsapi.org/v2/top-headlines?category=business&language=en&apiKey={NEWS_KEY}"
    try:
        res = requests.get(url).json()
        articles = [a['title'] for a in res.get('articles', [])[:5]]
        return "\n".join(articles)
    except:
        return "뉴스 데이터를 가져올 수 없습니다."

def alpha_trio_logic():
    market = get_market_data()
    news = get_news_data()
    
    # [Step 2/3 예고] Gemini에게 3인의 페르소나 역할을 부여하고 토론 시작
    prompt = f"""
    당신은 'Alpha-Trio 2.1' 위원회의 세 에이전트입니다.
    데이터: {market}
    뉴스: {news}
    
    에이전트 A(현대 퀀트): 기술적 지표(RSI, MACD, TDI) 기반 수급 분석.
    에이전트 B(존 듀이): 매크로 및 뉴스 심리 기반 가치 분석.
    에이전트 C(사무엘 베켓): 리스크 관리 및 최종 판결.
    
    과거 오답 노트를 참조하여 토론하고, [매수/매도/관망] 결론을 내세요.
    """
    
    response = model.generate_content(prompt)
    return response.text

def send_discord(msg):
    requests.post(DISCORD_URL, json={"content": msg})

if __name__ == "__main__":
    print("🚀 Alpha-Trio 2.1 인프라 가동...")
    report = alpha_trio_logic()
    send_discord(report)
    print("✅ 보고 완료")