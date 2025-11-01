import sqlite3
import pandas as pd
import json
import os # 1. os 임포트
from dotenv import load_dotenv # 2. load_dotenv 임포트
import google.generativeai as genai # Gemini API 라이브러리
import random

# --- 1. 설정 ---
DB_PATH = 'recipe_db.sqlite'

YOUR_API_KEY = os.getenv("GEMINI_API_KEY")

# ----------------------------------------------------
# [★] 추천받을 사용자를 ID로 선택하세요 (1~5)
# (1: 김다이어트, 2: 박벌크업, 3: 이채식, 4: 최바쁨, 5: 오영양)
# ----------------------------------------------------
TARGET_USER_ID = 2

# --- 2. DB 접근 및 프로필 파싱 함수 ---

def get_user_profile(conn, user_id):
    """'users' 테이블에서 특정 사용자 프로필을 불러옵니다."""
    try:
        profile_df = pd.read_sql(
            f"SELECT * FROM users WHERE user_id = {user_id}", 
            conn
        )
        if profile_df.empty: 
            print(f"오류: user_id {user_id}를 찾을 수 없습니다.")
            return None
        return profile_df.to_dict('records')[0]
    except Exception as e:
        print(f"프로필 로드 오류: {e}")
        return None

# -----------------------------------------------------------------
# [신규] 1차 필터링을 위한 '지식 베이스 (Knowledge Base)'
# -----------------------------------------------------------------
# 사용자의 프로필 용어(Key)를 실제 재료 키워드(Value)로 '번역'
# 이 맵을 확장하면 할수록 1차 필터링이 강력해집니다.
RESTRICTION_MAP = {
    # ==================================================
    # 1. 한국 표준 알레르기 유발 물질 (19종)
    # ==================================================
    
    # --- 1. 난류 (알류) ---
    '난류': ['계란', '달걀', '메추리알', '계란말이', '지단', '계란찜', '스크램블', '에그'],
    
    # --- 2. 우유 ---
    '우유': [
        '우유', '유제품', '치즈', '버터', '요거트', '요플레', '생크림', '크림', 
        '마가린', '연유', '분유', '카제인', '유청', '사워크림', '크림치즈'
    ],
    
    # --- 3. 메밀 ---
    '메밀': ['메밀', '메밀국수', '메밀가루', '메밀묵'],
    
    # --- 4. 땅콩 ---
    '땅콩': ['땅콩', '피넛', '땅콩버터', '땅콩가루'],
    
    # --- 5. 대두 ---
    '대두': [
        '대두', '콩', '두부', '된장', '간장', '고추장', '청국장', '콩나물', '순두부', 
        '유부', '콩가루', '두유', '춘장', '미소', '템페', '콩기름'
    ],
    
    # --- 6. 밀 ---
    '밀': [
        '밀', '밀가루', '부침가루', '빵가루', '수제비', '칼국수', '면', '파스타', 
        '라면', '국수', '스파게티', '빵', '케이크', '시리얼', '글루텐', '또띠아'
    ],
    
    # --- 7. 잣 ---
    '잣': ['잣', '잣가루'],
    
    # --- 8. 호두 ---
    '호두': ['호두', '월넛', '호두과자'],
    
    # --- 9. 게 ---
    '게': ['게', '크랩', '꽃게', '대게', '킹크랩', '게맛살', '맛살'],
    
    # --- 10. 새우 ---
    '새우': ['새우', '대하', '새우젓', '크릴', '칵테일새우', '건새우', '깐새우'],
    
    # --- 11. 오징어 ---
    '오징어': ['오징어', '꼴뚜기', '물오징어', '마른오징어', '오징어채'],
    
    # --- 12. 고등어 ---
    '고등어': ['고등어', '삼치', '방어'], # 등푸른 생선
    
    # --- 13. 조개류 ---
    '조개류': [
        '조개', '굴', '전복', '홍합', '가리비', '바지락', '꼬막', '소라', '키조개', 
        '백합', '동죽', '재첩', '관자'
    ],
    
    # --- 14. 복숭아 ---
    '복숭아': ['복숭아', '황도', '백도', '넥타린'],
    
    # --- 15. 토마토 ---
    '토마토': ['토마토', '방울토마토', '케첩', '토마토소스', '토마토페이스트', '파스타소스'],
    
    # --- 16. 닭고기 ---
    '닭고기': [
        '닭', '치킨', '닭가슴살', '닭다리', '닭발', '닭날개', '삼계탕', '닭볶음탕', 
        '닭갈비', '닭강정', '닭꼬치'
    ],
    
    # --- 17. 돼지고기 ---
    '돼지고기': [
        '돼지', '돈육', '등뼈', '베이컨', '햄', '소시지', '삼겹살', '목살', '항정살', 
        '족발', '수육', '등심', '안심', '갈매기살', '앞다리살', '뒷다리살'
    ],
    
    # --- 18. 쇠고기 (소고기) ---
    '쇠고기': [
        '소', '쇠', '한우', '육우', '우삼겹', '갈비', '사골', '소꼬리', '양지', 
        '차돌박이', '불고기감', '등심', '안심', '채끝', '설도', '우둔', '육회'
    ],
    
    # --- 19. 아황산류 ---
    '아황산류': ['와인', '건포도', '건과일', '표백제', '보존제', '아황산나트륨'], # 식품첨가물로 주로 사용됨

    # ==================================================
    # 2. 유용한 종합 카테고리
    # ==================================================
    
    # --- 견과류 종합 ---
    '견과류': [
        '땅콩', '피넛', '땅콩버터', '잣', '호두', '월넛', '아몬드', '캐슈넛', 
        '마카다미아', '피스타치오', '헤이즐넛', '견과'
    ],

    # --- 갑각류 종합 (게 + 새우) ---
    '갑각류': [
        '게', '크랩', '꽃게', '맛살', '새우', '대하', '새우젓', '가재', '랍스터', 
        '크릴'
    ],

    # --- 생선/어류 종합 ---
    '생선': [
        '생선', '고등어', '갈치', '조기', '참치', '연어', '꽁치', '생태', '명태', '동태', 
        '황태', '북어', '코다리', '임연수', '가자미', '삼치', '방어', '전어', '멸치'
    ],

    # --- 해산물 종합 (생선 + 갑각류 + 조개류 + 기타) ---
    '해산물': [
        # 생선
        '생선', '고등어', '갈치', '조기', '참치', '연어', '꽁치', '생태', '명태', '동태', 
        '황태', '북어', '코다리', '멸치',
        # 갑각류
        '게', '크랩', '꽃게', '맛살', '새우', '대하', '새우젓', '가재', '랍스터',
        # 조개류
        '조개', '굴', '전복', '홍합', '가리비', '바지락', '꼬막', '소라',
        # 기타
        '어묵', '해물', '오징어', '문어', '쭈꾸미', '낙지', '꼴뚜기', '멍게', '해삼', '날치알'
    ],

    # --- 육류 종합 (돼지 + 소 + 닭 + 기타) ---
    '육류': [
        # 돼지
        '돼지', '돈육', '베이컨', '햄', '소시지', '삼겹살', '목살', '족발', '수육',
        # 소
        '소', '쇠', '한우', '육우', '갈비', '사골', '소꼬리', '차돌박이', '불고기감', '육회',
        # 닭
        '닭', '치킨', '닭가슴살', '닭다리', '삼계탕', '닭볶음탕',
        # 기타
        '오리', '양', '염소', '육류', '고기'
    ],
    
    # ==================================================
    # 3. 특수 식이 제한 (채식 등)
    # ==================================================

    # --- 채식 (Vegetarian) ---
    '채식': [
        # 육류
        '돼지', '돈육', '베이컨', '햄', '소시지', '삼겹살', '소', '쇠', '한우', '육우', '갈비', '사골',
        '닭', '치킨', '오리', '양', '육류', '고기',
        # 어류
        '생선', '고등어', '갈치', '조기', '참치', '연어', '꽁치', '생태', '명태', '동태', '황태', '북어',
        # 해산물
        '어묵', '맛살', '해물', '해산물', '오징어', '문어', '조개', '굴', '전복', '홍합', '쭈꾸미', '낙지',
        # 숨은 동물성 재료 (CSV 샘플 확인 후 강화)
        '멸치', '액젓', '까나리', '새우젓', '육수', '스톡', '다시다', '사골육수', '멸치육수', 
        '치킨스톡', '비프스톡', '코인육수', '한알육수' # '육수' 키워드 자체가 강력하게 작용
    ],
    
    # --- 비건 (Vegan) ---
    '비건': [
        # 채식 키워드 모두 포함
        '돼지', '돈육', '베이컨', '햄', '소시지', '삼겹살', '소', '쇠', '한우', '육우', '갈비', '사골',
        '닭', '치킨', '오리', '양', '육류', '생선', '고등어', '갈치', '조기', '참치', '연어', '꽁치', '생태',
        '명태', '동태', '황태', '북어', '어묵', '맛살', '해물', '해산물', '오징어', '문어', '조개', '굴',
        '전복', '홍합', '쭈꾸미', '낙지', '멸치', '액젓', '까나리', '새우젓', '육수', '스톡', '다시다', 
        '사골육수', '멸치육수', '치킨스톡',
        # 유제품/난류
        '계란', '달걀', '메추리알', '난류', '알',
        '우유', '치즈', '버터', '요거트', '생크림', '유제품', '크림',
        # 기타 동물성
        '꿀', '젤라틴'
    ]
}

