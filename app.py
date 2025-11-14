import streamlit as st
import sqlite3
import pandas as pd
import json
from datetime import date
import os
import sys
import importlib.util

from dotenv import load_dotenv
load_dotenv()

# -----------------------------------------------------------
# [중요] 4단계에서 만든 백엔드 로직 파일(recommend_gemini.py)에서 
# 핵심 함수들을 import (가져오기) 합니다.
# -----------------------------------------------------------
try:
    # 1. 현재 app.py 파일이 있는 폴더의 절대 경로를 찾음
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    # 2. 백엔드 파일의 전체 경로를 생성
    backend_file_path = os.path.join(script_dir, 'recommend_gemini.py')

    # 3. importlib를 사용해 해당 경로의 파일을 'backend'라는 이름의 모듈로 강제 로드
    spec = importlib.util.spec_from_file_location("backend", backend_file_path)
    backend = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(backend)
    
    # 4. (확인) 로드 성공 시, Streamlit 경로에도 강제 추가
    if script_dir not in sys.path:
        sys.path.append(script_dir)
        
    print("✅ (디버그) 'recommend_gemini.py' 모듈 강제 로드 성공.")

except Exception as e:
    # 이 오류가 뜨면, GitHub에 파일이 없거나 이름이 다른 것입니다.
    st.error(f"오류: 'recommend_gemini.py' 파일을 강제로 로드하는 데 실패했습니다.")
    st.error(f"오류 상세: {e}")
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
    
# --- 3. '신규 가입' 탭에서 사용할 DB 추가 함수 ---

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

# --- 4. Streamlit UI 그리기 ---

st.title("🥗 BobFit: AI 기반 맞춤 식단 추천")
st.caption(f"오늘 날짜: {date.today().strftime('%Y년 %m월 %d일')}")

# [신규] 탭(Tab) UI 생성
tab1, tab2, tab3 = st.tabs([" 🧑‍🍳 식단 추천받기 ", " 📝 신규 프로필 가입 ", " 📈 마이페이지 "])

# [신규] 앱이 시작될 때 DB 테이블 셋업 함수를 한 번 호출
# (앱이 실행될 때마다 호출되지만, 'CREATE TABLE IF NOT EXISTS'이므로 안전합니다)
try:
    conn = sqlite3.connect(backend.DB_PATH)
    backend.setup_database(conn)
except Exception as e:
    st.error(f"DB 셋업 실패: {e}")
