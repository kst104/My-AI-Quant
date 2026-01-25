import yfinance as yf
import pandas as pd
import os
from datetime import datetime

# 1. 대상 자산 설정
market_assets = {
    "S&P500": "^GSPC",
    "나스닥": "^IXIC",
    "반도체(SOXX)": "SOXX",
    "헬스케어(XLV)": "XLV",
    "기술주(XLK)": "XLK",
    "금융(XLF)": "XLF",
    "에너지(XLE)": "XLE",
    "중소형주(IWM)": "IWM"
}

def run_self_learning_cycle():
    print(f"📅 분석 일시: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # [Data Collection]
    current_results = {"date": datetime.now().strftime('%Y-%m-%d')}
    for name, ticker in market_assets.items():
        data = yf.Ticker(ticker).history(period="5d")
        change = ((data['Close'].iloc[-1] - data['Close'].iloc[-2]) / data['Close'].iloc[-2]) * 100
        current_results[name] = round(change, 2)

    # [Memory: Save to CSV]
    file_name = "market_history.csv"
    df_current = pd.DataFrame([current_results])
    
    if os.path.exists(file_name):
        # 과거 데이터가 있다면 불러와서 비교 (자가학습 기초)
        df_history = pd.read_csv(file_name)
        last_record = df_history.iloc[-1]
        
        print("\n🔄 [자가 학습: 어제와 오늘 비교]")
        for asset in market_assets.keys():
            diff = current_results[asset] - last_record[asset]
            trend = "📈 강화" if diff > 0 else "📉 약화"
            print(f"{asset}: {current_results[asset]}% (전일 대비 {round(diff, 2)}% {trend})")
        
        # 합치기
        df_updated = pd.concat([df_history, df_current], ignore_index=True)
    else:
        print("\n🆕 첫 데이터 기록을 시작합니다.")
        df_updated = df_current

    df_updated.to_csv(file_name, index=False)
    print(f"\n✅ '{file_name}'에 지식이 저장되었습니다. AI의 기억력이 +1 상승했습니다.")

if __name__ == "__main__":
    run_self_learning_cycle()