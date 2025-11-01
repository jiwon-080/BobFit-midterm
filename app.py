import streamlit as st
import sqlite3
import pandas as pd
from datetime import date

# -----------------------------------------------------------
# [중요] 4단계에서 만든 백엔드 로직 파일(recommend_gemini.py)에서 
# 핵심 함수들을 import (가져오기) 합니다.
# -----------------------------------------------------------
try:
    # (API 키, DB 경로, 모든 함수를 'backend'라는 이름으로 가져옴)
    import recommend_gemini as backend 
except ImportError:
    st.error("오류: 'recommend_gemini.py' 파일을 찾을 수 없습니다.")
    st.stop()

# --- 1. 앱 기본 설정 ---

st.set_page_config(
    page_title="BobFit: AI 식단 추천",
    page_icon="🥗",
    layout="wide"
)

# [상태 저장소] 체크박스 상태, 추천 결과를 저장하기 위해 초기화
if 'recommendation' not in st.session_state:
    st.session_state.recommendation = ""
if 'tasks_checked' not in st.session_state:
    st.session_state.tasks_checked = 0

# --- 2. DB에서 사용자 목록 불러오기 (UI용) ---
def get_user_list(conn):
    """users 테이블에서 (ID, 이름) 목록을 가져옵니다."""
    try:
        df = pd.read_sql("SELECT user_id, username FROM users", conn)
        # (1, '김다이어트'), (2, '박벌크업')...
        return df.to_dict('records') 
    except Exception as e:
        st.error(f"DB에서 사용자 목록 로드 실패: {e}")
        return []

# --- 3. Streamlit UI 그리기 ---

st.title("🥗 BobFit: AI 기반 맞춤 식단 추천")
st.caption(f"오늘 날짜: {date.today().strftime('%Y년 %m월 %d일')}")

# [신규] 탭(Tab) UI 생성
tab1, tab2 = st.tabs([" 🧑‍🍳 식단 추천받기 ", " 📝 신규 프로필 가입 "])

