import sqlite3
import pandas as pd
import json
import os
import time
from tqdm import tqdm # 진행률 표시줄 (필수)

# 1. 팀원이 만든 네이버 API 함수 import
try:
    from get_price_min_func import get_lowest_price
except ImportError:
    print("❌ 오류: 'get_price_min_func.py' 파일을 찾을 수 없습니다.")
    print("이 스크립트와 같은 폴더에 있는지 확인하세요.")
    exit()

# --- 설정 ---
DB_PATH = 'recipe_db.sqlite'
CACHE_FILE = 'price_cache.json' # 재료 가격 캐시 파일
API_RATE_LIMIT_SEC = 0.11 # 1초당 10회 제한 (안전하게 0.11초)

# --- 1. DB에 'estimated_price' 컬럼 추가 ---
def add_price_column_to_db(conn):
    """
    recipes 테이블에 estimated_price 컬럼을 추가합니다. (이미 있으면 통과)
    """
    try:
        cursor = conn.cursor()
        # "IF NOT EXISTS"는 ALTER TABLE에서 표준 SQL이 아니므로,
        # 컬럼 목록을 직접 확인하는 방식을 사용합니다.
        cursor.execute("PRAGMA table_info(recipes)")
        columns = [info[1] for info in cursor.fetchall()]
        
        if 'estimated_price' not in columns:
            cursor.execute("ALTER TABLE recipes ADD COLUMN estimated_price INTEGER DEFAULT NULL")
            conn.commit()
            print("✅ (DB 수정) 'recipes' 테이블에 'estimated_price' 컬럼을 추가했습니다.")
        else:
            print("ℹ️ (DB 확인) 'estimated_price' 컬럼이 이미 존재합니다.")
            
    except Exception as e:
        print(f"❌ (DB 수정) 컬럼 추가 오류: {e}")
        conn.rollback()

# --- 2. 가격 캐시(Cache) 로드/저장 함수 ---
def load_price_cache():
    """
    API 호출을 아끼기 위해, 이전에 검색한 재료 가격 캐시를 로드합니다.
    """
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                cache = json.load(f)
                print(f"ℹ️ (캐시) {len(cache)}개의 재료 가격을 '{CACHE_FILE}'에서 로드했습니다.")
                return cache
        except json.JSONDecodeError:
            print(f"⚠️ (캐시) '{CACHE_FILE}'이 손상되었습니다. 새 캐시를 시작합니다.")
            return {}
    else:
        print("ℹ️ (캐시) 새 가격 캐시를 시작합니다.")
        return {}

def save_price_cache(cache):
    """
    재료 가격 캐시를 JSON 파일로 저장합니다.
    """
    try:
        with open(CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(cache, f, ensure_ascii=False, indent=4)
        # print(f"💾 (캐시) {len(cache)}개 재료 가격 저장 완료.")
    except Exception as e:
        print(f"❌ (캐시) 저장 실패: {e}")

# --- 3. 핵심: 모든 레시피 가격 계산 및 DB 업데이트 ---
def calculate_all_recipe_prices(conn):
    
    # 1. 가격 캐시 로드
    ingredient_price_cache = load_price_cache()
    
    # 2. (핵심) 아직 가격이 계산되지 않은(NULL) 레시피만 불러오기
    #    (스크립트가 중단되어도 이어서 가능!)
    df = pd.read_sql("SELECT RCP_SNO, ingredients_json FROM recipes WHERE estimated_price IS NULL", conn)
    
    if df.empty:
        print("\n🎉 모든 레시피의 가격 계산이 이미 완료되었습니다!")
        return

    print(f"\n총 {len(df)}개의 레시피에 대한 가격 계산을 시작합니다...")
    print("🚨 (API 호출로 인해 몇 시간이 걸릴 수 있습니다. 중단해도 이어서 가능합니다)")

    # 3. 진행률 표시줄(tqdm)과 함께 레시피 순회
    # (cursor는 DB 업데이트용)
    cursor = conn.cursor()
    
    for index, row in tqdm(df.iterrows(), total=df.shape[0]):
        
        recipe_sno = row['RCP_SNO']
        total_cost = 0
        
        try:
            ingredients_dict = json.loads(row['ingredients_json'])
            # (중복 재료 방지를 위해 key만 사용)
            unique_ingredients = ingredients_dict.keys() 
            
            if not unique_ingredients:
                continue # 재료가 비어있으면 0원으로 저장 (아래에서)

            # 4. 개별 재료 가격 계산 (캐시 우선)
            for ingredient_name in unique_ingredients:
                
                # 4-1. 캐시에 가격이 이미 있는가?
                if ingredient_name in ingredient_price_cache:
                    price = ingredient_price_cache[ingredient_name]
                
                # 4-2. 캐시에 가격이 없으면 -> API 호출
                else:
                    # [API 호출]
                    price = get_lowest_price(ingredient_name)
                    
                    ingredient_price_cache[ingredient_name] = price # 캐시에 저장
                    
                    # [중요!] 네이버 API 속도 제한 (10/sec) 준수
                    time.sleep(API_RATE_LIMIT_SEC) 
                
                total_cost += price
            
            # 5. (DB 저장) 계산된 총 가격을 DB에 즉시 업데이트
            # (속도보다 안정성/이어하기를 위해 매번 업데이트)
            cursor.execute(
                "UPDATE recipes SET estimated_price = ? WHERE RCP_SNO = ?",
                (total_cost, recipe_sno)
            )
            conn.commit() # 즉시 저장

        except (json.JSONDecodeError, TypeError):
            # ingredients_json이 깨진 경우 0원으로 처리
            cursor.execute(
                "UPDATE recipes SET estimated_price = 0 WHERE RCP_SNO = ?",
                (recipe_sno,)
            )
            conn.commit()
        except Exception as e:
            print(f"❌ (루프 오류) SNO {recipe_sno} 처리 중 오류: {e}")
            save_price_cache(ingredient_price_cache) # 오류 시에도 캐시 저장
            continue

        # 6. (캐시 저장) 100개마다 캐시 파일 저장 (안전장치)
        if (index + 1) % 100 == 0:
            save_price_cache(ingredient_price_cache)

    # 7. 루프 완료 후 최종 저장
    save_price_cache(ingredient_price_cache)
    print("\n✅ 모든 레시피의 가격 계산 및 DB 저장이 완료되었습니다!")


# --- 4. 메인 스크립트 실행 ---
if __name__ == "__main__":
    
    # (네이버 API 키가 .env에 있는지 확인 - get_price_min_func.py가 해줌)
    
    conn = None
    try:
        conn = sqlite3.connect(DB_PATH)
        print(f"'{DB_PATH}' 연결 성공.")
        
        # 1단계: DB 컬럼 추가
        add_price_column_to_db(conn)
        
        # 2단계: 가격 계산 시작
        calculate_all_recipe_prices(conn)
        
    except Exception as e:
        print(f"❌ (메인 오류) 전체 프로세스 중단: {e}")
    finally:
        if conn:
            conn.close()
            print(f"\n'{DB_PATH}' 연결 종료.")