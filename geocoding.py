import requests
import sqlite3
import pandas as pd
import time
from typing import Tuple, Optional, List, Dict

class GeocodingCache:
    """지오코딩 결과를 캐싱하는 클래스"""
    
    def __init__(self, db_path: str = "geocoding_cache.db"):
        self.db_path = db_path
        self.init_db()
    
    def init_db(self):
        """캐시 데이터베이스 초기화"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS geocoding_cache (
                address TEXT PRIMARY KEY,
                latitude REAL,
                longitude REAL,
                full_address TEXT,
                cached_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.commit()
        conn.close()
    
    def get_cache(self, address: str) -> Optional[Tuple[float, float, str]]:
        """캐시에서 지오코딩 결과 조회"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            'SELECT latitude, longitude, full_address FROM geocoding_cache WHERE address = ?',
            (address,)
        )
        result = cursor.fetchone()
        conn.close()
        return result if result else None
    
    def set_cache(self, address: str, lat: float, lng: float, full_address: str):
        """지오코딩 결과를 캐시에 저장"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO geocoding_cache 
            (address, latitude, longitude, full_address) 
            VALUES (?, ?, ?, ?)
        ''', (address, lat, lng, full_address))
        conn.commit()
        conn.close()

class KakaoGeocoder:
    """카카오맵 API를 사용한 지오코딩 클래스"""
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://dapi.kakao.com/v2/local/search/address.json"
        self.cache = GeocodingCache()
        self.failed_geocoding = []
        
    def geocode_address(self, address: str) -> Optional[Tuple[float, float, str]]:
        """단일 주소를 지오코딩"""
        if not address or address.strip() == "":
            return None
            
        # 캐시에서 먼저 확인
        cached_result = self.cache.get_cache(address)
        if cached_result:
            return cached_result
        
        # API 호출
        headers = {
            'Authorization': f'KakaoAK {self.api_key}'
        }
        params = {
            'query': address
        }
        
        try:
            response = requests.get(self.base_url, headers=headers, params=params)
            response.raise_for_status()
            
            data = response.json()
            documents = data.get('documents', [])
            
            if documents:
                doc = documents[0]  # 첫 번째 결과 사용
                lng = float(doc['x'])
                lat = float(doc['y'])
                full_address = doc.get('address_name', address)
                
                # 캐시에 저장
                self.cache.set_cache(address, lat, lng, full_address)
                
                return (lat, lng, full_address)
            else:
                return None
                
        except Exception as e:
            print(f"지오코딩 실패 - 주소: {address}, 오류: {e}")
            return None
    
    def batch_geocode(self, addresses: List[str], delay: float = 0.02) -> Dict[int, Tuple[float, float, str]]:
        """주소 리스트를 배치 처리로 지오코딩"""
        results = {}
        self.failed_geocoding = []
        
        for idx, address in enumerate(addresses):
            if pd.isna(address) or address.strip() == "":
                continue
                
            result = self.geocode_address(address)
            if result:
                results[idx] = result
            else:
                self.failed_geocoding.append({
                    'row_index': idx,
                    'address': address,
                    'error': 'Geocoding failed'
                })
            
            # API 호출 제한을 위한 딜레이
            time.sleep(delay)
        
        return results
    
    def get_failed_geocoding(self) -> List[Dict]:
        """지오코딩 실패한 항목들 반환"""
        return self.failed_geocoding

def process_excel_file(file_path: str, api_key: str) -> pd.DataFrame:
    """엑셀 파일을 처리하여 지오코딩된 데이터프레임 반환"""
    
    # 엑셀 파일 읽기
    try:
        df = pd.read_excel(file_path)
    except Exception as e:
        raise Exception(f"엑셀 파일 읽기 실패: {e}")
    
    # 컬럼명 정규화
    expected_columns = ['type', 'address', 'date', '비고', 'geocoding']
    if len(df.columns) >= 2:
        df.columns = expected_columns[:len(df.columns)]
    
    # address 컬럼이 없으면 오류
    if 'address' not in df.columns:
        raise Exception("주소 컬럼(address)을 찾을 수 없습니다.")
    
        # date 컬럼을 문자열로 변환 (parquet 저장 오류 방지)
    if 'date' in df.columns:
        df['date'] = df['date'].astype(str)
    # 지오코더 초기화
    geocoder = KakaoGeocoder(api_key)
    
    # 주소 데이터 추출 (비어있지 않은 주소만)
    valid_addresses = df['address'].dropna().astype(str)
    valid_indices = valid_addresses.index.tolist()
    
    print(f"총 {len(valid_indices)}개의 주소를 지오코딩합니다...")
    
    # 배치 지오코딩 실행
    geocoding_results = geocoder.batch_geocode(valid_addresses.tolist())
    
    # 결과를 데이터프레임에 적용
    if 'geocoding' not in df.columns:
        df['geocoding'] = ""
    
    for idx, (lat, lng, full_address) in geocoding_results.items():
        df.loc[valid_indices[idx], 'geocoding'] = f"{lat},{lng}"
    
    # 실패한 지오코딩 정보 출력
    failed_items = geocoder.get_failed_geocoding()
    if failed_items:
        print(f"\n지오코딩 실패한 항목 ({len(failed_items)}개):")
        for item in failed_items:
            print(f"  행 {item['row_index'] + 1}: {item['address']}")
    
    print(f"지오코딩 완료: 성공 {len(geocoding_results)}개, 실패 {len(failed_items)}개")
    
    return df

def save_dataframe(df: pd.DataFrame, output_path: str = "geocoded_data.parquet"):
    """데이터프레임을 parquet 형식으로 저장"""
    try:
        df.to_parquet(output_path, index=False)
        print(f"데이터가 {output_path}에 저장되었습니다.")
    except Exception as e:
        print(f"파일 저장 실패: {e}") 