# --- 3A. [추천받기] 탭 ---
with tab1:
    try:
        conn = sqlite3.connect(backend.DB_PATH) # 4단계 파일의 DB_PATH 변수 사용
        
        # 3A-1. 사용자 선택 (드롭다운)
        user_list = get_user_list(conn)
        if not user_list:
            st.error("사용자 프로필이 DB에 없습니다. 'create_profiles_v2.py'를 실행해주세요.")
            st.stop()
        
        user_options = {user['user_id']: f"{user['user_id']}. {user['username']}" for user in user_list}
        
        selected_id = st.selectbox(
            '추천받을 사용자를 선택하세요:',
            options=user_options.keys(),
            format_func=lambda x: user_options[x]
        )

        # 3A-2. 선택된 사용자 프로필 표시
        profile = backend.get_user_profile(conn, selected_id)
        if profile:
            with st.expander("선택한 사용자 프로필 보기"):
                col1, col2, col3 = st.columns(3)
                col1.metric("🎯 달성 목표", profile['goals'])
                col2.metric("👍 기호", profile['preferences'])
                col3.metric("🚫 알레르기", profile['restrictions_allergies'])
                col3.metric("🚫 기타 제약", profile['restrictions_other'])

        # 3A-3. 추천 실행 버튼
        if st.button("🤖 AI로 일주일 식단 추천받기"):
            if profile:
                st.session_state.recommendation = ""
                st.session_state.tasks_checked = 0
                st.session_state.votes = {} # [기능 3] 보팅 초기화
                
                with st.spinner("1차 필터링 및 Gemini API 호출 중... (최대 30초 소요)"):
                    try:
                        # [핵심 실행] 4단계 백엔드 로직 호출
                        restrictions = backend.parse_restrictions(profile)
                        filtered_recipes = backend.recommend_recipes_by_filter(conn, profile, restrictions)
                        
                        if filtered_recipes.empty:
                            st.error("1차 필터링 결과, 추천할 레시피가 없습니다.")
                        else:
                            sample_size = min(100, len(filtered_recipes))
                            candidate_recipes = filtered_recipes.sample(n=sample_size, random_state=42)
                            
                            recommendation_text = backend.get_gemini_recommendation(
                                backend.YOUR_API_KEY, 
                                profile,
                                candidate_recipes
                            )
                            
                            if recommendation_text:
                                # [기능 2, 3] 추천된 레시피 원본(후보군)과 AI 답변을 모두 저장
                                st.session_state.recommendation = recommendation_text
                                st.session_state.candidates_df = candidate_recipes # 상세정보 표시에 사용
                                st.success("AI 추천이 완료되었습니다!")
                            else:
                                st.error("Gemini API 호출에 실패했습니다.")
                    except Exception as e:
                        st.error(f"추천 중 오류 발생: {e}")
            else:
                st.error("프로필을 불러올 수 없습니다.")

        # 3A-4. 추천 결과 및 리워드 UI (기능 2, 3 포함하여 수정됨)
        if st.session_state.recommendation:
            
            st.divider()
            st.subheader(f"🎉 {profile['username']}님을 위한 AI 추천 식단")
            
            # (Gemini가 생성한 텍스트를 마크다운 형식으로 예쁘게 표시)
            st.markdown(st.session_state.recommendation) 

            # -----------------------------------------------------------
            # [기능 2 & 3] 레시피 상세정보(토글) 및 보팅 기능
            # -----------------------------------------------------------
            st.divider()
            st.subheader("🔍 레시피 상세 정보 및 평가")
            
            # ⚠️ 중요: 데이터 한계 (열량/조리법 정보)
            st.warning("""
            현재 DB에는 '열량(칼로리)' 및 '상세 조리법' 데이터가 없습니다. 
            (1단계 전처리 시, 원본 CSV에 해당 정보가 없었습니다.)
            
            데모에서는 **주요 재료 정보(`ingredients_json`)**를 대신 표시합니다.
            """)

            # AI가 추천한 텍스트에 포함된 레시피(후보군 100개 중)만 찾아서 표시
            rec_text = st.session_state.recommendation
            if 'candidates_df' in st.session_state:
                # 후보군(100개) DataFrame을 순회
                for index, row in st.session_state.candidates_df.iterrows():
                    recipe_title = row['RCP_TTL']
                    
                    # AI가 생성한 추천 텍스트에 이 레시피의 제목이 포함되어 있다면
                    if recipe_title in rec_text:
                        
                        # [기능 2] 토글(expander) 생성
                        with st.expander(f"**{recipe_title}** (상세보기)"):
                            
                            # (1) 재료 정보 표시
                            st.markdown("##### 🥑 주요 재료")
                            try:
                                # JSON 문자열 -> Python 딕셔너리 -> DataFrame
                                ingredients_dict = json.loads(row['ingredients_json'])
                                st.dataframe(pd.Series(ingredients_dict), use_container_width=True)
                            except:
                                st.text(row['ingredients_json']) # 파싱 실패 시 원본 표시
                            
                            # (2) 기타 정보 표시
                            st.markdown("#####  E.T.C")
                            st.text(f"조리법: {row['CKG_MTH_ACTO_NM']} | 소요시간: {row['CKG_TIME_NM']} | 인분: {row['CKG_INBUN_NM']}")

                            # [기능 3] 보팅 버튼
                            st.markdown("##### ⭐ 평가하기")
                            
                            # 'key='를 이용해 각 버튼을 고유하게 만듦
                            # (RCP_SNO는 레시피 고유 ID)
                            recipe_id = row['RCP_SNO']
                            key_like = f"like_{recipe_id}"
                            key_dislike = f"dislike_{recipe_id}"
                            
                            col1, col2, _ = st.columns([1, 1, 5])
                            
                            if col1.button("👍 Like", key=key_like):
                                st.session_state.votes[recipe_title] = "Like"
                                st.toast(f"'{recipe_title}' 👍 추천!")
                                
                            if col2.button("👎 Dislike", key=key_dislike):
                                st.session_state.votes[recipe_title] = "Dislike"
                                st.toast(f"'{recipe_title}' 👎 비추천")

            # 3A-5. 리워드 UI (기존과 동일)
            st.divider()
            st.subheader("🗓️ 7일 실천 리워드")
            
            tasks = [f"{i+1}일차: 식단 실천 완료" for i in range(7)]
            checked_count = 0
            cols = st.columns(4)
            for i, task in enumerate(tasks):
                if cols[i % 4].checkbox(task, key=f"task_{i}"):
                    checked_count += 1
            
            st.progress(checked_count / 7.0)
            
            if checked_count == 7:
                st.balloons()
                st.success("🎉 7일 달성 완료! 리워드 쿠폰(10% 할인)이 발급되었습니다! 🎁")
            else:
                st.info(f"{checked_count} / 7일 달성. {7-checked_count}일 더 힘내세요!")

    except Exception as e:
        st.error(f"DB 연결 실패: {e}")
    finally:
        if 'conn' in locals() and conn:
            conn.close()
            
            
