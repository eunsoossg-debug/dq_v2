import sys
import json
import pandas as pd
import re
import os
from PyQt6.QtWidgets import (QApplication, QMainWindow, QPushButton, QVBoxLayout, 
                             QHBoxLayout, QWidget, QFileDialog, QLabel, QTableWidget, 
                             QTableWidgetItem, QCheckBox, QMessageBox, QHeaderView, QFrame)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont

class DQChecker:
    def __init__(self, df, rules):
        self.df = df
        self.rules = rules.get("evaluation_rules", {})

    def check_value_completeness(self):
        total_cells = self.df.size
        null_count = self.df.isnull().sum().sum()
        return (1 - (null_count / total_cells)) * 100 if total_cells > 0 else 100

    def check_record_completeness(self):
        empty_rows = self.df.isnull().all(axis=1).sum()
        return (1 - (empty_rows / len(self.df))) * 100 if len(self.df) > 0 else 100

    def check_syntax_validity(self):
        syntax_rules = self.rules.get("3_syntax_validity", {}).get("columns", {})
        if not syntax_rules: return 100.0
        invalid_count, total_checks = 0, 0
        for col, pattern in syntax_rules.items():
            if col in self.df.columns:
                series = self.df[col].dropna()
                if not series.empty:
                    def clean_str(x):
                        s = str(x)
                        return s[:-2] if s.endswith('.0') else s
                    matches = series.apply(clean_str).apply(lambda x: re.match(pattern, x) is not None)
                    invalid_count += (~matches).sum()
                    total_checks += len(series)
        return (1 - (invalid_count / total_checks)) * 100 if total_checks > 0 else 100

    def check_semantic_validity(self):
        semantic_rules = self.rules.get("4_semantic_validity", {}).get("columns", {})
        if not semantic_rules: return 100.0
        invalid_count, total_checks = 0, 0
        for col, valid_list in semantic_rules.items():
            if col in self.df.columns:
                invalid_count += (~self.df[col].isin(valid_list)).sum()
                total_checks += len(self.df)
        return (1 - (invalid_count / total_checks)) * 100 if total_checks > 0 else 100

    def check_range_validity(self):
        range_rules = self.rules.get("5_range_validity", {}).get("columns", {})
        if not range_rules: return 100.0
        invalid_count, total_checks = 0, 0
        for col, limits in range_rules.items():
            if col in self.df.columns:
                temp_series = pd.to_numeric(self.df[col], errors='coerce')
                invalid_count += ((temp_series < limits['min']) | (temp_series > limits['max'])).sum()
                total_checks += len(self.df)
        return (1 - (invalid_count / total_checks)) * 100 if total_checks > 0 else 100

    def check_relationship_validity(self):
        rel_rules = self.rules.get("6_relationship_validity", {}).get("rules", [])
        if not rel_rules: return 100.0
        total_violations = 0
        for rule in rel_rules:
            try:
                valid_count = len(self.df.query(rule["formula"], engine='python'))
                total_violations += (len(self.df) - valid_count)
            except: continue
        total_checks = len(self.df) * len(rel_rules)
        return (1 - (total_violations / total_checks)) * 100 if total_checks > 0 else 100

    def check_referential_integrity(self):
        ref_rules = self.rules.get("7_referential_integrity", {}).get("checks", [])
        if not ref_rules: return 100.0
        total_violations = 0
        for rule in ref_rules:
            try:
                p_path = rule["parent_file"]
                p_df = pd.read_csv(p_path) if p_path.endswith('.csv') else pd.read_excel(p_path)
                total_violations += (~self.df[rule["child_column"]].isin(p_df[rule["parent_column"]])).sum()
            except: continue
        total_checks = len(self.df) * len(ref_rules)
        return (1 - (total_violations / total_checks)) * 100 if total_checks > 0 else 100

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Data Quality Pro - Studio")
        self.setMinimumSize(1100, 800)
        self.data_df = None
        self.rules = None
        self.init_ui()
        self.apply_style()

    def apply_style(self):
        self.setStyleSheet("""
            /* 전체 배경 및 텍스트 설정 */
            QMainWindow { background-color: #0F111A; }
            QWidget { color: #CFD8DC; font-family: 'Segoe UI', sans-serif; }
            
            /* 버튼 스타일 */
            QPushButton {
                background-color: #1A1D2E; border: 1px solid #2A2F45;
                border-radius: 8px; padding: 12px; font-weight: bold;
            }
            QPushButton:hover { background-color: #242942; border-color: #00A3FF; }
            QPushButton#run_btn {
                background-color: #00A3FF; color: white; font-size: 16px; margin-top: 15px; border: none;
            }
            
            /* 테이블 스타일 */
           QTableWidget {
                background-color: #161925; /* 테이블 자체 배경 */
                alternate-background-color: #1F2335; /* 줄마다 색상 다르게 (필요시) */
                border: 1px solid #232738;
                gridline-color: #232738; /* 칸 구분선 색상 */
                border-radius: 12px;
                color: #CFD8DC;
            }

            /* 2. 테이블 내부 아이템(글자/칸) 배경 강제 지정 */
            QTableWidget::item {
                background-color: #161925;
                padding: 5px;
            }

            /* 3. 데이터 선택 시 배경색 (하얗게 변하는 것 방지) */
            QTableWidget::item:selected {
                background-color: #00A3FF;
                color: white;
            }

            /* 4. 헤더(Dimension, Accuracy 칸) 디자인 */
            QHeaderView::section {
                background-color: #1F2335;
                color: #78909C;
                padding: 12px;
                border: none;
                font-weight: bold;
            }

            /* 5. 스크롤바가 붙는 코너(모퉁이) 부분 하얀색 방지 */
            QAbstractScrollArea QWidget {
                background-color: #161925;
            }

            /* 6. 스크롤바 스타일 (강제 적용) */
            QScrollBar:vertical {
                border: none;
                background: #161925;
                width: 10px;
            }
            QScrollBar::handle:vertical {
                background: #37474F;
                border-radius: 5px;
            }
            QScrollBar::handle:vertical:hover {
                background: #00A3FF;
            }
            QHeaderView::section {
                background-color: #1F2335; color: #78909C; padding: 12px; border: none;
            }
            
            /* 하단 등급 컨테이너 */
            #grade_container {
                background-color: #1A1D2E; border: 1px solid #2D334A; border-radius: 15px;
            }

            /* --- 스크롤바 강제 스타일 적용 (이 부분을 수정했습니다) --- */
            QScrollBar:vertical {
                border: none;
                background-color: #161925; /* 배경색 강제 지정 */
                width: 12px;
                margin: 0px;
            }
            QScrollBar::handle:vertical {
                background-color: #454D66; /* 바 색상을 조금 더 밝게 조정 */
                min-height: 30px;
                border-radius: 6px;
            }
            QScrollBar::handle:vertical:hover {
                background-color: #00A3FF;
            }
            /* 스크롤바 화살표 버튼을 완전히 투명하게 삭제 */
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                border: none;
                background: none;
                height: 0px;
            }
            QScrollBar::up-arrow:vertical, QScrollBar::down-arrow:vertical {
                background: none;
            }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                background: none;
            }

            /* 가로 스크롤바도 동일하게 적용 */
            QScrollBar:horizontal {
                border: none;
                background-color: #161925;
                height: 12px;
            }
            QScrollBar::handle:horizontal {
                background-color: #454D66;
                border-radius: 6px;
            }
        """)

    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(25, 25, 25, 25)

        sidebar = QVBoxLayout()
        logo = QLabel("DQ STUDIO")
        logo.setStyleSheet("font-size: 24px; font-weight: 800; color: #00A3FF; margin-bottom: 25px;")
        sidebar.addWidget(logo)

        self.btn_data = QPushButton("📁 Load Dataset")
        self.btn_json = QPushButton("⚙️ Load Rules (JSON)")
        self.btn_data.clicked.connect(self.load_file)
        self.btn_json.clicked.connect(self.load_json)
        sidebar.addWidget(self.btn_data)
        sidebar.addWidget(self.btn_json)

        sidebar.addSpacing(35)
        sidebar.addWidget(QLabel("ANALYSIS METRICS"))
        self.checks = {
            "Value": QCheckBox("데이터값완전성"), "Record": QCheckBox("데이터레코드완전성"),
            "Syntax": QCheckBox("구문유효성"), "Semantic": QCheckBox("의미유효성"),
            "Range": QCheckBox("범위유효성"), "Rel": QCheckBox("관계유효성"), "Ref": QCheckBox("참조무결일관성")
        }
        for cb in self.checks.values():
            cb.setChecked(True)
            sidebar.addWidget(cb)

        sidebar.addStretch()
        self.btn_run = QPushButton("START ANALYSIS")
        self.btn_run.setObjectName("run_btn")
        self.btn_run.clicked.connect(self.run_eval)
        sidebar.addWidget(self.btn_run)
        
        self.status_bar = QLabel("System Ready")
        sidebar.addWidget(self.status_bar)

        content_area = QVBoxLayout()
        self.result_table = QTableWidget(0, 2)
        self.result_table.setHorizontalHeaderLabels(["Dimension", "Accuracy"])
        self.result_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        content_area.addWidget(self.result_table)

        # --- 등급 판정 하단 패널 ---
        self.grade_container = QFrame()
        self.grade_container.setObjectName("grade_container")
        self.grade_container.setFixedHeight(160)
        grade_layout = QHBoxLayout(self.grade_container)

        self.grade_badge = QLabel("-")
        self.grade_badge.setFixedSize(90, 90)
        self.grade_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.grade_badge.setStyleSheet("background-color: #232738; border-radius: 45px; color: #444; font-size: 45px; font-weight: bold; border: 2px solid #2D334A;")
        
        text_info = QVBoxLayout()
        self.grade_title = QLabel("QUALITY REPORT SUMMARY")
        self.grade_title.setStyleSheet("color: #546E7A; font-size: 12px; font-weight: bold;")
        self.avg_score_label = QLabel("Wait for analysis...")
        self.avg_score_label.setStyleSheet("color: #FFFFFF; font-size: 28px; font-weight: bold;")
        self.grade_desc = QLabel("Result description will appear here.")
        self.grade_desc.setStyleSheet("color: #546E7A; font-size: 14px;")
        
        text_info.addWidget(self.grade_title)
        text_info.addWidget(self.avg_score_label)
        text_info.addWidget(self.grade_desc)

        grade_layout.addWidget(self.grade_badge)
        grade_layout.addSpacing(30)
        grade_layout.addLayout(text_info)
        grade_layout.addStretch()
        content_area.addWidget(self.grade_container)

        main_layout.addLayout(sidebar, 1)
        main_layout.addLayout(content_area, 3)

    def load_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open Data", "", "Data (*.csv *.xlsx)")
        if path:
            self.data_df = pd.read_csv(path) if path.endswith('.csv') else pd.read_excel(path)
            self.status_bar.setText(f"File: {os.path.basename(path)}")

    def load_json(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open Rules", "", "JSON (*.json)")
        if path:
            with open(path, 'r', encoding='utf-8') as f:
                self.rules = json.load(f)
            self.status_bar.setText(f"Rules: {os.path.basename(path)}")

    def run_eval(self):
        if self.data_df is None or self.rules is None: return
        
        checker = DQChecker(self.data_df, self.rules)
        mapping = {
            "Value": ("데이터값완전성", checker.check_value_completeness),
            "Record": ("데이터레코드완전성", checker.check_record_completeness),
            "Syntax": ("구문유효성", checker.check_syntax_validity),
            "Semantic": ("의미유효성", checker.check_semantic_validity),
            "Range": ("범위유효성", checker.check_range_validity),
            "Rel": ("관계유효성", checker.check_relationship_validity),
            "Ref": ("참조무결일관성", checker.check_referential_integrity)
        }

        self.result_table.setRowCount(0)
        scores = []
        for key, (name, func) in mapping.items():
            if self.checks[key].isChecked():
                row = self.result_table.rowCount()
                self.result_table.insertRow(row)
                score = func()
                scores.append(score)
                self.result_table.setItem(row, 0, QTableWidgetItem(name))
                self.result_table.setItem(row, 1, QTableWidgetItem(f"{score:.2f}%"))

        if scores:
            avg = sum(scores) / len(scores)
            if avg >= 99: g, color, desc = "A", "#00E676", "Excellent: High quality data detected."
            elif avg >= 97: g, color, desc = "B", "#00B0FF", "Good: Reliable data with minor issues."
            elif avg >= 95: g, color, desc = "C", "#FFD600", "Fair: Attention required."
            else: g, color, desc = "D", "#FF5252", "Poor: Needs cleansing."

            self.grade_badge.setText(g)
            # 테두리는 어둡게 고정하고, 글자색(color)만 바꿔서 깔끔하게 유지합니다.
            self.grade_badge.setStyleSheet(f"background-color: #1A1D2E; border-radius: 45px; color: {color}; font-size: 45px; font-weight: bold; border: 3px solid {color};")
            self.avg_score_label.setText(f"{avg:.2f}%")
            self.grade_desc.setText(desc)
            self.grade_desc.setStyleSheet(f"color: {color}; font-size: 14px;")
            # 컨테이너 테두리는 아주 은은하게만 강조합니다.
            self.grade_container.setStyleSheet(f"background-color: #161925; border: 1px solid #2D334A; border-radius: 15px;")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