# -----------------------------------------------------------------
# [강화된] 1차 필터링 함수
# -----------------------------------------------------------------

def parse_restrictions(profile):
    """
    (강화) 프로필을 '번역 맵(RESTRICTION_MAP)'을 사용해
    실제 필터링할 키워드 리스트를 생성합니다.
    """
    
    # 중복 키워드를 자동으로 제거하기 위해 set 사용
    final_keyword_set = set()
    
    # --- 1. DB 프로필에서 원시 제약어 추출 ---
    raw_allergies = profile['restrictions_allergies']
    raw_other = profile['restrictions_other']
    
    all_raw_terms = []
    if raw_allergies != '없음':
        all_raw_terms.extend([term.strip() for term in raw_allergies.split(',')])
        
    if raw_other != '없음':
        # '종교(돼지고기 x)' -> '돼지고기' 추출
        if '돼지고기' in raw_other:
            all_raw_terms.append('돼지고기')
        if '이슬람교' in raw_other:
            all_raw_terms.append('돼지고기')
        if '힌두교' in raw_other:
            all_raw_terms.append('소고기')
        # '채식, 비건' -> '채식', '비건' 추출
        if '채식' in raw_other:
            all_raw_terms.append('채식')
        if '비건' in raw_other:
            all_raw_terms.append('비건')
    
    # --- 2. '번역 맵'을 사용해 키워드 확장 ---
    # (예: '게' -> ['게', '크랩', '꽃게', '맛살'])
    
    # 중복된 원시 제약어 제거 (예: 이채식은 알레르기에 '닭고기', 제약에 '채식'이 둘 다 있음)
    unique_raw_terms = list(set(all_raw_terms))
    
    for term in unique_raw_terms:
        if term in RESTRICTION_MAP:
            # 맵에 정의된 키워드 묶음을 추가
            final_keyword_set.update(RESTRICTION_MAP[term])
        else:
            # 맵에 없는 단어(예: 복숭아)는 원본 단어 자체를 키워드로 추가
            final_keyword_set.add(term)
            
    final_list = list(final_keyword_set)
    
    # [로그 강화] 몇 개의 키워드가 생성되었는지 확인
    print(f"✅ (1차-강화) 프로필 용어 {unique_raw_terms}(으)로부터")
    print(f"   -> 총 {len(final_list)}개의 금지 재료 키워드를 생성했습니다.")
    # (너무 길면 일부만 출력)
    if len(final_list) > 20:
        print(f"   (예: {final_list[:20]}...)")
    else:
        print(f"   -> {final_list}")
        
    return final_list

