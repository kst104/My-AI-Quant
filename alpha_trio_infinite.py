# alpha_trio_infinite.py  (PATCHED FULL VERSION)

import os
import yfinance as yf
import pandas as pd
import requests
from pinecone import Pinecone
from datetime import datetime
import sys
import json

# =========================
# [1. 인프라 초기화]
# =========================
DISCORD_URL = os.environ.get("DISCORD_WEBHOOK_URL")
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")
PINECONE_KEY = os.environ.get("PINECONE_API_KEY")
NEWS_KEY = os.environ.get("NEWS_API_KEY")

# ✅ 필수값 검사 (NEWS_KEY 포함)
if not all([DISCORD_URL, GEMINI_KEY, PINECONE_KEY, NEWS_KEY]):
    print("❌ 에러: 필수 API 설정이 누락되었습니다. (DISCORD/GEMINI/PINECONE/NEWS)")
    sys.exit(1)

# ✅ Gemini 모델 후보 (404 뜨면 다음으로 자동 fallback)
GEMINI_MODEL_CANDIDATES = [
    "models/gemini-1.5-flash",  # 가장 안정적/추천
    "models/gemini-1.5-pro",    # 계정/리전에 따라 막혀 있을 수 있음
    "models/gemini-pro",        # 구버전 fallback
]

# Pinecone 초기화
pc = Pinecone(api_key=PINECONE_KEY)
index = pc.Index("alpha-trio-memory")

# =========================
# [2. 지표 계산]
# =========================
def calculate_expert_indicators(df: pd.DataFrame):
    if df is None or df.empty or len(df) < 40:
        return None

    df = df.copy()
    if "Close" not in df.columns:
        return None

    close = df["Close"]

    # Bollinger Bands
    df["BB_Mid"] = close.rolling(window=20).mean()
    df["BB_Std"] = close.rolling(window=20).std()
    df["BBU"] = df["BB_Mid"] + (df["BB_Std"] * 2)

    # RSI & TDI
    delta = close.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=13).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=13).mean()

    # ✅ 0 나누기 방지
    rs = gain / loss.replace(0, pd.NA)
    df["RSI"] = 100 - (100 / (1 + rs))
    df["TDI_PL"] = df["RSI"].rolling(window=2).mean()

    df = df.dropna()
    if df.empty:
        return None
    return df


# =========================
# [3. S&P500 스캔]
# =========================
def explore_sp500_full_galaxy():
    print("🌌 S&P 500 전 종목 5개년 전수 조사 가동...")

    try:
        table = pd.read_html("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies")
        tickers = table[0]["Symbol"].replace(".", "-", regex=True).tolist()

        # ✅ 실제 분석은 50개만 하므로, 다운로드도 50개만 (안정성 ↑)
        focus = tickers[:50]

        data = yf.download(
            focus,
            period="5y",
            group_by="ticker",
            progress=False,
            threads=True,
        )

        stats = {"Overbought": 0, "U-Break": 0}
        highlights = []

        for t in focus:
            try:
                # yfinance 결과 구조 안정화
                if isinstance(data.columns, pd.MultiIndex):
                    if t not in data.columns.get_level_values(0):
                        continue
                    sub = data[t].dropna(how="all")
                else:
                    # 단일 티커처럼 내려오는 경우 (드묾)
                    sub = data.dropna(how="all")

                df = calculate_expert_indicators(sub)
                if df is None:
                    continue

                l = df.iloc[-1]
                rsi = float(l["RSI"])
                bbu = float(l["BBU"])
                cls = float(l["Close"])
                tdi = float(l["TDI_PL"])

                if rsi > 70:
                    stats["Overbought"] += 1
                if cls > bbu:
                    stats["U-Break"] += 1

                if t in ["AAPL", "NVDA", "MSFT", "TSLA"]:
                    highlights.append(f"[{t}] RSI:{round(rsi,1)} | TDI:{round(tdi,1)}")

            except Exception:
                continue

        return (
            f"📊 S&P500 5y(Top50): 과매수({stats['Overbought']}), BB상단돌파({stats['U-Break']})\n"
            + "\n".join(highlights)
        )

    except Exception as e:
        return f"데이터 스캔 지연: {e}"


# =========================
# [4. Gemini REST 호출 (모델 fallback 포함)]
# =========================
def call_gemini_generate(prompt: str, model: str):
    url = f"https://generativelanguage.googleapis.com/v1beta/{model}:generateContent?key={GEMINI_KEY}"
    headers = {"Content-Type": "application/json"}
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.7, "topP": 0.95, "maxOutputTokens": 2048},
    }

    r = requests.post(url, headers=headers, json=payload, timeout=30)

    if r.status_code != 200:
        # 그대로 에러 텍스트를 올려서 원인 추적 가능하게
        raise Exception(f"{r.status_code} {r.text}")

    j = r.json()
    try:
        return j["candidates"][0]["content"]["parts"][0]["text"]
    except Exception:
        raise Exception(f"Gemini 응답 파싱 실패: {json.dumps(j)[:1000]}")


