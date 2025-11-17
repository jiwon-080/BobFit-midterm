import sqlite3
import os

db_path = 'recipe_db.sqlite'

def create_user_table(conn):
    """
    (2단계 수정) 기존 'users' 테이블을 삭제하고, budget 컬럼이 포함된 새 테이블을 생성합니다.
    """
    try:
        cursor = conn.cursor()
        
        # [핵심 수정] 기존 테이블이 있다면 삭제 (스키마 갱신을 위해)
        cursor.execute("DROP TABLE IF EXISTS users")
        
        # 새 스키마로 테이블 생성
        cursor.execute("""
        CREATE TABLE users (
            user_id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            preferences TEXT, 
            restrictions_allergies TEXT, 
            restrictions_other TEXT,
            goals TEXT,
            budget INTEGER DEFAULT 0  -- [신규] 한 끼 예산
        );
        """)
        print("✅ (2단계) 기존 테이블 삭제 후, budget 컬럼이 포함된 새 'users' 테이블 생성 완료.")
    except Exception as e:
        print(f"❌ 'users' 테이블 생성 오류: {e}")
        
def insert_demo_profiles_v2(conn):
    # [수정] 5명의 프로필에 'budget' 숫자 값 추가
    # (이름, 기호, 알레르기, 기타제약, 목표, [예산])
    profiles = [
        ('김다이어트', '한식, 일식, 채소', '게, 새우', '종교(돼지고기 x)', '다이어트, 저염식, 채식', 15000),
        ('박벌크업', '육류, 양식', '없음', '없음', '단백질 섭취, 근력 증가', 10000), # 1만원 제한
        ('이채식', '채식, 비건', '복숭아, 닭고기', '채식, 비건', '영양균형, 비건', 20000),
        ('최바쁨', '간편식, 한식', '없음', '조리시간 30분 이내', '빠른 식사', 0), # 0은 제한 없음
        ('오영양', '전체, 한식', '없음', '없음', '영양균형', 0)
    ]
    
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM users;")
        cursor.execute("DELETE FROM sqlite_sequence WHERE name='users';")
        
        # [수정] budget 값도 함께 INSERT
        cursor.executemany("""
        INSERT INTO users (username, preferences, restrictions_allergies, restrictions_other, goals, budget) 
        VALUES (?, ?, ?, ?, ?, ?)
        """, profiles)
        
        conn.commit()
        print(f"✅ 표준 프로필 {len(profiles)}개 (예산 포함) 삽입 성공.")
        
    except Exception as e:
        print(f"❌ 프로필 삽입 오류: {e}")

# ... (나머지 실행 코드는 동일) ...
if __name__ == "__main__":
    # ... (conn 연결 및 함수 호출 코드) ...
    conn = sqlite3.connect(db_path)
    create_user_table(conn)
    insert_demo_profiles_v2(conn)
    conn.close()