import os
import sys
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

UA_HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AlphaTrioBot/NOJSON/1.0 (+https://github.com/)",
    "Accept-Language": "en-US,en;q=0.9",
}

pc = Pinecone(api_key=PINECONE_KEY)
index = pc.Index("alpha-trio-memory")


# =========================
# [2. Discord 전송 - JSON 박멸 버전]
# =========================
def post_discord_report(report_text: str, title: str = "Alpha-Trio 판결문"):
    """
    ✅ JSON 박멸: 텍스트 리포트만 전송
    - 디스코드 2000자 제한 대응:
      (1) 짧으면 메시지로
      (2) 길면 텍스트 파일로 첨부(가장 확실)
      (3) 파일이 싫으면: 섹션 단위로 분할 전송(의미 유지)
    """
    if not report_text:
        return

    def _send_text(msg: str):
        try:
            r = requests.post(DISCORD_URL, json={"content": msg}, timeout=30)
            if r.status_code != 204:
                print(f"⚠️ 전송 경고: {r.status_code} {r.text[:200]}")
            time.sleep(1.2)
        except Exception as e:
            print(f"❌ 전송 실패: {e}")

    def _send_file(filename: str, text: str, caption: str):
        try:
            payload = {"content": caption}
            files = {"file": (filename, text.encode("utf-8"), "text/plain")}
            r = requests.post(
                DISCORD_URL,
                data={"payload_json": __import__("json").dumps(payload, ensure_ascii=False)},
                files=files,
                timeout=60,
            )
            if r.status_code not in (200, 204):
                print(f"⚠️ 파일 전송 경고: {r.status_code} {r.text[:200]}")
            time.sleep(1.2)
        except Exception as e:
            print(f"❌ 파일 전송 실패: {e}")

    # 디스코드 메시지 안전 길이(헤더 포함)
    SAFE = 1700
    header = f"🏛️ **{title}**"

    # 너무 길면: 파일 첨부가 제일 깔끔
    if len(report_text) > 6000:
        _send_file(
            filename="alpha_trio_report.txt",
            text=report_text,
            caption=f"{header}\n(길이 초과 → 첨부 TXT 확인)"
        )
        return

    # 길이가 중간이면: 섹션 기준으로 분할해서 메시지로 보냄
    # 섹션 헤더 패턴: [A] / [B] / [C]
    sections = split_report_by_sections(report_text)

    # 섹션 분리가 잘 되면 섹션 단위로 전송
    if len(sections) >= 2:
        for i, sec in enumerate(sections, 1):
            msg = f"{header} (Part {i}/{len(sections)})\n```text\n{sec}\n```"
            if len(msg) <= 1990:
                _send_text(msg)
            else:
                # 섹션도 길면 파일로
                _send_file(
                    filename=f"alpha_trio_part_{i}.txt",
                    text=sec,
                    caption=f"{header} (Part {i}/{len(sections)}) (첨부 TXT 확인)"
                )
        return

    # 섹션 분리 안 되면: 그냥 길이로 쪼개기(텍스트니까 깨져도 의미 크게 안 망가짐)
    chunks = [report_text[i:i+SAFE] for i in range(0, len(report_text), SAFE)]
    for i, ch in enumerate(chunks, 1):
        msg = f"{header} (Part {i}/{len(chunks)})\n```text\n{ch}\n```"
        if len(msg) <= 1990:
            _send_text(msg)
        else:
            _send_file(
                filename=f"alpha_trio_chunk_{i}.txt",
                text=ch,
                caption=f"{header} (Part {i}/{len(chunks)}) (첨부 TXT 확인)"
            )


def split_report_by_sections(text: str):
    """
    텍스트 리포트를 [A], [B], [C] 섹션 기준으로 분할.
    """
    # 섹션 시작점 찾기
    markers = ["[A]", "[B]", "[C]"]
    idxs = []
    for m in markers:
        p = text.find(m)
        if p != -1:
            idxs.append((p, m))
    idxs.sort(key=lambda x: x[0])

    if not idxs:
        return [text.strip()]

    parts = []
    for i in range(len(idxs)):
        start = idxs[i][0]
        end = idxs[i+1][0] if i+1 < len(idxs) else len(text)
        parts.append(text[start:end].strip())
    return [p for p in parts if p]


