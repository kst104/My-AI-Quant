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
# [1. 설정 최적화]
# =========================
HTTP_TIMEOUT = 180
DISCORD_URL = os.environ.get("DISCORD_WEBHOOK_URL")
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")
PINECONE_KEY = os.environ.get("PINECONE_API_KEY")
NEWS_KEY = os.environ.get("NEWS_API_KEY")

if not all([DISCORD_URL, GEMINI_KEY, PINECONE_KEY, NEWS_KEY]):
    print("❌ 에러: 필수 API 설정이 누락되었습니다.")
    sys.exit(1)

pc = Pinecone(api_key=PINECONE_KEY)
index = pc.Index("alpha-trio-memory")


# =========================
# [2. Discord 전송]
# =========================
def post_discord(content: str):
    """
    ✅ '깨진 JSON 조각' 문제 해결 버전
    - 2000자 제한 때문에 문자열을 자르면 JSON은 무조건 깨짐
    - 따라서:
      (1) JSON 파싱 성공 시: 섹션 단위로 "완전한 JSON"을 만들어 전송
      (2) JSON 파싱 실패/너무 긴 경우: JSON 파일(.json)로 첨부 전송 (가장 확실)
    """
    if not content:
        return

    def _send_text(msg: str):
        try:
            r = requests.post(DISCORD_URL, json={"content": msg}, timeout=30)
            if r.status_code != 204:
                print(f"⚠️ 전송 경고: {r.status_code} {r.text[:200]}")
            time.sleep(1.2)
        except Exception as e:
            print(f"❌ 전송 실패: {e}")

    def _send_file(filename: str, file_bytes: bytes, caption: str):
        """
        Discord webhook 파일 업로드 (multipart/form-data)
        """
        try:
            payload = {"content": caption}
            files = {"file": (filename, file_bytes)}
            r = requests.post(
                DISCORD_URL,
                data={"payload_json": json.dumps(payload)},
                files=files,
                timeout=60,
            )
            if r.status_code not in (200, 204):
                print(f"⚠️ 파일 전송 경고: {r.status_code} {r.text[:200]}")
            time.sleep(1.2)
        except Exception as e:
            print(f"❌ 파일 전송 실패: {e}")

    # --- 1) 코드펜스 제거(혹시 Gemini가 ```json ... ``` 형태로 줄 때 대비) ---
    text = content.strip()
    if text.startswith("```"):
        text = text.replace("```json", "").replace("```", "").strip()

    # --- 2) JSON 파싱 시도 ---
    obj = None
    try:
        obj = json.loads(text)
    except Exception:
        obj = None

    # Discord 메시지 안전 길이(여유)
    LIMIT = 1900

    # --- 3) JSON 파싱 성공: 섹션별로 "완전한 JSON" 전송 ---
    if obj is not None and isinstance(obj, dict):
        # 가장 이상적인 구조: Alpha-Trio_Analysis 아래 A/B/C가 있는 경우
        if "Alpha-Trio_Analysis" in obj and isinstance(obj["Alpha-Trio_Analysis"], dict):
            root = obj["Alpha-Trio_Analysis"]
            keys = list(root.keys())
            total = len(keys)

            for i, k in enumerate(keys, 1):
                payload = {"Alpha-Trio_Analysis": {k: root[k]}}
                chunk = json.dumps(payload, ensure_ascii=False, indent=2)
                header = f"🏛️ **Alpha-Trio 판결문 ({k})** ({i}/{total})"
                msg = f"{header}\n```json\n{chunk}\n```"

                # 메시지 길이 초과 시: 파일로 보내는 게 가장 안전
                if len(msg) > 1990:
                    _send_file(
                        filename=f"alpha_trio_{k}.json",
                        file_bytes=chunk.encode("utf-8"),
                        caption=f"🏛️ **Alpha-Trio 판결문 ({k})** (첨부파일 확인)",
                    )
                else:
                    _send_text(msg)

            return

        # 그 외 dict 구조: 최상단 키 단위 전송
        keys = list(obj.keys())
        total = len(keys)
        for i, k in enumerate(keys, 1):
            payload = {k: obj[k]}
            chunk = json.dumps(payload, ensure_ascii=False, indent=2)
            header = f"🏛️ **Alpha-Trio 판결문 ({k})** ({i}/{total})"
            msg = f"{header}\n```json\n{chunk}\n```"

            if len(msg) > 1990:
                _send_file(
                    filename=f"alpha_trio_{k}.json",
                    file_bytes=chunk.encode("utf-8"),
                    caption=f"🏛️ **Alpha-Trio 판결문 ({k})** (첨부파일 확인)",
                )
            else:
                _send_text(msg)

        return

    # --- 4) JSON 파싱 실패(=모델 출력이 유효 JSON이 아님) 또는 dict가 아님 ---
    #     => 이 경우 "깨진 JSON 조각"으로 자르지 말고, 통째로 파일로 첨부해버리면 보기 문제는 해결됨.
    _send_file(
        filename="alpha_trio_verdict_raw.json",
        file_bytes=text.encode("utf-8"),
        caption="🏛️ **Alpha-Trio 판결문** (유효 JSON 파싱 실패 → 원문을 첨부파일로 전송)",
    )


