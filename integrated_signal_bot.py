import pandas as pd
import requests
import os

# 당신이 제공해주신 디스코드 웹후크 URL입니다.
DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/1465062577879912686/22xOANOrt0m1AAIDoMyHUinUZhDxlrfry588g0JG7vYF3aA8MkccLP8ITf2AC19tq3GV"

def send_discord(msg):
    try:
        response = requests.post(DISCORD_WEBHOOK_URL, json={"content": msg})
        if response.status_code == 204:
            print("✅ 디스코드 메시지 전송 성공!")
        else:
            print(f"❌ 전송 실패 (상태 코드: {response.status_code})")
    except Exception as e:
        print(f"❌ 에러 발생: {e}")

def deep_study():
    if not os.path.exists("market_history.csv"):
        return "⚠️ 아직 수집된 시장 데이터가 없습니다. 먼저 scanner를 실행하세요."
    
    df = pd.read_csv("market_history.csv")
    
    # 딥러닝 보고서 헤더
    report = f"🧠 **AI 시장 지능형 분석 보고서 ({df.iloc[-1]['date']})**\n"
    report += "---"
    signals = []
    
    # 과거 데이터 전체 평균과 현재 수익률 비교 (공부 로직)
    for sector in ['S&P500', '헬스케어(XLV)', '에너지(XLE)', '반도체(SOXX)', '기술주(XLK)']:
        if sector in df.columns:
            current = df[sector].iloc[-1]
            past_avg = df[sector].mean() # 과거 데이터 전체 평균 산출
            
            status = "✅ 강세" if current > past_avg else "📉 약세"
            signals.append(f"{status} **{sector}** (현재: {current}% / 과거평균: {round(past_avg, 2)}%)")
    
    # 매수/매도 시그널 결정 (강세 섹터가 3개 이상일 때 BUY)
    bull_count = len([s for s in signals if "✅" in s])
    if bull_count >= 3:
        final_signal = "🟢 **BUY (적극 매수)**"
    elif bull_count >= 1:
        final_signal = "🟡 **HOLD (관망/유지)**"
    else:
        final_signal = "🔴 **SELL (비중 축소)**"
        
    full_message = f"{report}\n" + "\n".join(signals) + f"\n\n⚖️ 최종 판단: {final_signal}\n*데이터가 축적될수록 AI의 판단은 더 정교해집니다.*"
    return full_message

if __name__ == "__main__":
    msg = deep_study()
    send_discord(msg)