def get_law_list_from_api(query):
    exact_query = f'"{query}"'
    encoded_query = quote(exact_query)
    page = 1
    laws = []
    while True:
        url = f"{BASE}/DRF/lawSearch.do?OC={OC}&target=law&type=XML&display=100&page={page}&search=2&knd=A0002&query={encoded_query}"
        try:
            res = requests.get(url, timeout=10)
            res.encoding = 'utf-8'
            if res.status_code != 200:
                break
            root = ET.fromstring(res.content)
            for law in root.findall("law"):
                laws.append({
                    "법령명": law.findtext("법령명한글", "").strip(),
                    "MST": law.findtext("법령일련번호", "")
                })
            if len(root.findall("law")) < 100:
                break
            page += 1
        except Exception as e:
            print(f"법률 검색 중 오류 발생: {e}")
            break
    # 디버깅을 위해 검색된 법률 목록 출력
    print(f"검색된 법률 수: {len(laws)}")
    for idx, law in enumerate(laws):
        print(f"{idx+1}. {law['법령명']}")
    return laws

def run_amendment_logic(find_word, replace_word):
    """개정문 생성 로직"""
    amendment_results = []
    skipped_laws = []  # 디버깅을 위해 누락된 법률 추적
    
    for idx, law in enumerate(get_law_list_from_api(find_word)):
        law_name = law["법령명"]
        mst = law["MST"]
        print(f"처리 중: {law_name} (MST: {mst})")  # 디버깅 추가
        
        xml_data = get_law_text_by_mst(mst)
        if not xml_data:
            skipped_laws.append(f"{law_name}: XML 데이터 없음")
            continue
            
        try:
            tree = ET.fromstring(xml_data)
        except ET.ParseError as e:
            skipped_laws.append(f"{law_name}: XML 파싱 오류 - {str(e)}")
            continue
            
        articles = tree.findall(".//조문단위")
        if not articles:
            skipped_laws.append(f"{law_name}: 조문단위 없음")
            continue
            
        print(f"조문 개수: {len(articles)}")  # 디버깅 추가
        
        chunk_map = defaultdict(list)
        
        # 법률에서 검색어의 모든 출현을 찾기 위한 디버깅 변수
        found_matches = 0
        
        # 법률의 모든 텍스트 내용을 검색
        for article in articles:
            # 조문
            조번호 = article.findtext("조문번호", "").strip()
            조가지번호 = article.findtext("조문가지번호", "").strip()
            조문식별자 = make_article_number(조번호, 조가지번호)
            
            # 조문내용에서 검색
            조문내용 = article.findtext("조문내용", "") or ""
            if find_word in 조문내용:
                found_matches += 1
                print(f"매치 발견: {조문식별자} 조문내용")  # 디버깅 추가
                tokens = re.findall(r'[가-힣A-Za-z0-9]+', 조문내용)
                for token in tokens:
                    if find_word in token:
                        chunk, josa, suffix = extract_chunk_and_josa(token, find_word)
                        replaced = chunk.replace(find_word, replace_word)
                        location = f"{조문식별자}"
                        chunk_map[(chunk, replaced, josa, suffix)].append(location)

            # 항 내용 검색
            for 항 in article.findall("항"):
                항번호 = normalize_number(항.findtext("항번호", "").strip())
                항번호_부분 = f"제{항번호}항" if 항번호 else ""
                
                항내용 = 항.findtext("항내용", "") or ""
                if find_word in 항내용:
                    found_matches += 1
                    print(f"매치 발견: {조문식별자}{항번호_부분} 항내용")  # 디버깅 추가
                    tokens = re.findall(r'[가-힣A-Za-z0-9]+', 항내용)
                    for token in tokens:
                        if find_word in token:
                            chunk, josa, suffix = extract_chunk_and_josa(token, find_word)
                            replaced = chunk.replace(find_word, replace_word)
                            location = f"{조문식별자}{항번호_부분}"
                            chunk_map[(chunk, replaced, josa, suffix)].append(location)
                
                # 호 내용 검색
                for 호 in 항.findall("호"):
                    호번호 = 호.findtext("호번호")
                    호내용 = 호.findtext("호내용", "") or ""
                    if find_word in 호내용:
                        found_matches += 1
                        print(f"매치 발견: {조문식별자}{항번호_부분}제{호번호}호 호내용")  # 디버깅 추가
                        tokens = re.findall(r'[가-힣A-Za-z0-9]+', 호내용)
                        for token in tokens:
                            if find_word in token:
                                chunk, josa, suffix = extract_chunk_and_josa(token, find_word)
                                replaced = chunk.replace(find_word, replace_word)
                                location = f"{조문식별자}{항번호_부분}제{호번호}호"
                                chunk_map[(chunk, replaced, josa, suffix)].append(location)

                    # 목 내용 검색
                    for 목 in 호.findall("목"):
                        목번호 = 목.findtext("목번호")
                        for m in 목.findall("목내용"):
                            if not m.text:
                                continue
                                
                            if find_word in m.text:
                                found_matches += 1
                                print(f"매치 발견: {조문식별자}{항번호_부분}제{호번호}호{목번호}목 목내용")  # 디버깅 추가
                                줄들 = [line.strip() for line in m.text.splitlines() if line.strip()]
                                for 줄 in 줄들:
                                    if find_word in 줄:
                                        tokens = re.findall(r'[가-힣A-Za-z0-9]+', 줄)
                                        for token in tokens:
                                            if find_word in token:
                                                chunk, josa, suffix = extract_chunk_and_josa(token, find_word)
                                                replaced = chunk.replace(find_word, replace_word)
                                                location = f"{조문식별자}{항번호_부분}제{호번호}호{목번호}목"
                                                chunk_map[(chunk, replaced, josa, suffix)].append(location)

        # 매칭된 내용이 있지만 chunk_map에 추가되지 않은 경우
        if found_matches > 0 and not chunk_map:
            print(f"경고: {law_name}에서 {found_matches}개 매치 발견되었으나 chunk_map에 추가되지 않음")
            
            # 디버깅: 검색어를 포함하는 부분을 출력하여 문제 원인 파악
            for article in articles:
                조문내용 = article.findtext("조문내용", "") or ""
                if find_word in 조문내용:
                    print(f"누락된 검색어 위치 (조문내용): {조문내용}")
                    print(f"토큰: {re.findall(r'[가-힣A-Za-z0-9]+', 조문내용)}")
                
                for 항 in article.findall("항"):
                    항내용 = 항.findtext("항내용", "") or ""
                    if find_word in 항내용:
                        print(f"누락된 검색어 위치 (항내용): {항내용}")
                        print(f"토큰: {re.findall(r'[가-힣A-Za-z0-9]+', 항내용)}")
                    
                    for 호 in 항.findall("호"):
                        호내용 = 호.findtext("호내용", "") or ""
                        if find_word in 호내용:
                            print(f"누락된 검색어 위치 (호내용): {호내용}")
                            print(f"토큰: {re.findall(r'[가-힣A-Za-z0-9]+', 호내용)}")
            
            skipped_laws.append(f"{law_name}: 검색어 {found_matches}개 발견되었으나 chunk_map에 추가되지 않음")
            
        if not chunk_map:
            continue
        
        # 디버깅: chunk_map 내용 출력
        print(f"chunk_map 항목 수: {len(chunk_map)}")
        for (chunk, replaced, josa, suffix), locations in chunk_map.items():
            print(f"chunk: '{chunk}', replaced: '{replaced}', josa: '{josa}', suffix: '{suffix}', locations: {locations}")
        
        # 같은 출력 형식을 가진 항목들을 그룹화
        rule_map = defaultdict(list)
        for (chunk, replaced, josa, suffix), locations in chunk_map.items():
            # 접미사 처리
            if suffix and suffix != "의":  # "의"는 개별 처리하지 않음
                orig_with_suffix = chunk + suffix
                replaced_with_suffix = replaced + suffix
                rule = apply_josa_rule(orig_with_suffix, replaced_with_suffix, josa)
            else:
                rule = apply_josa_rule(chunk, replaced, josa)
                
            rule_map[rule].extend(sorted(set(locations)))
        
        # 디버깅: rule_map 내용 출력
        print(f"rule_map 항목 수: {len(rule_map)}")
        for rule, locations in rule_map.items():
            print(f"rule: '{rule}', locations: {locations}")
        
        # 그룹화된 항목들을 정렬하여 출력
        result_lines = []
        for rule, locations in rule_map.items():
            loc_str = group_locations(sorted(set(locations)))
            result_lines.append(f"{loc_str} 중 {rule}")
            
        # 변경된 법률에 대한 개정문 생성
        if result_lines:
            prefix = chr(9312 + idx) if idx < 20 else f'({idx + 1})'
            amendment = f"{prefix} {law_name} 일부를 다음과 같이 개정한다.\n"
            amendment += "\n".join(result_lines)
            amendment_results.append(amendment)
        else:
            skipped_laws.append(f"{law_name}: 결과줄이 생성되지 않음")

    # 디버깅 정보 출력
    if skipped_laws:
        print("누락된 법률 목록:", skipped_laws)
        
    return amendment_results if amendment_results else ["⚠️ 개정 대상 조문이 없습니다."]

