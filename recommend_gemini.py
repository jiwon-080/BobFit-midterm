import sqlite3
import pandas as pd
import json
import os # 1. os 임포트
from dotenv import load_dotenv # 2. load_dotenv 임포트
import google.generativeai as genai # Gemini API 라이브러리
import random

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np

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
        
        # ---------------------------------------------------------
        # [수정] 3. 예산 필터링 (정적 숫자 budget 사용)
        # ---------------------------------------------------------
        user_budget = profile.get('budget', 0) # DB에서 가져온 숫자 (없으면 0)
    
        if user_budget and user_budget > 0:
            # [전략] 네이버 가격은 '대용량(묶음)' 기준일 수 있으므로, 
            # 한 끼 예산(user_budget)의 3배까지는 후보군에 포함시켜 줍니다.
            # (예: 내 예산 1만원 -> 재료비 합계 2만원짜리(대용량) 레시피도 일단 통과)
            budget_limit = user_budget * 3
        
            final_filtered_df = final_filtered_df[
                (final_filtered_df['estimated_price'] <= budget_limit) | 
                (final_filtered_df['estimated_price'].isnull()) |
                (final_filtered_df['estimated_price'] == 0)
            ]
            print(f"💰 (1차-예산) {user_budget:,}원 예산 적용 -> 대용량 기준 {budget_limit:,}원 이하 {len(final_filtered_df)}개 남김.")
    
        else:
            print("💰 (1차-예산) 예산 제약 없음.")
        
        return final_filtered_df
    
    except Exception as e:
        print(f"필터링 중 오류: {e}")
        return pd.DataFrame()
    


