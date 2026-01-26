# alpha_trio_infinite.py (GitHub Actions HARDENED VERSION)

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

# =========================
# [1. 인프라 초기화]
# =========================
DISCORD_URL = os.environ.get("DISCORD_WEBHOOK_URL")
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")
PINECONE_KEY = os.environ.get("PINECONE_API_KEY")
NEWS_KEY = os.environ.get("NEWS_API_KEY")

if not all([DISCORD_URL, GEMINI_KEY, PINECONE_KEY, NEWS_KEY]):
    print("❌ 에러: 필수 API 설정 누락 (DISCORD/GEMINI/PINECONE/NEWS)")
    sys.exit(1)

GEMINI_MODEL_CANDIDATES = [
    "models/gemini-1.5-flash",
    "models/gemini-1.5-pro",
    "models/gemini-pro",
]

HTTP_TIMEOUT = 30
UA_HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AlphaTrioBot/1.0 (+https://github.com/)",
    "Accept-Language": "en-US,en;q=0.9",
}

# Pinecone
pc = Pinecone(api_key=PINECONE_KEY)
index = pc.Index("alpha-trio-memory")


# =========================
# [2. Discord]
# =========================
def post_discord(content: str):
    try:
        r = requests.post(DISCORD_URL, json={"content": content}, timeout=HTTP_TIMEOUT)
        if r.status_code >= 300:
            print("⚠️ Discord 전송 실패:", r.status_code, r.text[:200])
    except Exception as e:
        print("⚠️ Discord 전송 예외:", repr(e))


# =========================
# [3. Gemini REST]
# =========================
def call_gemini_generate(prompt: str, model: str) -> str:
    url = f"https://generativelanguage.googleapis.com/v1beta/{model}:generateContent?key={GEMINI_KEY}"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.7, "topP": 0.95, "maxOutputTokens": 2048},
    }

    r = requests.post(url, json=payload, timeout=HTTP_TIMEOUT)
    if r.status_code != 200:
        raise Exception(f"Gemini {model} 실패: {r.status_code} {r.text}")

    j = r.json()
    try:
        return j["candidates"][0]["content"]["parts"][0]["text"]
    except Exception:
        raise Exception(f"Gemini 응답 파싱 실패: {json.dumps(j)[:1000]}")


def call_gemini_nuclear_option(prompt: str) -> str:
    last = None
    for model in GEMINI_MODEL_CANDIDATES:
        try:
            return call_gemini_generate(prompt, model)
        except Exception as e:
            last = e
            msg = str(e)
            # 404/NOT_FOUND면 다음 모델 시도
            if ("404" in msg) or ("NOT_FOUND" in msg) or ("is not found" in msg):
                continue
            # 그 외(401/429/5xx)는 즉시 중단(키/쿼터 문제일 가능성)
            raise
    raise Exception(f"Gemini 모델 전부 실패: {last}")


def get_embedding_nuclear(text: str):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/text-embedding-004:embedContent?key={GEMINI_KEY}"
    payload = {"model": "models/text-embedding-004", "content": {"parts": [{"text": text}]}}

    r = requests.post(url, json=payload, timeout=HTTP_TIMEOUT)
    if r.status_code != 200:
        raise Exception(f"Embedding API 에러: {r.status_code} {r.text}")

    j = r.json()
    if "embedding" not in j or "values" not in j["embedding"]:
        raise Exception(f"Embedding 응답 형식 이상: {json.dumps(j)[:1000]}")
    return j["embedding"]["values"]


# =========================
# [4. 뉴스]
# =========================
def fetch_news_top5():
    url = f"https://newsapi.org/v2/top-headlines?category=business&language=en&apiKey={NEWS_KEY}"
    try:
        r = requests.get(url, headers=UA_HEADERS, timeout=HTTP_TIMEOUT)
        j = r.json()
        if r.status_code != 200:
            return "뉴스 없음"

        arts = j.get("articles", [])[:5]
        titles = [f"🔥 {a.get('title')}" for a in arts if a.get("title")]
        return "\n".join(titles) if titles else "뉴스 없음"
    except Exception:
        return "뉴스 없음"