def recommend_recipes_by_filter(conn, profile, restrictions):
    """
    (1차 필터링) 'recipes' 테이블에서 금지 재료 + 시간 제약을 필터링합니다.
    (이 함수는 입력(restrictions)이 강력해졌으므로, 로직 수정은 거의 필요 없음)
    """
    try:
        # DB에서 모든 레시피 로드 (AI로 시간 채우기 전 원본 DB)
        # (만약 1단계에서 recipes_imputed_xgb.csv를 DB에 덮어썼다면
        #  CKG_TIME_NM을 여기서 필터링할 수도 있습니다)
        
        # [참고] recipes_imputed_xgb.csv를 DB에 덮어쓰지 않았으므로
        # 1단계의 원본 DB(recipes)를 읽어오는 것이 맞습니다.
        all_recipes_df = pd.read_sql("SELECT * FROM recipes", conn)
        
        # --- 1. 재료 필터링 ---
        filtered_indices = [] # 합격한 레시피의 인덱스
        
        for index, row in all_recipes_df.iterrows():
            
            # [수정] 더 구체적인 예외 처리
            try:
                # ingredients_json 컬럼의 문자열을 딕셔너리로 변환
                ingredients_dict = json.loads(row['ingredients_json'])
            except (json.JSONDecodeError, TypeError):
                # JSON 형식이 아니거나 NaN인 경우, 안전하게 필터링(제외)
                continue 
                
            ingredient_names = ingredients_dict.keys()
            
            is_safe = True # 일단 안전하다고 가정
            for restriction in restrictions:
                for name in ingredient_names:
                    # [핵심 로직] '멸치'가 '국물용 멸치'에 포함되는지 검사
                    if restriction in name:
                        is_safe = False 
                        break 
                if not is_safe:
                    break 
            
            if is_safe:
                filtered_indices.append(index)
                
        material_filtered_df = all_recipes_df.loc[filtered_indices]
        print(f"✅ (1차-재료) {len(all_recipes_df)}개 중 {len(material_filtered_df)}개 레시피가 안전합니다.")
        
        # -----------------------------------------------------------------
        # [수정된 부분] 2. 시간 필터링 (30분 / 60분 제약 처리)
        # -----------------------------------------------------------------
        
        other_restrictions = profile['restrictions_other']
        allowed_times = []
        time_limit_str = "제약 없음"

        if '조리시간 30분 이내' in other_restrictions:
            # 30분 제약이 걸리면, 60분 제약은 무시 (더 강력한 조건)
            allowed_times = ['30분이내', '15분이내', '10분이내', '5분이내']
            time_limit_str = "30분 이내"
            
        elif '조리시간 60분 이내' in other_restrictions:
            # 30분 제약은 없지만 60분 제약이 있는 경우
            allowed_times = ['60분이내', '30분이내', '15분이내', '10분이내', '5분이내']
            time_limit_str = "60분 이내"
        
        # allowed_times 리스트가 비어있지 않다면 (즉, 시간 제약이 있다면)
        if allowed_times:
            print(f"시간 제약({time_limit_str})으로 필터링을 시작합니다...")
            
            # CKG_TIME_NM 컬럼값이 allowed_times 리스트에 포함된 것만 선택
            # (DB 원본의 NaN 값은 isin()에서 자동으로 False 처리되어 제외됨)
            final_filtered_df = material_filtered_df[
                material_filtered_df['CKG_TIME_NM'].isin(allowed_times)
            ]
            print(f"✅ (1차-시간) {len(final_filtered_df)}개 레시피만 남김.")
        else:
            # 시간 제약이 없으면(allowed_times가 비어있으면) 재료 필터링 결과 그대로 사용
            print("시간 제약 없음. 재료 필터링 결과만 사용합니다.")
            final_filtered_df = material_filtered_df
            
        return final_filtered_df
    
    except Exception as e:
        print(f"필터링 중 오류: {e}")
        return pd.DataFrame()
