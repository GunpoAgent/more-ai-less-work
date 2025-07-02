"""
import folium as f

map = f.Map(location=[45.5236, -122.6750], zoom_start=12)
map.save("map.html")
"""


import sys
import os
import pandas as pd
import folium
import json
from datetime import datetime
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QPushButton, QLabel, QFileDialog, 
                             QMessageBox, QProgressBar, QTextEdit, QSplitter,
                             QCheckBox, QScrollArea, QFrame)
from PyQt5.QtWebEngineWidgets import QWebEngineView
from PyQt5.QtCore import QUrl, QThread, pyqtSignal, Qt
from geocoding import process_excel_file, save_dataframe
from openpyxl import load_workbook
from openpyxl.styles import PatternFill

# API 키 (README.md에서 가져옴)
KAKAO_REST_API_KEY = "f4ca9d9fc9096a0f4f26a636e9d0ee29"

class GeocodingThread(QThread):
    """지오코딩을 백그라운드에서 처리하는 스레드"""
    
    progress_update = pyqtSignal(str)
    finished_signal = pyqtSignal(pd.DataFrame, list)
    error_signal = pyqtSignal(str)
    
    def __init__(self, file_path: str):
        super().__init__()
        self.file_path = file_path
        
    def run(self):
        try:
            self.progress_update.emit("엑셀 파일을 읽는 중...")
            df = process_excel_file(self.file_path, KAKAO_REST_API_KEY)
            
            self.progress_update.emit("지오코딩 완료! 결과를 저장하는 중...")
            save_dataframe(df)
            
            # 실패한 항목들 수집
            failed_items = []
            for idx, row in df.iterrows():
                if pd.isna(row.get('geocoding', '')) or row.get('geocoding', '') == '':
                    if not pd.isna(row.get('address', '')) and row.get('address', '') != '':
                        failed_items.append({
                            'row_index': idx + 1,
                            'type': row.get('type', ''),
                            'address': row.get('address', ''),
                            'date': row.get('date', '')
                        })
            
            self.finished_signal.emit(df, failed_items)
            
        except Exception as e:
            self.error_signal.emit(str(e))