# [수정] 3. 2차 (Gemini) 추천 함수 (최종 완성본)
def get_gemini_recommendation(api_key, profile, candidate_recipes, today_str, mood, free_text):
    """
    (2차 추천) 모든 상황(기분, 예산, 목표)을 고려하여 Gemini API로 최종 식단을 생성합니다.
    """
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('models/gemini-flash-latest') 
        
        # 1. 후보 레시피 목록 텍스트 생성 (가격 정보 포함)
        recipe_list_lines = []
        for _, row in candidate_recipes.iterrows():
            # 가격 정보 포맷팅 (0원이면 '정보 없음')
            price_info = f"{row['estimated_price']:,}원" if row.get('estimated_price', 0) > 0 else "정보 없음"
            
            # 재료 정보 포맷팅 (JSON -> 읽기 편한 텍스트로 변환)
            try:
                ing_dict = json.loads(row['ingredients_json'])
                # 너무 길면 AI가 힘들어하므로, 재료명만 나열하거나 주요 재료만 포함
                # 예: "두부 1모, 대파 1단..." -> "두부, 대파..."
                ingredients_info = ", ".join(list(ing_dict.keys())[:10]) # 최대 10개 재료만
            except:
                ingredients_info = "재료 정보 없음"
            
            line = (
                f"- [{row['RCP_TTL']}] "
                f"요리명: {row['CKG_NM']}, 조리법: {row['CKG_MTH_ACTO_NM']},"
                f"소요시간: {row['CKG_TIME_NM']}, 재료비(대용량): {price_info},"
                f"주재료: {ingredients_info})" # <-- AI가 이걸 보고 칼로리를 추정함
            )
            recipe_list_lines.append(line)
        
        recipe_list_str = "\n".join(recipe_list_lines)
        
        # 2. 사용자 프로필 텍스트 생성 (예산 포함)
        user_budget = profile.get('budget', 0)
        budget_str = f"{user_budget:,}원" if user_budget > 0 else "제한 없음"
        
        profile_str = f"""
        - 사용자명: {profile['username']}
        - 선호 음식: {profile['preferences']}
        - 달성 목표: {profile['goals']}
        - 알레르기: {profile['restrictions_allergies']}
        - 기타 제약: {profile['restrictions_other']}
        - 한 끼 예산: {budget_str}
        """

        # 3. 동적 컨텍스트 생성 (기분/요청)
        context_str = f"- 오늘은 {today_str}입니다."
        if mood != "-":
            context_str += f"\n- 사용자의 현재 기분: {mood}"
        if free_text:
            context_str += f"\n- 사용자의 추가 요청: {free_text}"
        else:
            context_str += "\n- 사용자의 추가 요청: 없음"

        # ------------------------------------------------------------------
        # [핵심] 최종 통합 프롬프트
        # ------------------------------------------------------------------
        prompt = f"""
        당신은 'BobFit'의 AI 식단 코치이자 전문 영양사입니다.
        아래 제공된 정보를 종합하여 사용자에게 최적화된 **오늘의 아침/점심/저녁 식단(후보 총 9개)**을 추천해주세요.

        # 1. 사용자 프로필
        {profile_str}

        # 2. 오늘의 상황 (Context)
        {context_str}

        # 3. 추천 대상 레시피 후보 목록 (엄선된 100개)
        {recipe_list_str}

        ---
        # [필수 요청 사항]

        **1. 추천 밸런스 (Balance)**
        - 추천하는 7개의 메뉴는 다음 두 가지 기준을 적절히 섞어서 구성하세요.
          - 사용자의 [달성 목표](예: 다이어트, 단백질 증가, 영양 균형)에 충실한 건강 메뉴
          - [오늘의 상황](기분, 날씨, 요청)을 위로하거나 만족시키는 메뉴
        
        **2. 제약 조건 준수 (Constraints)**
        - 사용자의 [알레르기] 및 [기타 제약](채식, 종교 등)을 **절대적으로 준수**하세요. 위 후보 목록은 이미 1차 필터링 되었으나, AI인 당신이 한 번 더 검토하세요.
        
        **3. 예산 고려 (Budget)**
        - 사용자의 [한 끼 예산] 제한이 있다면 확인하세요.
        - 후보 목록의 '재료비(대용량)'는 식재료를 묶음으로 샀을 때의 총가격입니다. 
        - 따라서 **실제 1인분 1끼 비용은 표시된 가격의 약 1/5 ~ 1/10 수준**으로 저렴하다고 판단하고, 이를 감안하여 예산 범위 내에서 합리적인 메뉴를 고르세요.

        **4. [★매우 중요 - 출력 형식]**
        - 레시피 제목은 반드시 후보 목록에 있는 **대괄호 `[]` 안의 원본 제목 그대로** 작성해야 합니다. (토글 매칭을 위해 필수)
        (잘못된 예: "순두부찌개", "맛있는 된장찌개")
        (올바른 예: "[바지락 순두부 찌개 끓이는 법]", "[차돌박이 된장찌개]")
        
        - **[열량 추정]** 후보 목록에 있는 **'주재료' 정보**를 바탕으로 대략적인 열량(kcal)을 추정하세요.
          - 표기의 편리를 위해 반드시 **1인분 기준으로 추정한 열량**을 메뉴 이름의 아래 줄에 `(약 XXX kcal)` 형식으로 명시하세요.
        
        - 각 추천 메뉴 사이에는 **반드시 빈 줄(줄바꿈 2번)**을 넣어주세요.
        
        - 설명은 Markdown 형식을 사용하여 가독성 있게 작성하세요.

        ---
        # [출력 예시]
        
        안녕하세요, {profile['username']}님! BobFit 영양사입니다.
        (인사말 및 추천 컨셉 설명...)

        아침 1. **[원본 레시피 제목 그대로]**:
           (약 XXX kcal)
           추천 이유: 사용자의 '다이어트' 목표에 맞춰 단백질이 풍부하고...

        아침 2. **[원본 레시피 제목 그대로]**: 
           (약 XXX kcal)
           추천 이유: 오늘 '우울함'을 느끼시는 고객님을 위해 따뜻한...
           
        아침 3. **[원본 레시피 제목 그대로]**: 
           (약 XXX kcal)
           추천 이유: 사용자의 '근육 증가' 목표에 맞춰 고단백...
           
        점심 1. **[원본 레시피 제목 그대로]**:
           (약 XXX kcal)
           추천 이유: ...

        ... (9번(아침 1 ~ 저녁 3)까지 반복)
        """
        
        print(f"\nGemini API에 추천을 요청합니다... (모델: {model.model_name})")
        response = model.generate_content(prompt)
        
        return response.text

    except Exception as e:
        print(f"❌ Gemini API 오류: {e}")
        return None
    