finally:
    if 'conn' in locals() and conn:
        conn.close()

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
                
        # -----------------------------------------------------------
        # [신규 기능] 3A-3. 동적 입력 (기분, 날짜, 자율 입력)
        # -----------------------------------------------------------
        st.divider() # 구분선
        
        # 1. "오늘의 시간 API" (Python datetime)
        today = date.today()
        today_date_str = today.strftime("%Y년 %m월 %d일")
        
        # 2. 오늘의 기분 (선택)
        mood_options = ["-", "기분 좋음 😊", "평범함 😐", "피곤함 😴", "스트레스 🔥"]
        mood = st.selectbox("오늘의 기분은 어떠신가요?", mood_options)

        # 3. 자율 입력
        free_text = st.text_input(
            "특별히 원하는 요청사항을 적어주세요 (선택 사항)", 
            placeholder="예: 비 오는 날이라 따뜻한 국물이 먹고 싶어요"
        )


        # 3A-4. 추천 실행 버튼
        if st.button("✨ AI로 오늘의 식단 추천받기"):
            if profile:
                st.session_state.recommendation = ""
                st.session_state.tasks_checked = 0
                st.session_state.votes = {} # [기능 3] 보팅 초기화
                
                with st.spinner("1차 필터링 및 '취향 저격' 후보군(ML) 선정 중..."):
                    try:
                        # 1. 1차 필터링 (동일)
                        restrictions = backend.parse_restrictions(profile)
                        filtered_recipes = backend.recommend_recipes_by_filter(conn, profile, restrictions)
                        
                        if filtered_recipes.empty:
                            st.error("1차 필터링 결과, 추천할 레시피가 없습니다.")
                        else:
                            # -------------------------------------------------
                            # [핵심 수정!]
                            # 2. (랜덤 샘플링 대신) "스마트" 후보군 선정 (ML 함수 호출)
                            candidate_recipes = backend.get_smart_candidates(
                                profile, filtered_recipes, top_n=100
                            )
                            # -------------------------------------------------

                            # (스피너 텍스트 변경)
                            with st.spinner("Gemini API 호출 중... (AI가 식단 구성 중)"):
                                # 3. 2차 (Gemini) 추천 (동일)
                                recommendation_text = backend.get_gemini_recommendation(
                                    backend.YOUR_API_KEY, 
                                    profile,
                                    candidate_recipes,
                                    today_date_str, 
                                    mood,           
                                    free_text       
                                )
                            
                            if recommendation_text:
                                # 1. AI 텍스트(recommendation_text)를 session_state에 저장
                                st.session_state.recommendation = recommendation_text
                                
                                # 2. 100개 후보군(candidates_df)을 session_state에 저장
                                st.session_state.candidates_df = candidate_recipes
                                
                                # 3. "성공" 메시지는 화면에 그냥 표시 (저장 X)
                                st.success("AI 추천이 완료되었습니다!")
                            else:
                                st.error("Gemini API 호출에 실패했습니다.")
                                
                    except Exception as e:
                        st.error(f"추천 중 오류 발생: {e}")
            else:
                st.error("프로필을 불러올 수 없습니다.")

        # 3A-4. 추천 결과 및 리워드 UI (기능 2, 3 포함하여 수정됨)
        if st.session_state.recommendation:
            
            st.divider() # 구분선
            st.subheader(f"🎉 {profile['username']}님을 위한 AI 추천 식단")
        
            # [수정 2]
            # AI가 보낸 줄바꿈(\n)을 Markdown 강제 줄바꿈(공백2개+\n)으로 변경
            formatted_text = st.session_state.recommendation.replace('\n', '  \n')
            st.markdown(formatted_text) 
        
            st.divider() # 다음 섹션 구분선
            st.subheader("🔍 레시피 상세 정보 및 평가")
            
            # ⚠️ 중요: 데이터 한계 (열량/조리법 정보)
            st.warning("""
            현재 DB에는 '열량(칼로리)' 및 '상세 조리법' 데이터가 없습니다. 
            (1단계 전처리 시, 원본 CSV에 해당 정보가 없었습니다.)
            
            데모에서는 주요 재료 정보(`ingredients_json`)를 대신 표시합니다.
            """)

            # AI가 추천한 텍스트에 포함된 레시피(후보군 100개 중)만 찾아서 표시
            # 1. AI 응답 텍스트와 100개 후보 DataFrame을 가져옴

            rec_text = st.session_state.recommendation
            candidates_df = st.session_state.get('candidates_df', pd.DataFrame())

            if not candidates_df.empty:
                import re 
                displayed_sno = set() 
                
                for index, row in candidates_df.iterrows():
                    
                    recipe_id = row['RCP_SNO']
                    recipe_title_full = str(row['RCP_TTL']) # 1. 원본 제목 (예: "[단호박...]")
                    clean_name = str(row['CKG_NM'])      # 2. 핵심 요리명 (예: "단호박에그슬럿")
                    
                    # --- [핵심] 하이브리드 매칭 ---
                    match_found = False
                    
                    # 1. AI 응답에 '원본 제목'이 통째로 있는지 확인
                    if recipe_title_full in rec_text:
                        match_found = True
                    
                    # 2. 1번이 실패하면, '핵심 요리명'이 있는지 재확인
                    #    (단, 요리명이 유효한 경우만)
                    elif (pd.notna(clean_name) and len(clean_name) > 1) and (clean_name in rec_text):
                        match_found = True
                    # ------------------------------

                    # 3. 둘 중 하나라도 성공하고, 아직 표시되지 않았다면
                    if match_found and recipe_id not in displayed_sno:
                        displayed_sno.add(recipe_id)
                        
                        with st.expander(f"**{recipe_title_full}** (상세보기)"):
                            
                            # (1) 재료 정보 표시
                            st.markdown("##### 🥑 주요 재료")
                            try:
                                ingredients_dict = json.loads(row['ingredients_json'])
                                st.dataframe(pd.Series(ingredients_dict), use_container_width=True)
                            except:
                                st.text(row['ingredients_json'])
                            
                            # (2) 기타 정보 표시
                            st.markdown("#####  E.T.C")
                            
                            # [디버그 1 수정]
                            # row['CKG_MTH_ACTO_NM'] -> row['CKG_TIME_NM']로 수정
                            st.text(f"조리법: {row['CKG_MTH_ACTO_NM']} | 소요시간: {row['CKG_TIME_NM']} | 인분: {row['CKG_INBUN_NM']}")

                            # [기능 3] 보팅 버튼
                            st.markdown("##### ⭐ 평가하기")
                            key_like = f"like_{recipe_id}"
                            key_dislike = f"dislike_{recipe_id}"
                            
                            col1, col2, _ = st.columns([1, 1, 5])
                            
                            # [수정] 버튼 클릭 시 backend.save_vote 함수 호출
                            if col1.button("👍 Like", key=key_like):
                                with sqlite3.connect(backend.DB_PATH) as conn:
                                    backend.save_vote(conn, profile['user_id'], recipe_id, "Like")
                                st.toast(f"'{recipe_title_full}' 👍 추천! (저장됨)")
                                    
                            if col2.button("👎 Dislike", key=key_dislike):
                                with sqlite3.connect(backend.DB_PATH) as conn:
                                    backend.save_vote(conn, profile['user_id'], recipe_id, "Dislike")
                                st.toast(f"'{recipe_title_full}' 👎 비추천 (저장됨)")
                
                # 4. 만약 7개 중 일부만 매칭되었다면 (디버깅)
                if len(displayed_sno) < 7 and len(displayed_sno) > 0:
                    st.warning(f"AI가 7개를 추천했지만, {len(displayed_sno)}개만 후보군과 매칭되었습니다.")
                elif len(displayed_sno) == 0:
                    st.error("AI가 추천한 레시피를 후보군(100개)과 매칭하는 데 실패했습니다.")
                    with st.expander("AI가 보낸 원본 응답 보기 (디버깅용)"):
                        st.code(rec_text)

            # 3A-5. 리워드 UI (기존과 동일)
            st.divider()
            st.subheader("🗓️ 7일 실천 리워드")
            
            # [수정] DB에서 현재 달성 횟수를 불러옴
            with sqlite3.connect(backend.DB_PATH) as conn:
                checked_count = backend.get_my_rewards(conn, profile['user_id'])
            
            tasks = [f"{i+1}일차: 식단 실천 완료" for i in range(7)]
            
            # [수정] 체크박스를 누를 때마다 DB에 즉시 저장
            # (st.checkbox는 on_change 콜백을 지원함)
            def on_checkbox_change(user_id, i):
                # on_change 콜백이 실행되는 시점에, st.session_state의 'key'에는
                # 체크박스의 '새로운 상태(True/False)'가 저장되어 있습니다.
                # 7개의 체크박스 상태를 모두 다시 세어서 DB에 저장합니다.
                current_checks = 0
                for j in range(7):
                    if st.session_state.get(f"task_{j}", False): # .get으로 안전하게 접근
                        current_checks += 1
                
                with sqlite3.connect(backend.DB_PATH) as conn:
                    backend.save_reward(conn, user_id, current_checks)

            cols = st.columns(4)
            for i, task in enumerate(tasks):
                cols[i % 4].checkbox(
                    task, 
                    value=(i < checked_count), # DB에서 불러온 값으로 초기화
                    key=f"task_{i}",
                    on_change=on_checkbox_change, # [신규]
                    args=(profile['user_id'], i) # [신규]
                )
            
            # (UI 표시는 동일)
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