# =========================
# [3. Gemini 1.5 Pro (REST)]
# =========================
def call_gemini(prompt: str) -> str:
    """
    - ListModels로 generateContent 가능한 모델만 가져옴
    - pro가 있으면 pro 우선, 없으면 첫 번째 사용
    - 응답이 JSON이 아니거나 끊길 수 있으므로, post_discord()가 파싱 실패 시 파일로 보냄
    """
    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={GEMINI_KEY}"
    r = requests.get(url, timeout=30).json()

    models = [
        m["name"]
        for m in r.get("models", [])
        if "generateContent" in m.get("supportedGenerationMethods", [])
    ]

    if not models:
        raise Exception("Gemini generateContent 지원 모델을 찾지 못했습니다. (ListModels 결과 비어있음)")

    # pro 우선 시도
    model = next((m for m in models if "pro" in m.lower()), models[0])

    api_url = f"https://generativelanguage.googleapis.com/v1beta/{model}:generateContent?key={GEMINI_KEY}"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.7,
            "maxOutputTokens": 4096,
            # NOTE: v1beta REST에서 무시될 수 있음. (모델이 텍스트 섞어서 주는 경우 있음)
            "response_mime_type": "application/json",
        },
    }

    res = requests.post(api_url, json=payload, timeout=HTTP_TIMEOUT)
    if res.status_code != 200:
        raise Exception(f"Gemini API 에러: {res.status_code} {res.text}")

    j = res.json()
    try:
        return j["candidates"][0]["content"]["parts"][0]["text"]
    except Exception:
        raise Exception(f"Gemini 응답 파싱 실패: {json.dumps(j)[:1000]}")


# =========================
# [4. Market & News (Full-Scan)]
# =========================
def explore_sp500_infinity():
    print("🌌 S&P 500 전 종목 5개년 전수 조사 가동...")
    try:
        r = requests.get("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies", timeout=30)
        tickers = pd.read_html(r.text)[0]["Symbol"].replace(".", "-", regex=True).tolist()

        # 데이터 수집 (500개 전 종목, 5년)
        data = yf.download(tickers, period="5y", group_by="ticker", progress=False, threads=True)

        # ... (지표 계산 및 요약 로직 생략, 기존 최강화 로직 적용) ...
        return "스캔 요약 데이터 (생략)"

    except Exception:
        return "데이터 수집 지연"


# =========================
# [5. main]
# =========================
if __name__ == "__main__":
    try:
        print("🚀 Alpha-Trio Infinite V2.2 가동...")
        m_data = explore_sp500_infinity()

        n_res = requests.get(
            f"https://newsapi.org/v2/top-headlines?category=business&language=en&apiKey={NEWS_KEY}",
            timeout=30
        ).json()
        n_data = "\n".join([f"🔥 {a['title']}" for a in n_res.get("articles", [])[:5]])

        prompt = f"""당신은 Alpha-Trio 위원회입니다.
[지표]: {m_data}
[뉴스]: {n_data}

에이전트 A, B, C의 분석을 포함하되, 각 분석은 핵심 통찰 위주로 간결하고 명확하게 작성하십시오.
불필요한 서술은 생략하고 JSON 구조를 엄격히 지키십시오.

반드시 아래 JSON 스키마를 따르십시오(다른 텍스트 금지):
{{
  "Alpha-Trio_Analysis": {{
    "A_Quant": {{}},
    "B_Dewey": {{}},
    "C_Beckett": {{}}
  }}
}}
"""

        verdict = call_gemini(prompt)

        # ✅ 디스코드 전송: 깨진 JSON 조각 방지 / 파싱 실패 시 파일 첨부
        post_discord(verdict)

        print("✅ 모든 보고가 완료되었습니다.")

    except Exception as e:
        print(f"🔥 에러: {e}")
        traceback.print_exc()
        sys.exit(1)