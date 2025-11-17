import requests
import json
import sys
import os
from dotenv import load_dotenv # .env 파일용

# .env 파일에서 API 키 불러오기
load_dotenv()

# 1. API 키 설정 (전역 변수)
CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")

# -----------------------------------------------------------
# [신규] 2. 스크립트 로직을 '함수'로 변경
# -----------------------------------------------------------
def get_lowest_price(keyword, display=3):
    """
    네이버 쇼핑 API를 호출하여 상위 display개 중 최저가를 반환합니다.
    """
    
    if not CLIENT_ID or not CLIENT_SECRET:
        # print("경고: NAVER_CLIENT_ID가 .env 파일에 없습니다.")
        return 0 # API 키가 없으면 0원 반환
        
    url = "https://openapi.naver.com/v1/search/shop.json"
    headers = {
        "X-Naver-Client-Id": CLIENT_ID,
        "X-Naver-Client-Secret": CLIENT_SECRET
    }
    params = {
        "query": keyword,
        "display": display, # (수정) 상위 3개만 비교 (속도 향상)
        "sort": "sim" 
    }

    try:
        response = requests.get(url, headers=headers, params=params)
        
        if response.status_code == 200:
            data = response.json()
            lowest_price = float('inf') 

            if not data['items']:
                # print(f"'{keyword}' 검색 결과 없음.")
                return 0 # 검색 결과 없으면 0원

            for item in data['items']:
                price_int = int(item['lprice'])
                if price_int < lowest_price:
                    lowest_price = price_int
            
            # (최종 최저가)
            if lowest_price == float('inf'):
                return 0 # (혹시 모를 예외)
            
            return lowest_price # (성공) 최저가(int) 반환

        else:
            # API 호출 실패
            # print(f"API Error: {response.status_code}")
            return 0 # 오류 시 0원 반환

    except Exception as e:
        # print(f"API 호출 오류: {e}")
        return 0 # 오류 시 0원 반환

# -----------------------------------------------------------
# [기존] 3. 터미널에서 직접 실행할 때만 작동하는 부분
# -----------------------------------------------------------
if __name__ == "__main__":
    
    # .env 파일에 키 변수명을 NAVER_CLIENT_ID로 저장하세요!
    if not CLIENT_ID or not CLIENT_SECRET:
        print("="*50)
        print("❌ 오류: .env 파일에 NAVER_CLIENT_ID 또는 NAVER_CLIENT_SECRET이 없습니다.")
        print("1. .env 파일을 만드세요.")
        print("2. 네이버 개발자 센터에서 발급받은 ID와 Secret을 추가하세요:")
        print("   NAVER_CLIENT_ID=\"...[ID]...\"")
        print("   NAVER_CLIENT_SECRET=\"...[SECRET]...\"")
        print("="*50)
        sys.exit()

    if len(sys.argv) > 1:
        keyword = sys.argv[1]
    else:
        keyword = "떡볶이떡"

    print(f"'{keyword}' 검색 결과 (상위 3개) 최저가 분석")
    
    # 2단계에서 만든 함수를 테스트
    price = get_lowest_price(keyword, display=3)
    
    if price > 0:
        print("--------------------------")
        print("📊 [최저가]")
        print(f"가 격: {price:,}원")
    else:
        print("최저가 검색에 실패했습니다.")