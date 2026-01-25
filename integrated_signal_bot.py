import pandas as pd
import requests
import os

# ⚠️ 여기에 본인의 디스코드 웹후크 URL이 따옴표 안에 정확히 있는지 다시 확인!
DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/1465062577879912686/22xOANOrt0m1AAIDoMyHUinUZhDxlrfry588g0JG7vYF3aA8MkccLP8ITf2AC19tq3GV"

def send_discord(msg):
    # 디스코드가 이해할 수 있는 형식으로 포장
    payload = {"content": msg}
    response = requests.post(DISCORD_WEBHOOK_URL, json=payload)
    if response.status_code == 204:
        print("✅ 디스코드 전송 성공!")
    else:
        print(f"❌ 전송 실패: {response.status_code}")

def deep_study():
    # 1. 파일이 있는지부터 확인
    if not os.path.exists("market_history.csv"):
        return "⚠️ [알림] market_history.csv 파일이 아직 없습니다. 수집부터 해야 해요!"

    df = pd.read_csv("market_history.csv")
    
    # 2. 데이터가 1개라도 있으면 일단 분석 시작
    if len(df) >= 1:
        latest_date = df.iloc[-1]['date']
        report = f"🚀 **AI 투자 비서가 보고드립니다! ({latest_date})**\n"
        report += "---"
        
        # 현재가와 전체 평균 비교 (데이터 1개면 평균이 곧 현재가)
        signals = []
        for sector in ['S&P500', '반도체(SOXX)', '기술주(XLK)']:
            if sector in df.columns:
                val = df[sector].iloc[-1]
                signals.append(f"- **{sector}**: {val}%")
        
        return report + "\n" + "\n".join(signals) + "\n\n✅ 시스템이 정상 작동 중입니다!"
    else:
        return "⚠️ 데이터 파일은 있는데 내용이 비어있습니다."

if __name__ == "__main__":
    # 무조건 실행 과정을 출력해서 로그에서 볼 수 있게 함
    print("🤖 시그널 봇 가동 시작...")
    analysis_result = deep_study()
    print(f"📝 분석 결과: {analysis_result}")
    send_discord(analysis_result)