# --- 3B. [신규 가입] 탭 (체크박스 형태로 수정) ---
with tab2:
    st.subheader("📝 BobFit 신규 프로필 등록")
    st.write("맞춤 추천을 위해 프로필을 입력해주세요.")

    # --- 1. 신규 가입 폼 (Form) ---
    with st.form(key='signup_form'):
        
        # --- 1-1. 기본 정보 ---
        st.markdown("##### 1. 기본 정보")
        new_username = st.text_input("사용자명 (필수)")
        new_preferences = st.text_input("선호 음식 (예: 한식, 육류, 채소)")

        # --- 1-2. 알레르기 (Multiselect 사용) ---
        st.markdown("##### 2. 알레르기 제약")
        ALLERGY_LIST = [
            '알류', '우유', '메밀', '땅콩', '대두', '밀', '잣', '호두', '게', '새우', 
            '오징어', '고등어', '조개류', '복숭아', '토마토', '닭고기', '돼지고기', '쇠고기', '아황산류'
        ]
        # (19개 체크박스는 너무 길어서, 다중 선택 드롭다운(multiselect)이 더 깔끔합니다)
        selected_allergies = st.multiselect(
            "알레르기가 있는 식품을 모두 선택하세요 (한국 표준 19종):",
            options=ALLERGY_LIST
        )

        # --- 1-3. 기타 제약 (체크박스 + 입력칸) ---
        st.markdown("##### 3. 기타 식이 제한")
        OTHER_CONSTRAINT_LIST = [
            '저염식', '당뇨', '채식', '비건', '이슬람교', '힌두교', '할랄'
        ]
        
        selected_other_constraints = []
        cols = st.columns(4) # 4열로 배치
        for i, constraint in enumerate(OTHER_CONSTRAINT_LIST):
            if cols[i % 4].checkbox(constraint, key=f"constraint_{i}"):
                selected_other_constraints.append(constraint)
        
        # 기타 직접 입력칸
        other_text_input = st.text_input("기타 사항 직접 입력 (예: 조리시간 30분 이내)")

        # --- 1-4. 달성 목표 ---
        st.markdown("##### 4. 달성 목표")
        new_goals = st.text_input("달성 목표 (예: 다이어트, 저염식, 단백질 섭취)")
        
        # --- 1-5. 제출 버튼 ---
        st.divider()
        submit_button = st.form_submit_button(label='가입하기')

    # --- 2. 폼 제출 시 실행되는 로직 ---
    if submit_button:
        if not new_username:
            st.error("사용자명은 필수입니다.")
        else:
            # 1. 알레르기 리스트 -> DB에 저장할 문자열로 변환
            # (예: ['게', '새우'] -> "게, 새우")
            new_allergies_str = ", ".join(selected_allergies) if selected_allergies else "없음"
                
            # 2. 기타 제약 리스트 + 입력칸 -> 문자열로 변환
            other_list = selected_other_constraints
            if other_text_input: # '기타' 입력칸에 쓴 내용 추가
                other_list.append(other_text_input)
            new_other_str = ", ".join(other_list) if other_list else "없음"
                
            # 3. 빈칸은 '없음'으로 처리
            new_preferences_str = new_preferences if new_preferences else '없음'
            new_goals_str = new_goals if new_goals else '없음'
            
            # 4. DB에 저장할 최종 튜플 생성
            profile_data = (
                new_username,
                new_preferences_str,
                new_allergies_str, # 변환된 문자열
                new_other_str,     # 변환된 문자열
                new_goals_str
            )
            
            # 5. DB 저장 함수 호출 (app.py 맨 끝에 이미 정의되어 있음)
            try:
                add_user_to_db(profile_data)
                st.success(f"✅ 환영합니다, {new_username}님! 프로필이 저장되었습니다.")
                st.info("이제 [식단 추천받기] 탭으로 이동하여 새로고침(F5)하면, 본인 이름이 목록에 나타납니다.")
            except Exception as e:
                st.error(f"DB 저장 실패: {e}")


# --- 4. [신규] '신규 가입' 탭에서 사용할 DB 추가 함수 ---
# (이 코드는 app.py의 맨 마지막, 전역 레벨에 추가합니다)

def add_user_to_db(profile_data):
    """
    st.form에서 받은 튜플을 'users' DB에 INSERT합니다.
    (이전 add_user.py 스크립트와 동일한 로직)
    """
    query = """
    INSERT INTO users (username, preferences, restrictions_allergies, restrictions_other, goals) 
    VALUES (?, ?, ?, ?, ?)
    """
    conn = None
    try:
        conn = sqlite3.connect(backend.DB_PATH)
        cursor = conn.cursor()
        cursor.execute(query, profile_data)
        conn.commit()
    except Exception as e:
        # 오류 발생 시, 롤백하고 오류를 다시 발생시켜 상위(UI)에서 처리
        if conn:
            conn.rollback()
        raise e
    finally:
        if conn:
            conn.close()