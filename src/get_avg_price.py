import requests  # API 요청을 보내는 라이브러리
import json      # JSON 데이터를 다루는 라이브러리
import sys       # 터미널에서 입력값을 받기 위한 라이브러리
import os

# 1. API 키 설정
CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")

# 2. 검색할 상품명 설정 (예: "떡볶이떡")
#    터미널에서 입력 받기 (예: python get_price_avg.py 떡볶이떡)
if len(sys.argv) > 1:
    keyword = sys.argv[1]
else:
    keyword = "떡볶이떡"  # 기본값

print(f"'{keyword}' 검색 결과 (상위 5개) 가격 분석")

# 3. API 요청 설정
url = "https://openapi.naver.com/v1/search/shop.json"

# 요청 헤더: "나 이런 사람이야" (인증 정보)
headers = {
    "X-Naver-Client-Id": CLIENT_ID,
    "X-Naver-Client-Secret": CLIENT_SECRET
}

# 요청 파라미터: "이런 걸 원해"
# display=5 : 5개만 보여줘
# sort=sim : 정확도순 (기본값)
params = {
    "query": keyword,
    "display": 5 
}

# 4. API 호출
try:
    response = requests.get(url, headers=headers, params=params)
    
    # 5. 응답 처리
    if response.status_code == 200:
        data = response.json()  # 응답 결과를 JSON 객체로 변환
        
        prices = [] # 가격을 저장할 리스트
        
        # 'items' 리스트에서 상품 정보를 하나씩 꺼내기
        for item in data['items']:
            # 'lprice' (최저가)를 가져옴
            price_str = item['lprice']
            
            # 가격(문자열)을 숫자(int)로 변환
            price_int = int(price_str) 
            prices.append(price_int)
            
            # 상품명과 가격 출력
            # <b> 태그 제거 (간단한 처리)
            title = item['title'].replace("<b>", "").replace("</b>", "")
            print(f"- 상품명: {title}")
            print(f"  가격: {price_int:,}원") # 1000단위 콤마

        # 6. 평균 계산
        if prices: # prices 리스트에 값이 있다면
            average_price = sum(prices) / len(prices)
            print("---")
            print(f"📊 상위 5개 상품 평균 가격: {average_price:,.0f}원")
        else:
            print("검색 결과에서 가격 정보를 찾을 수 없습니다.")

    else:
        # API 호출 실패
        print(f"Error: {response.status_code}")
        print(response.text)

except Exception as e:
    print(f"오류 발생: {e}")