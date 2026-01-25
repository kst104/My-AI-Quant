import pandas as pd
import requests
import os

# 디스코드 설정 (채널 설정 -> 연동 -> 웹후크 에서 복사한 URL)
DISCORD_WEBHOOK_URL = "여기에_디스코드_웹후크_URL_입력"

def send_discord_msg(message):
    payload = {"content": message}
    requests.post(DISCORD_WEBHOOK_URL, json=payload)

def deep_study_logic():
    if not os.path.exists("market_history.csv"):
        return "⚠️ 데이터 파일이 없습니다."

    df = pd.read_csv("market_history.csv")
    
    # [진짜 공부: 과거 데이터 전체 분석]
    # 데이터가 10개 이상 쌓이면 과거 평균과 현재를 비교하는 '공부'를 시작합니다.
    if len(df) < 10:
        return f"📚 데이터 수집 중... (현재 {len(df)}일치)"

    report = "🧠 **AI 과거 데이터 딥러닝 결과**\n"
    signals = []

    # 섹터별로 과거 평균 대비 현재 위치 공부
    for sector in ['헬스케어(XLV)', '에너지(XLE)', '반도체(SOXX)', '기술주(XLK)']:
        current = df[sector].iloc[-1]
        past_avg = df[sector].mean() # 이게 '공부'입니다. 과거 전체의 평균을 계산함.
        
        if current > past_avg:
            signals.append(f"✅ {sector}: 과거 평균 돌파 (강세)")
        else:
            signals.append(f"📉 {sector}: 과거 평균 하회 (약세)")

    # 시그널 결정
    final = "🟢 BUY" if len([s for s in signals if "✅" in s]) >= 3 else "🟡 WAIT"

    return f"{report}\n{chr(10).join(signals)}\n\n⚖️ 최종 시그널: **{final}**"

if __name__ == "__main__":
    msg = deep_study_logic()
    send_discord_msg(msg)