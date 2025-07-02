import polars as pl

def read_excel_to_objects(file_path):
    """
    엑셀 파일을 읽어서 각 행의 1, 2, 3열 데이터를 객체로 변환
    
    Args:
        file_path (str): 엑셀 파일 경로
    
    Returns:
        list: 각 행이 딕셔너리 객체로 변환된 리스트
    """
    # 엑셀 파일 읽기 (헤더 없음)
    df = pl.read_excel(file_path,has_header=False)
    print(df)


def main():
    # 파일 경로 설정
    file_path = "C:\\Users\\ssjm0\\Desktop\\map_by_python\\integrated.xlsx"
    try:
        # 엑셀 데이터를 객체로 변환
        data_objects = read_excel_to_objects(file_path)
        
        # 결과 출력
        print(f"총 {len(data_objects)}개의 데이터를 읽었습니다.")
        print("\n처음 5개 데이터:")
        for i, obj in enumerate(data_objects[:5]):
            print(f"{i+1}. 종류: {obj['종류']}, 주소: {obj['주소']}, 날짜: {obj['날짜']}")
            
        return data_objects
        
    except FileNotFoundError:
        print(f"파일을 찾을 수 없습니다: {file_path}")
    except Exception as e:
        print(f"오류가 발생했습니다: {e}")

# 실행
if __name__ == "__main__":
    data_objects = main()
