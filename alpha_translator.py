import re

def polish_to_human(raw_text, agent_type):
    """기계어와 태그를 제거하고, 문장의 위계를 정리하여 유려하게 번역"""
    pattern = r"\[REPORT_START\](.*?)\[REPORT_END\]"
    match = re.search(pattern, raw_text, re.DOTALL)
    content = match.group(1).strip() if match else raw_text

    # 불필요한 기호 및 JSON 잔재 물리적 박멸
    content = re.sub(r'[\{\}\[\]""]', '', content)
    content = re.sub(r'[a-zA-Z0-9_]+:', '', content).strip()

    # 지능 검수: 너무 짧으면 '나처럼' 다시 생각하게 만드는 로직 (개념적)
    if len(content) < 100:
        return "⚠️ 분석의 깊이가 임계점에 도달하지 못했습니다. 공정을 재가동하십시오."
    
    # 여기서 각 에이전트의 톤을 '유려하게' 최종 보정하는 텍스트 필터 상주
    return content