def call_gemini_nuclear_option(prompt: str):
    # ✅ 모델 후보를 순차 시도. 404/NOT_FOUND 뜨면 다음 모델로.
    last_err = None
    for model in GEMINI_MODEL_CANDIDATES:
        try:
            return call_gemini_generate(prompt, model)
        except Exception as e:
            last_err = e
            msg = str(e)
            if "404" in msg or "NOT_FOUND" in msg or "is not found" in msg:
                continue
            # 404가 아닌데 실패면(401/429/5xx 등) 즉시 중단하는 게 좋음
            raise
    raise Exception(f"Gemini 모델 전부 실패. 마지막 에러: {last_err}")


# =========================
# [5. 임베딩 REST 호출 (status 체크)]
# =========================
def get_embedding_nuclear(text: str):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/text-embedding-004:embedContent?key={GEMINI_KEY}"
    payload = {"model": "models/text-embedding-004", "content": {"parts": [{"text": text}]}}

    r = requests.post(url, json=payload, timeout=30)
    if r.status_code != 200:
        raise Exception(f"Embedding API 에러: {r.status_code} {r.text}")

    j = r.json()
    if "embedding" not in j or "values" not in j["embedding"]:
        raise Exception(f"Embedding 응답 형식 이상: {json.dumps(j)[:1000]}")

    return j["embedding"]["values"]


# =========================
# [6. NewsAPI (timeout + 안전 파싱)]
# =========================
def fetch_news_top5():
    url = f"https://newsapi.org/v2/top-headlines?category=business&language=en&apiKey={NEWS_KEY}"
    try:
        r = requests.get(url, timeout=15)
        j = r.json()
        if r.status_code != 200:
            return "뉴스 없음"

        arts = j.get("articles", [])
        titles = []
        for a in arts[:5]:
            t = a.get("title")
            if t:
                titles.append(f"🔥 {t}")
        return "\n".join(titles) if titles else "뉴스 없음"

    except Exception:
        return "뉴스 없음"


# =========================
# [7. Discord 전송 (에러 로깅)]
# =========================
def post_discord(content: str):
    try:
        r = requests.post(DISCORD_URL, json={"content": content}, timeout=15)
        if r.status_code >= 300:
            print("⚠️ Discord 전송 실패:", r.status_code, r.text[:200])
    except Exception as e:
        print("⚠️ Discord 전송 예외:", e)


# =========================
# [8. main]
# =========================
if __name__ == "__main__":
    print("🚀 Alpha-Trio Infinite V2 엔진 점화...")

    try:
        m_data = explore_sp500_full_galaxy()
        n_data = fetch_news_top5()

        brain_input = f"지표: {m_data}\n뉴스: {n_data}"
        if len(brain_input.strip()) < 30:
            brain_input = "데이터 수집 지연. 불확실성 시나리오 자가학습 가동."

        vector = get_embedding_nuclear(brain_input)
        # print("embedding dim:", len(vector))  # 필요시 확인

        # ✅ Pinecone memory 조회 안전화
        past = index.query(vector=vector, top_k=1, include_metadata=True)
        if past.get("matches"):
            md = past["matches"][0].get("metadata", {})
            memory = md.get("conclusion", "기억 불러오기 실패.")
        else:
            memory = "신규 학습 모드."

        prompt = f"""당신은 Alpha-Trio 위원회입니다.
데이터: {brain_input}
기억: {memory}

1. A(Quant): $BB$, $TDI$, $RSI$의 5개년 분포 분석.
2. B(Dewey): 뉴스와 지표 융합 지식 증류.
3. C(Beckett): 과거의 실패 근거로 독설 및 리스크 설계.

반드시 JSON 형식으로만 답하십시오.
"""

        verdict = call_gemini_nuclear_option(prompt)

        # ✅ Pinecone upsert
        index.upsert(
            vectors=[
                {
                    "id": str(datetime.now().timestamp()),
                    "values": vector,
                    "metadata": {"conclusion": verdict, "date": str(datetime.now())},
                }
            ]
        )

        # ✅ Discord 분할 전송 (1800 chars)
        for chunk in [verdict[i : i + 1800] for i in range(0, len(verdict), 1800)]:
            post_discord(f"🏛️ **Alpha-Trio Infinite(REST) 보고**\n```json\n{chunk}\n```")

        print("✅ 자가학습 완료. 이번엔 정말 성공입니다.")

    except Exception as e:
        print(f"🔥 치명적 에러 자백: {e}")
        sys.exit(1)
