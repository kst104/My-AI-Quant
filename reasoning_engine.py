import pandas as pd
import os  # os 모듈을 따로 불러와야 합니다!

def generate_market_hypothesis():
    file_name = "market_history.csv"
    
    # 1. 파일 존재 여부 확인 (수정된 부분)
    if not os.path.exists(file_name):
        print(f"❌ '{file_name}' 파일이 없습니다. 먼저 market_scanner.py를 실행하세요.")
        return

    # 2. 데이터 읽기
    df = pd.read_csv(file_name)
    if df.empty:
        print("❌ 데이터가 비어 있습니다.")
        return
        
    latest = df.iloc[-1]
    
    print(f"\n🤖 [AI 에이전트 간의 전략 회의 - {latest['date']}]")
    print("-" * 50)
    
    # 3. 이상 징후 포착 (분석 로직)
    anomalies = []
    if latest.get('에너지(XLE)', 0) > 2: anomalies.append("에너지 과열")
    if latest.get('금융(XLF)', 0) < -2: anomalies.append("금융권 불안")
    
    print(f"🧐 분석된 이상 징후: {', '.join(anomalies) if anomalies else '특이사항 없음'}")
    
    # 4. 에이전트 디베이트
    print("\n🐂 [Bull Agent]: '에너지와 헬스케어의 강세는 지수를 방어하려는 의지다. 기술주가 버티고 있으니 곧 반등한다.'")
    print("🐻 [Bear Agent]: '금융주의 급락은 실물 경제의 균열이다. 에너지가 튄 건 인플레이션 압박이다. 조심해라.'")
    
    # 5. 가설 설정 및 저장
    hypothesis = f"현재 {', '.join(anomalies) if anomalies else '안정세'} 상태임. 내일은 섹터 간 수익률 격차가 줄어들 것인가?"
    
    print("-" * 50)
    print(f"📝 내일 검증할 가설: {hypothesis}")
    
    with open("hypothesis_log.txt", "a", encoding="utf-8") as f:
        f.write(f"{latest['date']} | 가설: {hypothesis}\n")
    print("✅ 가설이 'hypothesis_log.txt'에 저장되었습니다.")

if __name__ == "__main__":
    generate_market_hypothesis()