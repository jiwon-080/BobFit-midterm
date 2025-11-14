# 파일명: get_price_min.py

import requests
import json
import sys
import os

# 1. API 키 설정 (본인의 키로 변경하세요)
CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")

# 2. 검색할 상품명 설정
if len(sys.argv) > 1:
    keyword = sys.argv[1]
else:
    keyword = "떡볶이떡"  # 기본값

print(f"'{keyword}' 검색 결과 (상위 5개) 최저가 분석")

# 3. API 요청 설정
url = "https://openapi.naver.com/v1/search/shop.json"
headers = {
    "X-Naver-Client-Id": CLIENT_ID,
    "X-Naver-Client-Secret": CLIENT_SECRET
}
params = {
    "query": keyword,
    "display": 5,
    "sort": "sim" # 정확도순
}

# 4. API 호출
try:
    response = requests.get(url, headers=headers, params=params)
    
    # 5. 응답 처리
    if response.status_code == 200:
        data = response.json()
        
        # 최저가 정보를 저장할 변수 초기화
        # float('inf')는 '무한대'를 의미. 어떤 가격이든 이것보다 작음.
        lowest_price = float('inf') 
        lowest_title = ""

        if not data['items']:
            print("검색 결과가 없습니다.")
            sys.exit() # 프로그램 종료

        print("--- [검색된 상품 목록] ---")
        
        # 'items' 리스트에서 상품 정보를 하나씩 꺼내기
        for item in data['items']:
            price_str = item['lprice']
            price_int = int(price_str)
            title = item['title'].replace("<b>", "").replace("</b>", "")
            
            # 상품명과 가격 출력
            print(f"- {title} ({price_int:,}원)")

            # 6. 최저가 비교
            # 현재 상품 가격이, 지금까지 기억된 최저가보다 더 싸다면?
            if price_int < lowest_price:
                lowest_price = price_int # 최저가를 이 상품 가격으로 교체
                lowest_title = title      # 최저가 상품명을 이 상품명으로 교체

        # 7. 최종 최저가 출력
        print("--------------------------")
        print("📊 [최저가 상품]")
        print(f"상품명: {lowest_title}")
        print(f"가 격: {lowest_price:,}원")

    else:
        # API 호출 실패
        print(f"Error: {response.status_code}")
        print(response.text)

except Exception as e:
    print(f"오류 발생: {e}")