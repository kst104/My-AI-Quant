import os
import yfinance as yf
import pandas as pd
import pandas_ta as ta
import requests
import google.generativeai as genai
from pinecone import Pinecone, ServerlessSpec

# [환경 변수 로드]
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")
NEWS_KEY = os.environ.get("NEWS_API_KEY")
PINECONE_KEY = os.environ.get("PINECONE_API_KEY")
DISCORD_URL = os.environ.get("DISCORD_WEBHOOK_URL")

# Gemini 및 Pinecone 초기화
genai.configure(api_key=GEMINI_KEY)
pc = Pinecone(api_key=PINECONE_KEY)
index_name = "alpha-trio-memory"

# 인덱스 연결
index = pc.Index(index_name)

def get_market_intelligence():
    """RSI, BB, MACD, TDI, ATR 지표 및 뉴스 통합 수집"""
    targets = ["^GSPC", "^TNX", "NVDA", "LLY"]
    market_str = ""
    for t in targets:
        df = yf.download(t, period="60d", progress=False)
        # 지표 계산
        df['RSI'] = ta.rsi(df['Close'], length=13)
        df['ATR'] = ta.atr(df['High'], df['Low'], df['Close'], length=14)
        macd = ta.macd(df['Close'])
        df = pd.concat([df, macd], axis=1)
        
        latest = df.iloc[-1]
        market_str += f"{t}: {round(latest['Close'],2)} (RSI:{round(latest['RSI'],1)}, ATR:{round(latest['ATR'],2)})\n"
    
    # 뉴스 수집
    news_url = f"https://newsapi.org/v2/top-headlines?category=business&apiKey={NEWS_KEY}"
    news_res = requests.get(news_url).json().get('articles', [])[:3]
    news_str = "\n".join([a['title'] for a in news_res])
    
    return market_str, news_str

def get_past_memories(query):
    """[Step 3] 유사 상황 오답 노트 소환"""
    try:
        # 텍스트를 벡터로 변환 (Gemini Embedding 모델 사용)
        res = genai.embed_content(model="models/text-embedding-004", content=query)
        vector = res['embedding']
        
        # Pinecone에서 가장 유사한 기록 2개 검색
        results = index.query(vector=vector, top_k=2, include_metadata=True)
        memories = ""
        for match in results['matches']:
            memories += f"- 과거 사례: {match['metadata']['conclusion']} (결과: {match['metadata']['result']})\n"
        return memories if memories else "과거 유사 사례 없음."
    except:
        return "기억 소환 실패 (신규 학습 중)"

def alpha_trio_council():
    market, news = get_market_intelligence()
    memories = get_past_memories(market) # 과거 오답 노트 소환
    
    # [Step 2 & 4] 세 명의 페르소나 토론 및 확정적 판결
    prompt = f"""
    당신은 Alpha-Trio 2.1 위원회입니다. 아래 데이터를 기반으로 토론하십시오.
    
    [시장 데이터]\n{market}
    [매크로 뉴스]\n{news}
    [과거 기억(오답 노트)]\n{memories}
    
    에이전트 A (Momentum): RSI, MACD 기반 수급 및 탄력 분석.
    에이전트 B (Fundamental): 금리, 가치, 뉴스 심리 분석. (Dewey의 관점)
    에이전트 C (Moderator): 과거 오답 노트를 근거로 판결. (Beckett의 리스크 관리)
    
    반드시 다음 형식의 JSON으로만 출력하세요:
    {{
        "Action": "매수/매도/관망",
        "Targets": {{"Entry": "가격", "Target": "가격", "StopLoss": "가격"}},
        "Confidence": "0-100%",
        "Debate": "에이전트별 핵심 논쟁 요약"
    }}
    """
    
    response = model.generate_content(prompt)
    return response.text

def distillate_knowledge(conclusion):
    """[Step 3] 지식 증류 및 Vector DB 영구 저장"""
    # 현재 상황을 벡터화하여 Pinecone에 저장
    # (실제 구현 시에는 내일 수익률 확인 후 'Success/Fail' 메타데이터 업데이트 로직 추가)
    res = genai.embed_content(model="models/text-embedding-004", content=conclusion)
    vector = res['embedding']
    index.upsert(vectors=[{
        "id": str(pd.Timestamp.now().timestamp()),
        "values": vector,
        "metadata": {"conclusion": conclusion, "result": "Pending"}
    }])

if __name__ == "__main__":
    print("🧠 Alpha-Trio 2.1 지능 가동...")
    final_verdict = alpha_trio_council()
    distillate_knowledge(final_verdict) # 지식 증류 (기억 저장)
    
    # 디스코드 전송
    requests.post(DISCORD_URL, json={"content": f"🏛️ **Alpha-Trio 2.1 최종 판결**\n```json\n{final_verdict}\n```"})
    print("✅ 지식 증류 및 보고 완료")