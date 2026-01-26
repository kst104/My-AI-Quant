def post_discord(content: str):
    """
    ✅ Discord에서 '깨진 JSON 조각'이 아니라
    ✅ 각 메시지마다 '완전한 JSON'이 오게 하는 전송기

    전략:
    1) Gemini 응답에서 코드펜스 제거
    2) json.loads로 파싱 시도
    3) 파싱 성공하면:
       - 큰 JSON을 키(섹션) 단위로 분해해서
       - 각 조각을 json.dumps로 다시 직렬화(=유효한 JSON)
       - 2000자 제한에 맞춰 더 쪼개야 하면 '배열 단위/키 단위'로 더 잘게
    4) 파싱 실패하면:
       - 어쩔 수 없이 원문 텍스트로 보내되, 줄바꿈 포함하여 가독성만 확보
    """
    if not content:
        return

    def _send(msg: str):
        try:
            r = requests.post(DISCORD_URL, json={"content": msg}, timeout=30)
            if r.status_code != 204:
                print(f"⚠️ 전송 경고: {r.status_code} {r.text[:200]}")
            time.sleep(1.2)
        except Exception as e:
            print(f"❌ 전송 실패: {e}")

    # 1) 코드펜스 제거(혹시 Gemini가 ```json ... ``` 형태로 줄 때 대비)
    text = content.strip()
    if text.startswith("```"):
        # ```json ... ``` 제거
        text = text.replace("```json", "").replace("```", "").strip()

    # 2) JSON 파싱 시도
    obj = None
    try:
        obj = json.loads(text)
    except Exception:
        obj = None

    # 디스코드 글자 제한(보수적으로 1900)
    LIMIT = 1900

    # 3) 파싱 성공: "섹션 단위"로 보내기 (각 메시지 = 완전한 JSON)
    if obj is not None:
        # 최상단이 dict면 key 단위로 분리
        if isinstance(obj, dict):
            # 1순위: Alpha-Trio_Analysis 같은 최상위 키가 있으면 그 내부를 먼저 나눔
            if "Alpha-Trio_Analysis" in obj and isinstance(obj["Alpha-Trio_Analysis"], dict):
                root = obj["Alpha-Trio_Analysis"]
                parts = list(root.keys())
                total = len(parts)

                for i, k in enumerate(parts, 1):
                    payload = {"Alpha-Trio_Analysis": {k: root[k]}}
                    chunk = json.dumps(payload, ensure_ascii=False, indent=2)

                    # 만약 이 chunk 자체가 너무 크면 한 단계 더 쪼갬
                    if len(chunk) > LIMIT and isinstance(root[k], dict):
                        subkeys = list(root[k].keys())
                        for j, sk in enumerate(subkeys, 1):
                            payload2 = {"Alpha-Trio_Analysis": {k: {sk: root[k][sk]}}}
                            chunk2 = json.dumps(payload2, ensure_ascii=False, indent=2)
                            header = f"🏛️ **Alpha-Trio 판결문 ({k}.{sk})**"
                            msg = f"{header}\n```json\n{chunk2}\n```"
                            if len(msg) > 1990:
                                # 그래도 길면 indent 제거해서 최대한 줄임
                                chunk2 = json.dumps(payload2, ensure_ascii=False)
                                msg = f"{header}\n```json\n{chunk2}\n```"
                            _send(msg)
                        continue

                    header = f"🏛️ **Alpha-Trio 판결문 ({k})** ({i}/{total})"
                    msg = f"{header}\n```json\n{chunk}\n```"
                    if len(msg) > 1990:
                        chunk = json.dumps(payload, ensure_ascii=False)  # indent 제거
                        msg = f"{header}\n```json\n{chunk}\n```"
                    _send(msg)

                return  # ✅ 여기서 종료 (정상 전송 완료)

            # 최상단 키가 다른 구조면: 최상단 키별로 전송
            keys = list(obj.keys())
            total = len(keys)
            for i, k in enumerate(keys, 1):
                payload = {k: obj[k]}
                chunk = json.dumps(payload, ensure_ascii=False, indent=2)
                header = f"🏛️ **Alpha-Trio 판결문 ({k})** ({i}/{total})"
                msg = f"{header}\n```json\n{chunk}\n```"
                if len(msg) > 1990:
                    chunk = json.dumps(payload, ensure_ascii=False)
                    msg = f"{header}\n```json\n{chunk}\n```"
                _send(msg)
            return

        # 최상단이 list면: 원소 단위로 전송
        if isinstance(obj, list):
            for i, item in enumerate(obj, 1):
                chunk = json.dumps(item, ensure_ascii=False, indent=2)
                header = f"🏛️ **Alpha-Trio 판결문 (item {i}/{len(obj)})**"
                msg = f"{header}\n```json\n{chunk}\n```"
                if len(msg) > 1990:
                    chunk = json.dumps(item, ensure_ascii=False)
                    msg = f"{header}\n```json\n{chunk}\n```"
                _send(msg)
            return

    # 4) 파싱 실패: 원문을 "텍스트"로 분할 전송(깨진 JSON이라도 최소 가독성 유지)
    #    -> 그래도 너가 원하는 건 JSON이므로, 이 케이스가 나오면 Gemini 응답이 JSON이 아닌 것.
    chunk_size = 1500
    chunks = [text[i:i + chunk_size] for i in range(0, len(text), chunk_size)]
    for idx, chunk in enumerate(chunks, 1):
        header = f"🏛️ **Alpha-Trio 판결문 (RAW Part {idx}/{len(chunks)})**"
        msg = f"{header}\n```text\n{chunk}\n```"
        _send(msg)