# --- 3. (신규) 4단계: Gemini API 호출 함수 (수정된 버전) ---

def get_gemini_recommendation(api_key, profile, candidate_recipes):
    """
    (2차 추천) Gemini API를 호출하여 최종 식단을 추천받습니다.
    (모델명 및 프롬프트 로직 수정)
    """
    try:
        genai.configure(api_key=api_key)
        
        # 모델명
        model = genai.GenerativeModel('models/gemini-pro-latest') 
        
        # 후보 레시피 목록을 텍스트로 변환
        recipe_list_str = "\n".join([
            f"- {row['RCP_TTL']} (조리법: {row['CKG_MTH_ACTO_NM']}, 소요시간: {row['CKG_TIME_NM']})"
            for _, row in candidate_recipes.iterrows()
        ])
        
        # 사용자 프로필을 텍스트로 변환
        profile_str = f"""
        - 사용자명: {profile['username']}
        - 선호 음식: {profile['preferences']}
        - 달성 목표: {profile['goals']}
        - (참고) 기타 제약: {profile['restrictions_other']}
        """

        # [수정 2] 프롬프트 예시를 더 일반적이고 강력하게 변경
        prompt = f"""
        당신은 BobFit의 식단 코치 전문 영양사입니다. 
        '{profile['username']}' 님을 위한 일주일치 저녁 식단 7개를 추천해야 합니다.

        [사용자 프로필]
        {profile_str}

        [추천 대상 레시피 후보 목록 (최대 100개)]
        {recipe_list_str}

        [요청 사항]
        1. 위 후보 목록 중에서 7개의 레시피를 선택해주세요.
        2. 선택 기준은 사용자의 [달성 목표]와 [선호 음식]을 최우선으로 고려해야 합니다.
        
        3. [중요] 사용자의 [달성 목표]와 [기타 제약]을 반드시 확인하세요.
           - (예: 목표에 '다이어트'가 있다면) 칼로리가 낮거나 건강한 조리법(찜, 무침, 샐러드) 위주로 선택하세요.
           - (예: 목표에 '단백질 섭취'가 있다면) '육류', '생선', '두부'가 포함된 메뉴를 우선 고려하세요.
           - (예: 제약에 '조리시간 30분 이내'가 있다면) 후보 목록의 '소요시간'을 확인하여 '30분이내', '15분이내' 등 조건에 맞는 레시피만 골라야 합니다.
           
        4. 추천 결과는 아래 [출력 형식]을 반드시 지켜주세요.

        [출력 형식]
        1. [레시피명]: 이 레시피를 추천하는 이유 (달성 목표/기호와 연결지어 설명)
        2. [레시피명]: 추천 이유
        ...
        7. [레시피명]: 추천 이유
        """
        
        print("\nGemini API에 추천을 요청합니다...")
        response = model.generate_content(prompt)
        
        return response.text

    except Exception as e:
        print(f"❌ Gemini API 오류: {e}")
        return None