def extract_chunk_and_josa(token, searchword):
    """검색어를 포함하는 덩어리와 조사를 추출"""
    # 제외할 접미사 리스트 (덩어리에 포함시키지 않을 것들)
    suffix_exclude = ["의", "에", "에서", "으로서", "등", "에게", "만", "만을", "만이", "만은", "만에", "만으로"]
    
    # 처리할 조사 리스트
    josa_list = ["을", "를", "과", "와", "이", "가", "이나", "나", "으로", "로", "은", "는", "란", "이란", "라", "이라"]
    
    # 원본 토큰 저장
    original_token = token
    suffix = None
    
    # 디버깅 출력
    print(f"토큰 분석: '{token}', 검색어: '{searchword}'")
    
    # 검색어 자체가 토큰인 경우 바로 반환
    if token == searchword:
        print(f"정확히 일치: '{token}' == '{searchword}'")
        return token, None, None
    
    # 토큰에 검색어가 포함되어 있지 않으면 바로 반환
    if searchword not in token:
        print(f"검색어 미포함: '{searchword}' not in '{token}'")
        return token, None, None
    
    # 1. 접미사 제거 시도 (단, 이 접미사들은 덩어리에 포함시키지 않음)
    for s in sorted(suffix_exclude, key=len, reverse=True):
        if token.endswith(s) and len(token) > len(s):
            # 검색어와 접미사가 분리되어 있는지 확인
            if searchword + s == token:
                # 이 경우 검색어 자체를 반환하고 접미사는 별도로 처리
                print(f"검색어+접미사 패턴: '{searchword}' + '{s}' == '{token}'")
                return searchword, None, s
            elif token.endswith(searchword + s):
                # 뒤쪽에 접미사가 붙은 경우 (예: "검색어의")
                prefix = token[:-len(searchword + s)]
                # 접두어가 있는 경우 전체 토큰 반환
                if prefix:
                    print(f"접두어+검색어+접미사 패턴: '{prefix}' + '{searchword}' + '{s}' == '{token}'")
                    return token, None, None
                # 접두어가 없는 경우 검색어만 반환
                else:
                    print(f"검색어+접미사 패턴(후미): '{searchword}' + '{s}' == '{token}'")
                    return searchword, None, s
            print(f"접미사 '{s}' 발견됨: '{token}'")
            suffix = s
            token = token[:-len(s)]
            break
    
    # 2. 조사 확인
    josa = None
    chunk = token
    
    # 토큰이 "검색어 + 조사"로 정확히 구성된 경우
    for j in sorted(josa_list, key=len, reverse=True):
        if token == searchword + j:
            print(f"검색어+조사 패턴: '{searchword}' + '{j}' == '{token}'")
            return searchword, j, suffix
    
    # 3. 토큰 내의 위치 찾기
    start_pos = token.find(searchword)
    if start_pos != -1:
        end_pos = start_pos + len(searchword)
        
        # 검색어가 토큰의 끝에 있는 경우
        if end_pos == len(token):
            if start_pos == 0:  # 토큰이 정확히 검색어인 경우
                print(f"토큰 = 검색어: '{token}' == '{searchword}'")
                return searchword, None, suffix
            else:  # 검색어 앞에 다른 내용이 있는 경우
                print(f"접두어+검색어 패턴: '{token[:start_pos]}' + '{searchword}' == '{token}'")
                return token, None, suffix
                
        # 검색어 뒤에 조사가 있는지 확인
        for j in sorted(josa_list, key=len, reverse=True):
            if token[end_pos:].startswith(j):
                # 검색어 + 조사 앞에 다른 내용이 있는 경우
                if start_pos > 0:
                    print(f"접두어+검색어+조사 패턴: '{token[:start_pos]}' + '{searchword}' + '{j}' + '{token[end_pos+len(j):]}' == '{token}'")
                    return token, None, suffix
                # 검색어 + 조사 뒤에 다른 내용이 있는 경우
                elif end_pos + len(j) < len(token):
                    print(f"검색어+조사+접미사 패턴: '{searchword}' + '{j}' + '{token[end_pos+len(j):]}' == '{token}'")
                    return token, None, suffix
                # 정확히 "검색어 + 조사"인 경우
                else:
                    print(f"검색어+조사 패턴(후미): '{searchword}' + '{j}' == '{token}'")
                    return searchword, j, suffix
    
    # 4. 토큰이 검색어를 포함하지만 조건에 맞지 않는 경우 토큰 전체 반환
    print(f"기타 패턴 (토큰 전체 반환): '{token}'")
    return token, None, suffix
