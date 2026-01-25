import pandas as pd
import requests
import os

# 당신이 방금 주신 URL을 제가 직접 심었습니다.
DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/1465062577879912686/22xOANOrt0m1AAIDoMyHUinUZhDxlrfry588g0JG7vYF3aA8MkccLP8ITf2AC19tq3GV"

def send_discord(msg):
    payload = {"content": msg}
    try:
        response = requests.post(DISCORD_WEBHOOK_URL, json=payload)
        if response.status_code == 204:
            print("✅ 디스코드 전송 성공!")
        else:
            print(f"❌ 전송 실패 (상태 코드: {response.status_code})")
    except Exception as e:
        print(f"❌ 연결 에러: {e}")

def deep_study():
    # 데이터 파일 존재 여부 확인
    if not os.path.exists("market_history.csv"):
        return "📢 [테스트 보고] 시스템은 성공했으나 데이터 파일이 아직 생성되지 않았습니다."

    try:
        df = pd.read_csv("market_history.csv")
        if len(df) == 0:
            return "📢 [테스트 보고] 파일은 존재하나 데이터가 비어있습니다."
        
        # 데이터가 있으면 분석 수행
        latest = df.iloc[-1]
        report = f"🚀 **AI 시장 분석 보고 ({latest['date']})**\n"
        report += f"📊 S&P500: {latest.get('S&P500', 'N/A')}% | 기술주: {latest.get('기술주(XLK)', 'N/A')}%\n"
        report += "--- \n✅ AI가 시장 데이터를 정상적으로 읽고 전송 중입니다."
        return report
    except Exception as e:
        return f"⚠️ 분석 중 에러 발생: {e}"

if __name__ == "__main__":
    print("🤖 시그널 봇 작동 시작...")
    # 1. 일단 공부 결과 생성
    result_msg = deep_study()
    # 2. 디스코드로 전송
    send_discord(result_msg)
    # 3. 로그에도 남김
    print(f"최종 전송 메시지: {result_msg}")