def get_or_create_recipe_steps(conn, api_key, recipe_id, recipe_title, ingredients_json):
    """
    DB에 조리법이 있으면 가져오고, 없으면 AI로 생성 후 저장합니다.
    """
    try:
        cursor = conn.cursor()
        # 1. DB 확인
        cursor.execute("SELECT recipe_steps FROM recipes WHERE RCP_SNO = ?", (recipe_id,))
        result = cursor.fetchone()
        
        if result and result[0]:
            print(f"✅ (Cache) DB에서 조리법 로드: {recipe_title}")
            return result[0] # 저장된 조리법 반환
        
        # 2. 없으면 AI 생성
        print(f"🤖 (GenAI) 조리법 신규 생성 중: {recipe_title}")
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('models/gemini-flash-latest')
        
        safety_settings = [
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
        ]
        
        # 재료 텍스트 변환
        try:
            ing_dict = json.loads(ingredients_json)
            ing_str = ", ".join([f"{k} {v}" for k, v in ing_dict.items()])
        except:
            ing_str = ingredients_json
            
        prompt = f"""
        당신은 요리 전문가입니다. 다음 요리의 [상세 조리 순서]를 작성해주세요.
        
        - 요리명: {recipe_title}
        - 재료: {ing_str}
        
        [작성 조건]
        1. 번호(1., 2., ...)를 붙여서 단계별로 명확하게 작성하세요.
        2. 각 단계는 구체적인 행동(썰다, 볶다, 끓이다)으로 끝맺으세요.
        3. 불 조절이나 팁이 있다면 함께 적어주세요.
        4. 출력은 오직 조리 순서 텍스트만 작성하세요.
        """
        
        # safety_settings 적용
        response = model.generate_content(prompt, safety_settings=safety_settings)
        
        # 응답 유효성 검사
        if response.candidates and response.candidates[0].content.parts:
            generated_steps = response.text
        
            # 3. DB에 저장 (UPDATE)
            cursor.execute("UPDATE recipes SET recipe_steps = ? WHERE RCP_SNO = ?", (generated_steps, recipe_id))
            conn.commit()
            print(f"💾 (DB 저장) 조리법 저장 완료: {recipe_title}")
            
            return generated_steps
        else:
            print(f"⚠️ (GenAI) 조리법 생성 응답 없음. (Reason: {response.candidates[0].finish_reason})")
            return "조리법 정보를 생성하지 못했습니다. (AI 응답 오류)"
    

    except Exception as e:
        print(f"❌ 조리법 생성/저장 실패: {e}")
        return "조리법 정보를 불러올 수 없습니다."

# --- 4. [신규 추가] DB 연동 (마이페이지) 함수 ---

