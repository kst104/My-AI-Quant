import requests, time, os

def deliver_report(webhook_url, agent_id, model, text, market_sum=""):
    """디스코드 2000자 제한을 우회하여 100% 안전 배송"""
    emoji = {"A": "📉", "B": "💡", "C": "💀"}.get(agent_id, "🏛️")
    title = {"A": "수량적 수급 인과 분석", "B": "역사적 지능 기반 전략", "C": "실존적 비판 오답노트"}.get(agent_id)
    
    # 디자인적 위계를 고려한 헤더 구성
    header = f"### 📊 [Market Summary]\n{market_sum}\n\n" if agent_id == "A" else ""
    full_msg = f"{header}## {emoji} {title} ({model})\n---\n{text}\n"
    
    # 1800자 단위로 쪼개서 분할 전송 (잘림 방지)
    for i in range(0, len(full_msg), 1800):
        requests.post(webhook_url, json={"content": full_msg[i:i+1800]})
        time.sleep(1.2)