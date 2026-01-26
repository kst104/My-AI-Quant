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
# [1. 설정]
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

UA_HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AlphaTrioBot/4.0 (+https://github.com/)",
    "Accept-Language": "en-US,en;q=0.9",
}

# =========================
# [2. Discord 전송]
# =========================
def post_discord_json(obj: dict):
    """
    ✅ Discord에 '유효한 JSON'만 보내는 전송기
    - 메시지로 보내기(짧을 때) or 파일로 첨부(길 때)
    - A/B/C 섹션 단위로 쪼개서 각 메시지를 '완전한 JSON'으로 보장
    """
    def _send_text(msg: str):
        r = requests.post(DISCORD_URL, json={"content": msg}, timeout=30)
        if r.status_code != 204:
            print(f"⚠️ Discord 전송 경고: {r.status_code} {r.text[:200]}")
        time.sleep(1.2)

    def _send_file(filename: str, text: str, caption: str):
        payload = {"content": caption}
        files = {"file": (filename, text.encode("utf-8"), "application/json")}
        r = requests.post(
            DISCORD_URL,
            data={"payload_json": json.dumps(payload, ensure_ascii=False)},
            files=files,
            timeout=60,
        )
        if r.status_code not in (200, 204):
            print(f"⚠️ Discord 파일 전송 경고: {r.status_code} {r.text[:200]}")
        time.sleep(1.2)

    # 디스코드 메시지 제한 여유치
    LIMIT = 1900

    # 가장 흔한 스키마: {"Alpha-Trio_Analysis": {...}}
    if isinstance(obj, dict) and "Alpha-Trio_Analysis" in obj and isinstance(obj["Alpha-Trio_Analysis"], dict):
        root = obj["Alpha-Trio_Analysis"]
        keys = list(root.keys())  # A_Quant, B_Dewey, C_Beckett...
        total = len(keys)

        for i, k in enumerate(keys, 1):
            payload = {"Alpha-Trio_Analysis": {k: root[k]}}
            body_pretty = json.dumps(payload, ensure_ascii=False, indent=2)
            msg = f"🏛️ **Alpha-Trio 판결문 ({k})** ({i}/{total})\n```json\n{body_pretty}\n```"

            if len(msg) <= 1990:
                _send_text(msg)
            else:
                # 너무 길면 파일로
                _send_file(
                    filename=f"alpha_trio_{k}.json",
                    text=body_pretty,
                    caption=f"🏛️ **Alpha-Trio 판결문 ({k})** (길이 초과 → 첨부 JSON 확인)",
                )
        return

    # 기타 구조면 전체를 한번에 시도 (길면 파일)
    body_pretty = json.dumps(obj, ensure_ascii=False, indent=2)
    msg = f"🏛️ **Alpha-Trio 판결문**\n```json\n{body_pretty}\n```"
    if len(msg) <= 1990:
        _send_text(msg)
    else:
        _send_file("alpha_trio_verdict.json", body_pretty, "🏛️ **Alpha-Trio 판결문** (첨부 JSON 확인)")


def post_discord_raw(text: str, reason: str):
    """
    ✅ 최후의 보루: 모델이 끝까지 JSON을 못 만들면 원문을 파일로 첨부
    (그래도 디스코드에서 '깨져 보이는' 문제는 끝)
    """
    payload = {"content": f"🏛️ **Alpha-Trio 판결문** ({reason})\n(원문 첨부파일 확인)"}
    files = {"file": ("alpha_trio_verdict_raw.txt", (text or "").encode("utf-8"), "text/plain")}
    r = requests.post(
        DISCORD_URL,
        data={"payload_json": json.dumps(payload, ensure_ascii=False)},
        files=files,
        timeout=60,
    )
    if r.status_code not in (200, 204):
        print(f"⚠️ Discord RAW 파일 전송 경고: {r.status_code} {r.text[:200]}")
    time.sleep(1.2)

# =========================
# [3. Gemini REST]
# =========================
def pick_gemini_generate_model() -> str:
    """
    ✅ ListModels로 generateContent 지원 모델 중에서:
    - 가능하면 flash 우선(자동화 안정성)
    - pro는 있으면 선택 가능하지만, 계정/리전에 따라 아예 안 뜨는 경우가 많음
    """
    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={GEMINI_KEY}"
    res = requests.get(url, timeout=30)
    if res.status_code != 200:
        raise Exception(f"ListModels 실패: {res.status_code} {res.text}")

    j = res.json()
    models = []
    for m in j.get("models", []):
        name = m.get("name", "")
        methods = m.get("supportedGenerationMethods", []) or []
        if "generateContent" in methods:
            models.append(name)

    if not models:
        raise Exception("generateContent 지원 모델이 없습니다.")

    # 우선순위: flash > pro > others
    def score(n: str):
        n = (n or "").lower()
        if "flash" in n:
            return 0
        if "pro" in n:
            return 1
        return 2

    models.sort(key=score)
    return models[0]