def setup_database(conn):
    """
    (최초 1회 실행) votes, rewards 테이블이 없으면 생성합니다.
    """
    try:
        cursor = conn.cursor()
        
        # 1. '좋아요/싫어요' 투표 저장 테이블
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS votes (
            vote_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            recipe_sno INTEGER NOT NULL,
            vote_type TEXT NOT NULL, -- 'Like' or 'Dislike'
            voted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(user_id),
            FOREIGN KEY (recipe_sno) REFERENCES recipes(RCP_SNO),
            UNIQUE(user_id, recipe_sno) -- 한 사용자가 한 레시피에 한 번만 투표
        );
        """)
        
        # 2. '7일 달성' 리워드 기록 테이블
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS rewards (
            reward_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL UNIQUE, -- 한 사용자당 하나의 기록
            checked_count INTEGER DEFAULT 0,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)
        
        conn.commit()
        print("✅ (DB 셋업) 'votes' 및 'rewards' 테이블 확인/생성 완료.")
    except Exception as e:
        print(f"❌ (DB 셋업) 테이블 생성 오류: {e}")
        conn.rollback()

def save_vote(conn, user_id, recipe_sno, vote_type):
    """
    '좋아요' 또는 '싫어요' 투표를 DB에 저장합니다.
    (이미 투표했다면 덮어씁니다: INSERT OR REPLACE)
    """
    query = """
    INSERT OR REPLACE INTO votes (user_id, recipe_sno, vote_type)
    VALUES (?, ?, ?)
    """
    try:
        cursor = conn.cursor()
        cursor.execute(query, (user_id, recipe_sno, vote_type))
        conn.commit()
        print(f"🗳️ (DB 저장) user_id {user_id}가 recipe_sno {recipe_sno}에 '{vote_type}' 투표함.")
    except Exception as e:
        print(f"❌ (DB 저장) 투표 저장 오류: {e}")
        conn.rollback()

def save_reward(conn, user_id, checked_count):
    """
    '7일 달성' 체크박스 개수를 DB에 저장(업데이트)합니다.
    """
    query = """
    INSERT OR REPLACE INTO rewards (user_id, checked_count, updated_at)
    VALUES (?, ?, CURRENT_TIMESTAMP)
    """
    try:
        cursor = conn.cursor()
        cursor.execute(query, (user_id, checked_count))
        conn.commit()
        # print(f"🏆 (DB 저장) user_id {user_id}의 달성률 {checked_count}/7 저장.")
    except Exception as e:
        print(f"❌ (DB 저장) 리워드 저장 오류: {e}")
        conn.rollback()

def get_my_votes(conn, user_id):
    """
    (마이페이지용) 내가 'Like'한 레시피 목록을 불러옵니다.
    """
    query = """
    SELECT r.RCP_TTL, r.CKG_MTH_ACTO_NM
    FROM votes v
    JOIN recipes r ON v.recipe_sno = r.RCP_SNO
    WHERE v.user_id = ? AND v.vote_type = 'Like'
    ORDER BY v.voted_at DESC
    """
    try:
        # read_sql로 바로 DataFrame을 만듭니다.
        df = pd.read_sql(query, conn, params=(user_id,))
        return df
    except Exception as e:
        print(f"❌ (DB 조회) '좋아요' 목록 로딩 오류: {e}")
        return pd.DataFrame()

def get_my_rewards(conn, user_id):
    """
    (마이페이지용) 나의 현재 '달성' 횟수를 불러옵니다.
    """
    query = "SELECT checked_count FROM rewards WHERE user_id = ?"
    try:
        cursor = conn.cursor()
        cursor.execute(query, (user_id,))
        result = cursor.fetchone() # (7,) 또는 None
        if result:
            return result[0] # 7
        else:
            return 0 # 기록이 없으면 0
    except Exception as e:
        print(f"❌ (DB 조회) 리워드 로딩 오류: {e}")
        return 0
    
# --- 5. [신규 추가]"스마트" 후보군 선정 (ML) ---

def _extract_ingredients_text(json_str):
    """(HELPER) ingredients_json에서 재료명(key)만 추출해 텍스트로 반환"""
    try:
        ingredients_dict = json.loads(json_str)
        # 재료명(key)만 " "으로 묶어서 반환 (예: "두부 아보카도 간장")
        return " ".join(ingredients_dict.keys())
    except (json.JSONDecodeError, TypeError):
        return "" # 파싱 실패 시 빈 텍스트 반환

# -----------------------------------------------------------------
# [신규 추가] 1순위: AI 레시피 변형 (Generative AI)
# -----------------------------------------------------------------

def modify_recipe_with_gemini(api_key, recipe_title, ingredients_json, modification_request, original_cal_str="정보 없음"):
    """
    (GenAI) 원본 레시피를 사용자의 요청에 맞춰 변형합니다. (칼로리 일관성 유지)
    """
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('models/gemini-flash-latest')
        
        # 안전 설정 해제
        safety_settings = [
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
        ]
        
        try:
            ing_dict = json.loads(ingredients_json)
            ingredients_str = ", ".join([f"{k} {v}" for k, v in ing_dict.items()])
        except:
            ingredients_str = ingredients_json

        # [프롬프트 수정] 기준 칼로리 정보 명시
        prompt = f"""
        당신은 창의적이고 유능한 요리 연구가입니다.
        아래의 [원본 레시피]를 사용자의 [요청 사항]에 맞춰 **새롭게 변형**해주세요.

        [원본 레시피 정보]
        - 요리명: {recipe_title}
        - 원본 재료: {ingredients_str}
        - **원본 1인분 기준 열량: {original_cal_str}**

        [사용자 요청 사항]
        👉 "{modification_request}"

        [작성 가이드]
        1. 요청 사항을 철저히 반영하여 **변경된 재료 목록**을 작성하세요. 
        2. [★매우 중요 - 열량 재계산]
           - 위에서 제공된 **원본 기준 열량({original_cal_str})**을 기준으로, 재료가 빠지거나 줄어들면 낮추고, 추가되면 높여서 계산하세요.
           - 결과물 맨 윗줄에 **(변형된 예상 열량: 약 XXX kcal)** 라고 명시해주세요.
           - (예: 원본이 500kcal인데 '1/2분량' 요청 -> "약 250kcal")
           
        3. 변형된 재료로 요리하는 **간단한 조리법(Step-by-Step)**을 3~7단계로 요약해서 작성하세요.
        4. 마지막에 이 변형이 왜 좋은지 **'영양사의 한마디'**를 덧붙여주세요.
        5. 출력 형식은 읽기 편한 **Markdown**으로 작성해주세요.
        """
        
        print(f"🤖 (GenAI) 레시피 변형 요청: {recipe_title} (기준: {original_cal_str}) -> {modification_request}")
        
        response = model.generate_content(prompt, safety_settings=safety_settings)
        
        if response.candidates and response.candidates[0].content.parts:
            return response.text
        else:
            return "죄송합니다. AI가 응답을 생성하지 못했습니다."

    except Exception as e:
        print(f"❌ (GenAI) 레시피 변형 실패: {e}")
        return "오류가 발생했습니다."

# -----------------------------------------------------------------
# [신규 추가] 2순위: 동적 키워드 추출 (AI 핀포인트)
# -----------------------------------------------------------------

def extract_keywords_with_gemini(api_key, user_input):
    """
    사용자의 자율 입력(문장)에서 검색에 사용할 핵심 식재료/요리 키워드를 추출합니다.
    예: "비 오니까 따뜻한 국물 땡겨" -> "국물 요리 따뜻한 전골 찌개"
    """
    if not user_input or len(user_input) < 2:
        return ""
        
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('models/gemini-flash-latest')
        
        prompt = f"""
        역할: 레시피 데이터베이스 검색을 위한 '스마트 키워드 추출기'

        [사용자 입력]
        "{user_input}"

        [지시 사항]
        1. 사용자의 입력에서 '먹고 싶어', '땡겨', '해줘', '오늘' 같은 서술어나 불필요한 단어는 **모두 버리세요.**
        2. 오직 **음식명, 식재료, 맛(매운, 달콤), 조리법(튀김, 찜)**과 관련된 핵심 단어만 남기세요.
        3. [★중요★] 사용자가 '면류', '국물', '고기' 처럼 포괄적인 단어를 사용했다면, DB 검색이 잘 되도록 **구체적인 메뉴명으로 확장**해주세요.

        [확장 예시]
        - 입력: "면류가 먹고 싶어" -> 출력: "면 국수 파스타 라면 우동 스파게티 짬뽕 짜장면"
        - 입력: "비 와서 국물 땡겨" -> 출력: "국물 탕 찌개 전골 국 따뜻한 얼큰한"
        - 입력: "스트레스 받아서 매운거" -> 출력: "매운 매콤한 얼큰한 떡볶이 마라 불닭 닭발"
        - 입력: "간단하게 먹고 싶어" -> 출력: "간편식 덮밥 볶음밥 토스트 샌드위치"

        [출력 형식]
        오직 공백으로 구분된 키워드만 한 줄로 출력하세요. (특수문자 제외)
        """
        
        response = model.generate_content(prompt)
        keywords = response.text.strip()
        print(f"🔍 사용자 입력 '{user_input}' -> 키워드 추출: '{keywords}'")
        return keywords
        
    except Exception as e:
        print(f"❌ 키워드 추출 실패: {e}")
        return ""
    
def get_smart_candidates(profile, filtered_recipes_df, top_n=100, dynamic_keywords=""):
    """
    (ML) 사용자 프로필 + [동적 키워드]와 가장 유사한 레시피 선정
    """
    print(f"🤖 (ML) '취향 저격' 후보군 선정을 시작합니다... (대상: {len(filtered_recipes_df)}개)")
    
    # [핵심 수정] 사용자 프로필 텍스트에 동적 키워드를 '가중치'로 추가
    # (키워드를 3번 반복해서 넣어주면 검색 중요도가 확 올라갑니다)
    user_text = profile['preferences'] + " " + profile['goals']
    
    if dynamic_keywords:
        weighted_keywords = (dynamic_keywords + " ") * 3 # 가중치 3배 증폭
        user_text += " " + weighted_keywords
        print(f"✨ (ML) 동적 가중치 적용됨: {weighted_keywords}")
    
    # 2. 레시피 재료 텍스트 생성 (비교 대상)
    # (이 작업은 수천~수만 건이므로 시간이 조금 걸릴 수 있음)
    recipe_texts = filtered_recipes_df['ingredients_json'].apply(_extract_ingredients_text)
    
    if recipe_texts.empty:
        print("⚠️ (ML) 재료 텍스트를 추출할 수 없습니다. 랜덤 샘플링으로 대체합니다.")
        sample_size = min(top_n, len(filtered_recipes_df))
        return filtered_recipes_df.sample(n=sample_size, random_state=42)
        
    # 3. TF-IDF 벡터화
    try:
        vectorizer = TfidfVectorizer()
        
        # 3-1. 레시피(재료) 전체로 TF-IDF 어휘 사전 학습
        tfidf_matrix_recipes = vectorizer.fit_transform(recipe_texts)
        
        # 3-2. 사용자 프로필 텍스트를 동일한 어휘 사전으로 변환
        tfidf_vector_user = vectorizer.transform([user_text])
        
        # 4. 코사인 유사도 계산
        # (결과 shape: [1, num_recipes])
        cosine_sims = cosine_similarity(tfidf_vector_user, tfidf_matrix_recipes)
        
        # 5. 유사도 점수가 가장 높은 top_n개의 *인덱스* 찾기
        # [0]으로 1D 배열로 만들고, argsort로 정렬 후, 상위 top_n개 선택
        # (유사도가 0인 레시피가 많을 수 있으므로, 실제 개수(len)와 top_n 중 작은 값을 택함)
        num_candidates = min(top_n, len(cosine_sims[0]))
        top_indices = np.argsort(cosine_sims[0])[-num_candidates:][::-1]
        
        # 6. 상위 top_n개 레시피 DataFrame 반환
        smart_candidates_df = filtered_recipes_df.iloc[top_indices]
        
        print(f"✅ (ML) '취향 저격' 후보군 {len(smart_candidates_df)}개 선정 완료.")
        return smart_candidates_df
        
    except Exception as e:
        print(f"❌ (ML) TF-IDF/유사도 계산 실패: {e}. 랜덤 샘플링으로 대체합니다.")
        sample_size = min(top_n, len(filtered_recipes_df))
        return filtered_recipes_df.sample(n=sample_size, random_state=42)
    
    
# --- 6. 메인 코드 실행(api 호출 테스트용) ---

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