# --- 3C. [신규] 마이페이지 탭 ---
with tab3:
    st.subheader(f"📈 마이페이지")
    
    # 1. (중요) '추천받기' 탭에서 선택한 사용자의 프로필을 그대로 사용
    #    (selected_id 변수는 tab1에서 이미 정의되었음)
    if 'profile' in locals() and profile:
        st.info(f"현재 **{profile['username']}**(ID:{profile['user_id']}) 님의 정보를 보고 있습니다.")
        
        col1, col2 = st.columns(2)
        
        # --- 2. 내가 '좋아요' 한 레시피 ---
        with col1:
            st.markdown("#### 👍 내가 '좋아요' 한 레시피")
            with sqlite3.connect(backend.DB_PATH) as conn:
                liked_recipes_df = backend.get_my_votes(conn, profile['user_id'])
            
            if liked_recipes_df.empty:
                st.write("아직 '좋아요' 한 레시피가 없습니다.")
            else:
                st.dataframe(liked_recipes_df, use_container_width=True)

        # --- 3. 나의 '달성 기록' ---
        with col2:
            st.markdown("#### 🏆 나의 7일 달성 기록")
            with sqlite3.connect(backend.DB_PATH) as conn:
                current_rewards = backend.get_my_rewards(conn, profile['user_id'])
            
            st.metric(label="현재 달성일", value=f"{current_rewards} / 7 일")
            st.progress(current_rewards / 7.0)
            if current_rewards == 7:
                st.success("목표 달성! 대단합니다! 🥳")

    else:
        st.warning("먼저 [식단 추천받기] 탭에서 사용자를 선택해주세요.")