# (파일의 나머지 부분(1, 2, 4단계)은 그대로 두시면 됩니다.)

# --- 4. 메인 코드 실행 ---
if __name__ == "__main__":
    
    if "YOUR_API_KEY" in YOUR_API_KEY:
        print("="*50)
        print("❌ 오류: 스크립트 10줄의 YOUR_API_KEY를")
        print("Google AI Studio에서 발급받은 본인의 키로 변경해주세요.")
        print("="*50)
        exit()

    conn = None
    try:
        conn = sqlite3.connect(DB_PATH)
        print(f"'{DB_PATH}' 연결 성공.")
        
        # [1단계] 사용자 프로필 로드 (TARGET_USER_ID 기준)
        profile = get_user_profile(conn, TARGET_USER_ID)
        if not profile:
            exit()
            
        print(f"\n--- {profile['username']}님(ID:{TARGET_USER_ID})을 위한 추천 프로세스 시작 ---")
        print(f"목표: {profile['goals']} | 선호: {profile['preferences']}")
        
        # [2단계] 1차 필터링 (제약 조건 + 시간)
        restrictions = parse_restrictions(profile)
        # (수정) profile 객체도 함께 전달
        filtered_recipes = recommend_recipes_by_filter(conn, profile, restrictions)
        
        if filtered_recipes.empty:
            print("필터링 결과, 추천할 수 있는 레시피가 없습니다.")
        else:
            # [3단계] 2차 추천 (Gemini API)
            
            # 100개 샘플링
            sample_size = min(100, len(filtered_recipes))
            candidate_recipes = filtered_recipes.sample(n=sample_size, random_state=42)
            print(f"✅ (2차) {len(candidate_recipes)}개 레시피를 샘플링하여 AI 후보로 선정.")
            
            # [4단계] AI 호출
            recommendation_text = get_gemini_recommendation(
                YOUR_API_KEY, 
                profile, 
                candidate_recipes
            )
            
            if recommendation_text:
                print("\n" + "="*25)
                print(f"  Gemini API가 추천하는")
                print(f" '{profile['username']}' 님을 위한 주간 식단")
                print("="*25)
                print(recommendation_text)

    except Exception as e:
        print(f"전체 프로세스 오류: {e}")
        
    finally:
        if conn:
            conn.close()
            print(f"\n'{DB_PATH}' 연결 종료.")