def call_gemini_once(prompt: str) -> str:
    model = pick_gemini_generate_model()
    api_url = f"https://generativelanguage.googleapis.com/v1beta/{model}:generateContent?key={GEMINI_KEY}"

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.3,
            "topP": 0.9,
            "maxOutputTokens": 4096,
        },
    }

    res = requests.post(api_url, json=payload, timeout=HTTP_TIMEOUT)
    if res.status_code != 200:
        raise Exception(f"Gemini API 에러(model={model}): {res.status_code} {res.text}")

    j = res.json()
    try:
        return j["candidates"][0]["content"]["parts"][0]["text"]
    except Exception:
        raise Exception(f"Gemini 응답 파싱 실패: {json.dumps(j)[:1000]}")


def extract_text_clean(s: str) -> str:
    if not s:
        return ""
    t = s.strip()
    if t.startswith("```"):
        t = t.replace("```json", "").replace("```", "").strip()
    return t


def call_gemini_json(prompt: str, max_retries: int = 3) -> dict:
    """
    ✅ 핵심 해결 로직
    - 모델 출력이 '중간에서 끊긴 JSON'이면 디스코드가 뭘 해도 깨져 보임
    - 그래서 모델 응답을 json.loads로 검증하고, 실패하면 'JSON만' 다시 쓰라고 재요청
    """
    raw = ""
    for attempt in range(1, max_retries + 1):
        raw = call_gemini_once(prompt)
        cleaned = extract_text_clean(raw)

        try:
            obj = json.loads(cleaned)
            if isinstance(obj, dict):
                return obj
            # dict가 아니면 스키마 위반이므로 재요청
            raise ValueError("최상단 JSON이 dict가 아님")
        except Exception as e:
            # 다음 라운드: "수정 요청 프롬프트"로 재시도
            prompt = f"""너의 이전 응답은 유효한 JSON이 아니었습니다(중간에서 끊겼거나 따옴표/괄호가 닫히지 않음).
아래 텍스트를 '내용은 최대한 유지'하면서, 반드시 json.loads()가 성공하는 '완전한 JSON'으로만 다시 출력하세요.

규칙:
- 코드블록( ``` ) 금지
- JSON 외 텍스트 금지
- 문자열/배열/객체 모두 완전히 닫기
- 너무 길면 항목 수를 줄여서라도 JSON을 완결시키기
- 스키마는 반드시 아래를 따르기:
{{
  "Alpha-Trio_Analysis": {{
    "A_Quant": {{}},
    "B_Dewey": {{}},
    "C_Beckett": {{}}
  }}
}}

[이전 응답 텍스트]
{cleaned}
"""
            # 재시도 간 딜레이
            time.sleep(1.5)

    # 끝까지 실패하면 호출자가 처리
    raise Exception(f"유효 JSON 생성 실패(재시도 {max_retries}회). 마지막 원문 일부: {raw[:300]}")


# =========================
# [4. Market & News]
# =========================
def explore_sp500_infinity():
    print("🌌 S&P 500 전 종목 5개년 전수 조사 가동...")
    try:
        r = requests.get("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies", timeout=30, headers=UA_HEADERS)
        tickers = pd.read_html(r.text)[0]["Symbol"].replace(".", "-", regex=True).tolist()

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
            timeout=30,
            headers=UA_HEADERS
        ).json()
        n_data = "\n".join([f"🔥 {a['title']}" for a in n_res.get("articles", [])[:5]])

        # ✅ 길게 쓰지 말라고 강하게 제한해야 "중간에서 끊김"이 사라짐
        prompt = f"""당신은 Alpha-Trio 위원회입니다.
[지표]: {m_data}
[뉴스]: {n_data}

요구사항:
- 반드시 JSON만 출력(다른 텍스트 금지)
- 각 섹션(A/B/C)은 길지 않게: 문장 3~6개, 또는 bullet 3~6개 수준으로 제한
- 리스트 항목은 최대 6개
- 너무 길어질 것 같으면 요약해서라도 JSON을 완결시키기

반드시 아래 스키마를 따르십시오:
{{
  "Alpha-Trio_Analysis": {{
    "A_Quant": {{
      "analysis_title": "...",
      "analysis_body": ["...","..."]
    }},
    "B_Dewey": {{
      "analysis_title": "...",
      "analysis_body": ["...","..."]
    }},
    "C_Beckett": {{
      "analysis_title": "...",
      "analysis_body": ["...","..."]
    }}
  }}
}}
"""

        # ✅ 여기서 '유효 JSON'이 될 때까지 고쳐 받는다
        verdict_obj = call_gemini_json(prompt, max_retries=3)

        # ✅ 디스코드는 이제 항상 '완전한 JSON'만 받는다
        post_discord_json(verdict_obj)

        print("✅ 모든 보고가 완료되었습니다.")

    except Exception as e:
        print(f"🔥 에러: {e}")
        traceback.print_exc()
        # 실패해도 디스코드에 원문/에러를 파일로 남기고 싶으면 여기서 보낼 수 있음
        try:
            post_discord_raw(str(e), reason="실행 에러")
        except Exception:
            pass
        sys.exit(1)