class MapGeocodingApp(QMainWindow):
    """메인 애플리케이션 클래스"""
    
    def __init__(self):
        super().__init__()
        self.current_df = None
        self.failed_items = []
        self.metadata_file = "app_metadata.json"
        self.parquet_file = "geocoded_data.parquet"
        self.color_map = {}
        self.type_checkboxes = {}
        self.init_ui()
        self.load_last_session()
        
    def init_ui(self):
        """UI 초기화"""
        self.setWindowTitle("지오코딩 & 지도 시각화 애플리케이션")
        self.setGeometry(100, 100, 1400, 800)
        
        # 중앙 위젯
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # 메인 레이아웃
        main_layout = QHBoxLayout(central_widget)
        
        # 스플리터로 좌우 분할
        splitter = QSplitter(Qt.Horizontal)
        main_layout.addWidget(splitter)
        
        # 좌측 지도 영역
        self.create_map_panel(splitter)
        
        # 우측 컨트롤 패널
        self.create_control_panel(splitter)
        
        # 스플리터 비율 설정
        splitter.setSizes([1000, 400])
        
    def create_control_panel(self, parent):
        """우측 컨트롤 패널 생성"""
        control_widget = QWidget()
        control_layout = QVBoxLayout(control_widget)
        
        # 마지막 갱신 정보
        self.update_date_label = QLabel("마지막 갱신 날짜: -")
        self.update_date_label.setStyleSheet("font-size: 16px; font-weight: bold; margin: 10px;")
        control_layout.addWidget(self.update_date_label)
        
        self.update_file_label = QLabel("저장된 파일: -")
        self.update_file_label.setStyleSheet("font-size: 16px; font-weight: bold; margin: 10px;")
        control_layout.addWidget(self.update_file_label)
        
        # 제목
        title_label = QLabel("지오코딩 & 지도 시각화")
        title_label.setStyleSheet("font-size: 16px; font-weight: bold; margin: 10px;")
        control_layout.addWidget(title_label)
        
        # 기본 엑셀 양식 다운로드 버튼
        self.download_button = QPushButton("기본 엑셀 양식 DOWNLOAD")
        self.download_button.clicked.connect(self.download_template)
        control_layout.addWidget(self.download_button)
        
        # 파일 선택 버튼
        self.file_button = QPushButton("UPLOAD EXCEL")
        self.file_button.clicked.connect(self.select_file)
        control_layout.addWidget(self.file_button)
        
        # 선택된 파일 경로 표시
        self.file_label = QLabel("selected file: 없음")
        self.file_label.setWordWrap(True)
        control_layout.addWidget(self.file_label)
        
        # 진행 상황 표시
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        control_layout.addWidget(self.progress_bar)
        
        # 상태 메시지
        self.status_label = QLabel("준비됨")
        control_layout.addWidget(self.status_label)
        
        # 결과 텍스트 영역
        self.result_text = QTextEdit()
        self.result_text.setMaximumHeight(200)
        self.result_text.setPlaceholderText("Geocoding Result:")
        control_layout.addWidget(self.result_text)
        
        # Check Failed List 버튼
        self.check_failed_button = QPushButton("CHECK FAILED LIST")
        self.check_failed_button.clicked.connect(self.export_failed_data)
        self.check_failed_button.setEnabled(False)
        control_layout.addWidget(self.check_failed_button)
        
        control_layout.addStretch()
        parent.addWidget(control_widget)
        
    def create_map_panel(self, parent):
        """좌측 지도 패널 생성"""
        # 지도 패널을 위한 컨테이너 위젯
        map_container = QWidget()
        map_layout = QVBoxLayout(map_container)
        map_layout.setContentsMargins(0, 0, 0, 0)
        
        # 웹뷰
        self.web_view = QWebEngineView()
        map_layout.addWidget(self.web_view)
        
        # 범례 오버레이 위젯 생성
        self.create_legend_overlay(map_container)
        
        parent.addWidget(map_container)
        
    def create_legend_overlay(self, parent):
        """지도 위에 범례 오버레이 생성"""
        # 범례 컨테이너
        self.legend_overlay = QWidget(parent)
        self.legend_overlay.setStyleSheet("""
            QWidget {
                background-color: rgba(255, 255, 255, 240);
                border: 2px solid #666666;
                border-radius: 8px;
                padding: 5px;
            }
        """)
        
        # 범례 레이아웃
        overlay_layout = QVBoxLayout(self.legend_overlay)
        overlay_layout.setContentsMargins(10, 5, 10, 5)
        overlay_layout.setSpacing(3)
        
        # 제목
        legend_title = QLabel("Marker Type:")
        legend_title.setStyleSheet("font-weight: bold; font-size: 14px; margin-bottom: 5px;")
        overlay_layout.addWidget(legend_title)
        
        # 스크롤 영역
        self.legend_scroll = QScrollArea()
        self.legend_scroll.setWidgetResizable(True)
        self.legend_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.legend_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.legend_scroll.setStyleSheet("""
            QScrollArea {
                border: none;
                background-color: transparent;
            }
            QScrollBar:vertical {
                width: 12px;
                background: rgba(0,0,0,0);
            }
            QScrollBar::handle:vertical {
                background: #888;
                border-radius: 6px;
            }
        """)
        
        self.legend_widget = QWidget()
        self.legend_layout = QVBoxLayout(self.legend_widget)
        self.legend_layout.setContentsMargins(0, 0, 0, 0)
        self.legend_layout.setSpacing(2)
        
        # 모두 선택 체크박스
        self.select_all_checkbox = QCheckBox("모두 선택")
        self.select_all_checkbox.setChecked(True)
        self.select_all_checkbox.clicked.connect(self.toggle_all_types)
        self.select_all_checkbox.setStyleSheet("font-weight: bold; color: #333;")
        self.legend_layout.addWidget(self.select_all_checkbox)
        
        # 구분선
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        line.setStyleSheet("color: #ccc;")
        self.legend_layout.addWidget(line)
        
        self.legend_scroll.setWidget(self.legend_widget)
        overlay_layout.addWidget(self.legend_scroll)
        
        # 초기 크기 및 위치 설정 (가로 2/3, 세로 2배)
        self.legend_overlay.resize(167, 400)  # 기본 250px의 2/3 ≈ 167px, 200px의 2배 = 400px
        self.legend_overlay.hide()  # 초기에는 숨김
        
    def resizeEvent(self, event):
        """창 크기 변경 시 범례 위치 조정"""
        super().resizeEvent(event)
        self.position_legend_overlay()
        
    def load_default_map(self):
        """기본 지도 로드"""
        # 경기도 군포시 청백리길6 좌표 (README.md에서 언급된 기본 위치)
        tiles = "http://mt0.google.com/vt/lyrs=m&hl=ko&x={x}&y={y}&z={z}"
        attr = "Google"
        map_folium = folium.Map(
            location=[37.36163002691529, 126.93520593427584], 
            zoom_start=11,
            tiles=tiles,
            attr=attr
        )
        
        # 기본 위치에 마커 추가
        folium.Marker(
            [37.36163002691529, 126.93520593427584],
            popup="기본 위치: 경기도 군포시 청백리길6",
            tooltip="기본 위치",
            icon=folium.Icon(color='red', icon='home')
        ).add_to(map_folium)
        
        html_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "map.html")
        map_folium.save(html_file)
        self.web_view.load(QUrl.fromLocalFile(html_file))
        
        # 범례 숨기기
        if hasattr(self, 'legend_overlay'):
            self.legend_overlay.hide()
            
    def select_file(self):
        """엑셀 파일 선택"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, 
            "엑셀 파일 선택", 
            "", 
            "Excel files (*.xlsx *.xls)"
        )
        
        if file_path:
            self.current_file_path = file_path
            self.file_label.setText(f"selected file: {os.path.basename(file_path)}")
            self.status_label.setText("파일이 선택되었습니다. 지오코딩을 시작합니다...")
            # 자동으로 지오코딩 실행
            self.start_geocoding()

    def download_template(self):
        """기본 엑셀 양식 다운로드"""
        template_file = "integrated.xlsx"
        
        if not os.path.exists(template_file):
            QMessageBox.warning(self, "파일 없음", "기본 양식 파일(integrated.xlsx)이 존재하지 않습니다.")
            return
            
        # 저장할 위치 선택
        save_path, _ = QFileDialog.getSaveFileName(
            self, 
            "기본 엑셀 양식 저장", 
            "기본_지오코딩_양식.xlsx",
            "Excel files (*.xlsx)"
        )
        
        if save_path:
            try:
                import shutil
                shutil.copy2(template_file, save_path)
                QMessageBox.information(self, "다운로드 완료", f"기본 양식이 다음 위치에 저장되었습니다:\n{save_path}")
            except Exception as e:
                QMessageBox.critical(self, "다운로드 실패", f"파일 저장 중 오류가 발생했습니다:\n{e}")
 
            
    def start_geocoding(self):
        """지오코딩 시작"""
        if not hasattr(self, 'current_file_path'):
            QMessageBox.warning(self, "파일 선택", "먼저 파일을 선택해주세요.")
            return
            
        # UI 업데이트
        self.file_button.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)  # 무한 진행바
        self.status_label.setText("지오코딩 진행 중...")
        self.result_text.clear()
        
        # 백그라운드 스레드에서 지오코딩 실행
        self.geocoding_thread = GeocodingThread(self.current_file_path)
        self.geocoding_thread.progress_update.connect(self.update_progress)
        self.geocoding_thread.finished_signal.connect(self.geocoding_finished)
        self.geocoding_thread.error_signal.connect(self.geocoding_error)
        self.geocoding_thread.start()
        
    def update_progress(self, message):
        """진행 상황 업데이트"""
        self.status_label.setText(message)
        
    def geocoding_finished(self, df, failed_items):
        """지오코딩 완료 처리"""
        self.current_df = df
        
        # failed_items의 datetime 객체를 문자열로 변환 (JSON 직렬화 오류 방지)
        processed_failed_items = []
        for item in failed_items:
            processed_item = item.copy()
            if 'date' in processed_item and hasattr(processed_item['date'], 'strftime'):
                processed_item['date'] = processed_item['date'].strftime('%Y-%m-%d %H:%M:%S')
            processed_failed_items.append(processed_item)
        
        self.failed_items = processed_failed_items
        
        # 마지막 갱신 정보 업데이트
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.update_date_label.setText(f"마지막 갱신 날짜: {current_time}")
        self.update_file_label.setText(f"저장된 파일: {os.path.basename(self.current_file_path)}")
        
        # UI 업데이트
        self.progress_bar.setVisible(False)
        self.file_button.setEnabled(True)
        
        # Check Failed List 버튼 활성화 (실패한 항목이 있는 경우)
        self.check_failed_button.setEnabled(len(failed_items) > 0)
        
        # 자동으로 지도에 마커 표시
        self.status_label.setText("지도에 마커를 표시하는 중...")
        self.create_map_with_markers()
        
        # 결과 표시
        total_count = len(df)
        success_count = len(df[df['geocoding'].notna() & (df['geocoding'] != '')])
        failed_count = len(failed_items)
        
        result_text = f"Geocoding Result:\n"
        result_text += f"=== 지오코딩 완료 ===\n"
        result_text += f"총 데이터: {total_count}개\n"
        result_text += f"성공: {success_count}개\n"
        result_text += f"실패: {failed_count}개\n\n"
        result_text += f"데이터가 geocoded_data.parquet 파일로 저장되었습니다."
        
        self.result_text.setPlainText(result_text)
        
        self.status_label.setText(f"완료! 지도에 {success_count}개의 마커가 표시되었습니다.")
        
        # 메타데이터 저장
        self.save_session_metadata()
        
    def geocoding_error(self, error_message):
        """지오코딩 오류 처리"""
        self.progress_bar.setVisible(False)
        self.file_button.setEnabled(True)
        self.status_label.setText("지오코딩 중 오류가 발생했습니다.")
        
        QMessageBox.critical(self, "오류", f"지오코딩 중 오류가 발생했습니다:\n{error_message}")
    
    def export_failed_data(self):
        """실패한 데이터를 빨간색으로 처리하여 엑셀 파일로 내보내기"""
        if not self.failed_items:
            QMessageBox.information(self, "정보", "실패한 지오코딩 항목이 없습니다.")
            return
            
        try:
            # 원본 파일 이름에서 확장자 제거
            original_filename = os.path.splitext(os.path.basename(self.current_file_path))[0]
            failed_filename = f"FAILED_{original_filename}.xlsx"
            
            # 저장할 위치 선택
            save_path, _ = QFileDialog.getSaveFileName(
                self, 
                "실패한 항목 저장", 
                failed_filename,
                "Excel files (*.xlsx)"
            )
            
            if save_path:
                # 원본 파일을 복사하여 새 파일 생성
                import shutil
                shutil.copy2(self.current_file_path, save_path)
                
                # 실패한 행들을 빨간색으로 처리
                wb = load_workbook(save_path)
                ws = wb.active
                
                # 빨간색 배경 스타일
                red_fill = PatternFill(start_color="FFFF0000", end_color="FFFF0000", fill_type="solid")
                
                # 실패한 행들에 빨간색 배경 적용
                for item in self.failed_items:
                    row_num = item['row_index'] + 1  # 헤더 고려
                    for col in range(1, ws.max_column + 1):
                        ws.cell(row=row_num, column=col).fill = red_fill
                
                wb.save(save_path)
                
                QMessageBox.information(
                    self, 
                    "내보내기 완료", 
                    f"실패한 {len(self.failed_items)}개 항목이 빨간색으로 표시되어 저장되었습니다:\n{save_path}"
                )
                
        except Exception as e:
            QMessageBox.critical(self, "내보내기 실패", f"파일 저장 중 오류가 발생했습니다:\n{e}")
    
    def update_legend_checkboxes(self):
        """범례 체크박스 업데이트"""
        # 기존 체크박스들 제거 (모두 선택과 구분선 제외)
        for i in reversed(range(self.legend_layout.count())):
            if i > 1:  # 모두 선택과 구분선 이후의 항목들만 제거
                child = self.legend_layout.takeAt(i)
                if child.widget():
                    child.widget().deleteLater()
        
        self.type_checkboxes.clear()
        
        if self.current_df is None:
            self.legend_overlay.hide()
            return
            
        # 색상 매핑 업데이트
        unique_types = self.current_df['type'].dropna().unique()
        available_colors = ['red', 'blue', 'green', 'purple', 'orange', 'darkred', 'lightred', 
                           'beige', 'darkblue', 'darkgreen', 'cadetblue', 'darkpurple', 
                           'white', 'pink', 'lightblue', 'lightgreen', 'gray', 'black', 'lightgray']
        
        self.color_map = {}
        for i, place_type in enumerate(unique_types):
            self.color_map[place_type] = available_colors[i % len(available_colors)]
        
        # 타입별 개수 계산
        type_counts = self.current_df[self.current_df['geocoding'].notna() & (self.current_df['geocoding'] != '')]['type'].value_counts()
        
        # 각 타입별 체크박스 생성
        for place_type, color in self.color_map.items():
            count = type_counts.get(place_type, 0)
            checkbox = QCheckBox(f"{place_type} ({count}개)")
            checkbox.setChecked(True)
            checkbox.clicked.connect(self.update_map_markers)
            checkbox.setStyleSheet("color: #333; font-size: 12px;")
            self.type_checkboxes[place_type] = checkbox
            self.legend_layout.addWidget(checkbox)
        
        # 범례 오버레이 표시 및 위치 조정
        self.legend_overlay.show()
        self.position_legend_overlay()
            
    def position_legend_overlay(self):
        """범례 오버레이 위치 조정"""
        if hasattr(self, 'legend_overlay') and hasattr(self, 'web_view'):
            # 지도 영역의 좌표 계산
            web_view_rect = self.web_view.geometry()
            parent_rect = self.legend_overlay.parent().geometry()
            
            # 왼쪽 아래 위치 (여백 20px)
            x = 20
            y = web_view_rect.height() - self.legend_overlay.height() - 20
            self.legend_overlay.move(x, y)
            
    def toggle_all_types(self):
        """모든 타입 체크박스 토글"""
        is_checked = self.select_all_checkbox.isChecked()
        for checkbox in self.type_checkboxes.values():
            checkbox.setChecked(is_checked)
        self.update_map_markers()
        
    def update_map_markers(self):
        """체크박스 상태에 따라 지도 마커 업데이트"""
        if self.current_df is None:
            return
            
        # 선택된 타입들 수집
        selected_types = []
        for place_type, checkbox in self.type_checkboxes.items():
            if checkbox.isChecked():
                selected_types.append(place_type)
        
        # 모두 선택 체크박스 상태 업데이트
        if len(selected_types) == len(self.type_checkboxes):
            self.select_all_checkbox.setChecked(True)
        elif len(selected_types) == 0:
            self.select_all_checkbox.setChecked(False)
        else:
            self.select_all_checkbox.setChecked(False)
        
        # 지도 업데이트
        self.create_filtered_map(selected_types)
        
    def create_filtered_map(self, selected_types):
        """선택된 타입들만 표시하는 지도 생성"""
        # 기본 지도 생성 (경기도 군포시청 중심)
        tiles = "http://mt0.google.com/vt/lyrs=m&hl=ko&x={x}&y={y}&z={z}"
        attr = "Google"
        map_folium = folium.Map(
            location=[37.36163002691529, 126.93520593427584], 
            zoom_start=11,
            tiles=tiles,
            attr=attr
        )
        
        # 마커 추가 (선택된 타입만)
        marker_count = 0
        for idx, row in self.current_df.iterrows():
            geocoding_data = row.get('geocoding', '')
            place_type = row.get('type', '기타')
            
            # 선택된 타입만 표시
            if place_type not in selected_types:
                continue
                
            if pd.notna(geocoding_data) and geocoding_data != '':
                try:
                    lat, lng = map(float, geocoding_data.split(','))
                    address = row.get('address', '')
                    date = row.get('date', '')
                    note = row.get('비고', '')
                    
                    # 색상 선택
                    color = self.color_map.get(place_type, 'gray')
                    
                    # 팝업 내용
                    popup_content = f"""
                    <b>타입:</b> {place_type}<br>
                    <b>주소:</b> {address}<br>
                    <b>날짜:</b> {date}<br>
                    <b>비고:</b> {note}
                    """
                    
                    folium.Marker(
                        [lat, lng],
                        popup=folium.Popup(popup_content, max_width=300),
                        tooltip=f"{place_type}: {address}",
                        icon=folium.Icon(color=color, icon='info-sign')
                    ).add_to(map_folium)
                    
                    marker_count += 1
                    
                except Exception as e:
                    print(f"마커 생성 실패 - 행 {idx}: {e}")
        
        # 기본 위치 마커 (빨간색)
        folium.Marker(
            [37.36163002691529, 126.93520593427584],
            popup="기본 위치: 경기도 군포시 청백리길6",
            tooltip="기본 위치",
            icon=folium.Icon(color='red', icon='home')
        ).add_to(map_folium)
        
        # 지도 저장 및 표시
        html_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "map.html")
        map_folium.save(html_file)
        self.web_view.load(QUrl.fromLocalFile(html_file))
        
    def create_map_with_markers(self):
        """지오코딩된 데이터로 지도에 마커 표시"""
        if self.current_df is None:
            QMessageBox.warning(self, "데이터 없음", "먼저 지오코딩을 실행해주세요.")
            return
        
        # 범례 체크박스 업데이트
        self.update_legend_checkboxes()
        
        # 모든 타입이 선택된 상태로 지도 생성
        selected_types = list(self.color_map.keys())
        self.create_filtered_map(selected_types)

    def save_session_metadata(self):
        """현재 세션 메타데이터 저장"""
        if hasattr(self, 'current_file_path'):
            metadata = {
                "last_update": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "source_file": os.path.basename(self.current_file_path),
                "full_path": self.current_file_path,
                "parquet_file": self.parquet_file,
                "total_records": len(self.current_df) if self.current_df is not None else 0,
                "success_count": len(self.current_df[self.current_df['geocoding'].notna() & (self.current_df['geocoding'] != '')]) if self.current_df is not None else 0,
                "failed_items": self.failed_items
            }
            
            try:
                with open(self.metadata_file, 'w', encoding='utf-8') as f:
                    json.dump(metadata, f, ensure_ascii=False, indent=2)
            except Exception as e:
                print(f"메타데이터 저장 실패: {e}")
    
    def load_last_session(self):
        """마지막 세션 로드"""
        try:
            # 메타데이터 파일과 parquet 파일이 모두 존재하는지 확인
            if os.path.exists(self.metadata_file) and os.path.exists(self.parquet_file):
                
                # 메타데이터 로드
                with open(self.metadata_file, 'r', encoding='utf-8') as f:
                    metadata = json.load(f)
                
                # parquet 파일 로드
                self.current_df = pd.read_parquet(self.parquet_file)
                
                # 실패한 항목들 로드
                self.failed_items = metadata.get('failed_items', [])
                
                # UI 업데이트
                self.update_date_label.setText(f"마지막 갱신 날짜: {metadata['last_update']}")
                self.update_file_label.setText(f"저장된 파일: {metadata['source_file']}")
                
                # Check Failed List 버튼 활성화 (실패한 항목이 있는 경우)
                self.check_failed_button.setEnabled(len(self.failed_items) > 0)
                
                # 결과 텍스트 업데이트
                result_text = f"Result:\n"
                result_text += f"=== 저장된 데이터 로드 ===\n"
                result_text += f"Total Data: {metadata['total_records']}\n"
                result_text += f"Success: {metadata['success_count']}\n"
                result_text += f"Failed: {metadata['total_records'] - metadata['success_count']}\n\n"
                
                if self.failed_items:
                    result_text += f"=== 실패한 지오코딩 항목 ===\n"
                    for item in self.failed_items:
                        result_text += f"Row {item['row_index']}: [{item['type']}] {item['address']}\n"
                    result_text += f"\n"
                
                result_text += f"Data loaded from {self.parquet_file} file."
                
                self.result_text.setPlainText(result_text)
                
                # 자동으로 지도에 마커 표시
                self.create_map_with_markers()
                
                total_records = metadata['total_records']
                success_count = metadata['success_count']
                failed_count = total_records - success_count

                self.status_label.setText(f"표시된 마커 : {success_count}\n 총 데이터 : {total_records}\n 실패 : {failed_count}")
                
                return True
                
        except Exception as e:
            print(f"세션 로드 실패: {e}")
        
        # 세션 로드에 실패하면 기본 지도 로드
        self.load_default_map()
        return False

def main():
    app = QApplication(sys.argv)
    
    # 애플리케이션 정보 설정
    app.setApplicationName("지오코딩 & 지도 시각화")
    app.setApplicationVersion("1.0")
    
    window = MapGeocodingApp()
    window.show()
    
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