# =========================
# [5. 지표 계산]
# =========================
def calculate_expert_indicators(df: pd.DataFrame):
    if df is None or df.empty or len(df) < 40:
        return None
    if "Close" not in df.columns:
        return None

    df = df.copy()
    close = df["Close"]

    # Bollinger Bands
    df["BB_Mid"] = close.rolling(window=20).mean()
    df["BB_Std"] = close.rolling(window=20).std()
    df["BBU"] = df["BB_Mid"] + (df["BB_Std"] * 2)

    # RSI & TDI
    delta = close.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=13).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=13).mean()

    rs = gain / loss.replace(0, pd.NA)
    df["RSI"] = 100 - (100 / (1 + rs))
    df["TDI_PL"] = df["RSI"].rolling(window=2).mean()

    df = df.dropna()
    if df.empty:
        return None
    return df


# =========================
# [6. S&P500 티커 가져오기 (Actions에서 위키 차단 대응)]
# =========================
def fetch_sp500_tickers():
    wiki = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"

    # 실패 대비 폴백(최소 실행 보장용)
    fallback = [
        "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "BRK-B",
        "JPM", "V", "MA", "UNH", "XOM", "AVGO", "LLY", "COST", "HD", "KO"
    ]

    for attempt in range(1, 4):
        try:
            # ✅ 위키가 pd.read_html 직접 호출을 막는 경우가 있어
            # 먼저 requests로 HTML을 받아오고, 그 문자열로 read_html 파싱
            r = requests.get(wiki, headers=UA_HEADERS, timeout=HTTP_TIMEOUT)
            r.raise_for_status()
            tables = pd.read_html(r.text)
            tickers = tables[0]["Symbol"].replace(".", "-", regex=True).tolist()
            if tickers:
                return tickers
        except Exception as e:
            print(f"⚠️ 위키 티커 로드 실패 (attempt {attempt}/3): {repr(e)}")
            time.sleep(2 * attempt)

    print("⚠️ 위키 티커 로드 최종 실패 → 폴백 티커 사용")
    return fallback


def download_focus_data(tickers, period="5y"):
    # yfinance도 가끔 빈값 주거나 레이트리밋 걸리므로 재시도
    for attempt in range(1, 4):
        try:
            data = yf.download(
                tickers,
                period=period,
                group_by="ticker",
                progress=False,
                threads=True,
            )
            return data
        except Exception as e:
            print(f"⚠️ yfinance download 실패 (attempt {attempt}/3): {repr(e)}")
            time.sleep(2 * attempt)
    return None


def explore_sp500_full_galaxy():
    print("🌌 S&P 500 5개년 스캔 가동...")

    tickers = fetch_sp500_tickers()

    # ✅ 실제 분석은 50개만 → 다운로드도 50개만
    focus = tickers[:50]
    data = download_focus_data(focus, period="5y")

    if data is None or (isinstance(data, pd.DataFrame) and data.empty):
        return "데이터 스캔 지연: yfinance 데이터 수집 실패/빈 데이터"

    stats = {"Overbought": 0, "U-Break": 0}
    highlights = []

    for t in focus:
        try:
            if isinstance(data.columns, pd.MultiIndex):
                if t not in data.columns.get_level_values(0):
                    continue
                sub = data[t].dropna(how="all")
            else:
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


# =========================
# [7. main]
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

        index.upsert(
            vectors=[{
                "id": str(datetime.now().timestamp()),
                "values": vector,
                "metadata": {"conclusion": verdict, "date": str(datetime.now())},
            }]
        )

        for chunk in [verdict[i:i+1800] for i in range(0, len(verdict), 1800)]:
            post_discord(f"🏛️ **Alpha-Trio Infinite(REST) 보고**\n```json\n{chunk}\n```")

        print("✅ 자가학습 완료.")

    except Exception as e:
        print("🔥 치명적 에러 자백:", repr(e))
        traceback.print_exc()  # ✅ Actions에서 가장 중요 (에러 원인 바로 보임)
        sys.exit(1)
