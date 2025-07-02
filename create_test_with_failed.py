import pandas as pd

# 성공/실패가 섞인 테스트 데이터 생성
data = {
    'type': ['카페', '마트', '병원', '학교', '은행', '약국'],
    'address': [
        '경기도 군포시 청백리길6',           # 성공할 주소
        '서울특별시 강남구 테헤란로 152',    # 성공할 주소
        '존재하지않는주소123번지',           # 실패할 주소
        '경기도 성남시 분당구 정자일로 95',  # 성공할 주소
        '가짜주소 999-999',               # 실패할 주소
        '서울특별시 강남구 강남대로 396'     # 성공할 주소
    ],
    'date': ['2024-01-01', '2024-01-02', '2024-01-03', '2024-01-04', '2024-01-05', '2024-01-06'],
    '비고': ['성공예상', '성공예상', '실패예상', '성공예상', '실패예상', '성공예상'],
    'geocoding': [
        '37.3610235158794,126.935316401541',  # 성공 데이터
        '37.5012743036055,127.039492155632',  # 성공 데이터
        '',                                    # 실패 데이터 (빈 문자열)
        '37.3632147090662,127.111835861628',  # 성공 데이터
        '',                                    # 실패 데이터 (빈 문자열)
        '37.5176877767793,127.047714838609'   # 성공 데이터
    ]
}

df = pd.DataFrame(data)
df.to_parquet('test_with_failed.parquet', index=False)

# 메타데이터도 생성
import json
from datetime import datetime

metadata = {
    "last_update": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    "source_file": "test_with_failed_data.xlsx",
    "full_path": "test_with_failed_data.xlsx",
    "parquet_file": "test_with_failed.parquet",
    "total_records": 6,
    "success_count": 4
}

with open('test_metadata.json', 'w', encoding='utf-8') as f:
    json.dump(metadata, f, ensure_ascii=False, indent=2)

print("실패 포함 테스트 데이터가 생성되었습니다:")
print(f"- test_with_failed.parquet")
print(f"- test_metadata.json")
print(f"총 {len(df)}개 데이터 중 성공 4개, 실패 2개") 