# =========================
# [3. Gemini - JSON 금지 / 텍스트 보고서만]
# =========================
def pick_gemini_generate_model() -> str:
    """
    ListModels로 generateContent 가능한 모델만 선택.
    - pro가 있으면 pro 우선(있을 때만)
    - 없으면 flash/others
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

    # pro 우선, 없으면 flash 우선
    pro = [m for m in models if "pro" in m.lower()]
    if pro:
        return pro[0]
    flash = [m for m in models if "flash" in m.lower()]
    return flash[0] if flash else models[0]


def call_gemini_report(prompt: str) -> str:
    model = pick_gemini_generate_model()
    api_url = f"https://generativelanguage.googleapis.com/v1beta/{model}:generateContent?key={GEMINI_KEY}"

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.5,
            "topP": 0.9,
            "maxOutputTokens": 2048,  # ✅ 끊김 방지: 너무 크게 잡지 말고, 대신 "짧게 쓰게" 강제
        },
    }

    res = requests.post(api_url, json=payload, timeout=HTTP_TIMEOUT)
    if res.status_code != 200:
        raise Exception(f"Gemini API 에러(model={model}): {res.status_code} {res.text}")

    j = res.json()
    try:
        text = j["candidates"][0]["content"]["parts"][0]["text"]
        return (text or "").strip()
    except Exception:
        raise Exception(f"Gemini 응답 파싱 실패: {str(j)[:1000]}")


# =========================
# [4. Market & News (Full-Scan)]
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
        print("🚀 Alpha-Trio Infinite V2.2 (NO JSON) 가동...")
        m_data = explore_sp500_infinity()

        n_res = requests.get(
            f"https://newsapi.org/v2/top-headlines?category=business&language=en&apiKey={NEWS_KEY}",
            timeout=30,
            headers=UA_HEADERS
        ).json()
        n_data = "\n".join([f"- {a['title']}" for a in n_res.get("articles", [])[:5] if a.get("title")]) or "- (뉴스 없음)"

        # ✅ JSON 박멸 프롬프트: 고정 템플릿 강제 + 짧게 쓰게 제한
        prompt = f"""당신은 Alpha-Trio 위원회입니다.
절대 JSON을 사용하지 마십시오. 절대 중괄호/대괄호 기반 구조(JSON/유사JSON)를 쓰지 마십시오.
아래 템플릿 그대로 '텍스트 보고서'로만 출력하십시오.

[입력]
[지표]
{m_data}

[뉴스]
{n_data}

[출력 템플릿] (이 형식을 반드시 그대로 유지)
[A] Quant — 시장 상태
- (핵심 요약 3~6줄)
- (과매수/과매도/변동성/상단돌파 같은 관찰 3~6줄)

[B] Dewey — 뉴스×지표 결론
- (뉴스 5개를 시장 지표와 연결해 해석 3~6줄)
- (다음 24h~1주 리스크/기회 3~6줄)

[C] Beckett — 독설/리스크 설계
- (리스크 경고 3~6줄)
- (실패 시나리오 3~6줄)
- (행동 원칙 3~6줄)

[제한]
- 각 섹션은 최대 12줄
- 길어지면 요약해서라도 반드시 끝까지 완결된 보고서를 작성
"""

        verdict_text = call_gemini_report(prompt)

        # ✅ 디스코드: 텍스트 보고서만 전송
        post_discord_report(verdict_text, title="Alpha-Trio 판결문 (NO-JSON)")

        print("✅ 모든 보고가 완료되었습니다.")

    except Exception as e:
        print(f"🔥 에러: {e}")
        traceback.print_exc()
        # 에러도 디스코드로 남기고 싶으면:
        try:
            post_discord_report(str(e), title="Alpha-Trio 실행 에러")
        except Exception:
            pass
        sys.exit(1)