import pandas as pd
import os

def evaluate_self_learning():
    history_file = "market_history.csv"
    hypothesis_file = "hypothesis_log.txt"

    if not os.path.exists(history_file) or not os.path.exists(hypothesis_file):
        print("❌ 학습을 위한 데이터나 가설 로그가 부족합니다.")
        return

    # 1. 데이터 로드
    df = pd.read_csv(history_file)
    if len(df) < 2:
        print("💡 자가학습을 위해서는 최소 2일 이상의 데이터가 필요합니다. 내일 다시 실행해 주세요!")
        return

    # 2. 어제의 가설과 오늘의 실제 데이터 비교
    yesterday_data = df.iloc[-2]
    today_data = df.iloc[-1]
    
    # 예시: 섹터 간 격차(표준편차) 계산을 통한 가설 검증
    yesterday_std = yesterday_data[1:].std() # 날짜 제외한 섹터들 수익률 편차
    today_std = today_data[1:].std()

    print(f"\n🧠 [AI 자가 성찰 보고서]")
    print("-" * 50)
    print(f"📉 어제의 시장 변동성(격차): {round(yesterday_std, 2)}")
    print(f"📈 오늘의 시장 변동성(격차): {round(today_std, 2)}")

    if today_std < yesterday_std:
        result = "성공 (격차가 줄어듦)"
    else:
        result = "실패 (격차가 오히려 벌어짐)"

    print(f"\n🎯 가설 검증 결과: {result}")
    
    # 3. 학습 결과 저장 (이것이 AI의 지능이 됩니다)
    with open("learning_results.txt", "a", encoding="utf-8") as f:
        f.write(f"{today_data['date']} | 결과: {result} | 변동성 변화: {round(yesterday_std, 2)} -> {round(today_std, 2)}\n")
    
    print("-" * 50)
    print("✅ 학습 결과가 'learning_results.txt'에 저장되었습니다. AI가 한 단계 성장했습니다.")

if __name__ == "__main__":
    evaluate_self_learning()