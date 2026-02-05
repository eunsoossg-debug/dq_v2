import sys
import json
import pandas as pd
import re
import os
from PyQt6.QtWidgets import (QApplication, QMainWindow, QPushButton, QVBoxLayout, 
                             QHBoxLayout, QWidget, QFileDialog, QLabel, QTableWidget, 
                             QTableWidgetItem, QCheckBox, QMessageBox, QHeaderView)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont

# --- 1. 품질 평가 엔진 클래스 ---
class DQChecker:
    def __init__(self, df, rules):
        self.df = df
        # rules.json의 'evaluation_rules' 섹션을 가져옴
        self.rules = rules.get("evaluation_rules", {})

    def check_value_completeness(self):
        total_cells = self.df.size
        null_count = self.df.isnull().sum().sum()
        return (1 - (null_count / total_cells)) * 100 if total_cells > 0 else 100

    def check_record_completeness(self):
        empty_rows = self.df.isnull().all(axis=1).sum()
        return (1 - (empty_rows / len(self.df))) * 100 if len(self.df) > 0 else 100

    # def check_syntax_validity(self):
    #     syntax_rules = self.rules.get("3_syntax_validity", {}).get("columns", {})
    #     if not syntax_rules: return 100.0
    #     invalid_count, total_checks = 0, 0
    #     for col, pattern in syntax_rules.items():
    #         if col in self.df.columns:
    #             invalid_count += self.df[col].astype(str).apply(lambda x: re.match(pattern, x) is None).sum()
    #             total_checks += len(self.df)
    #     return (1 - (invalid_count / total_checks)) * 100 if total_checks > 0 else 100
    
    def check_syntax_validity(self):
        syntax_rules = self.rules.get("3_syntax_validity", {}).get("columns", {})
        if not syntax_rules: 
            return 100.0
        
        invalid_count = 0
        total_checks = 0
        
        for col, pattern in syntax_rules.items():
            if col in self.df.columns:
                # 1. 결측치(NaN)를 완전히 제거한 실제 값만 추출
                series = self.df[col].dropna()
                
                # 2. 데이터가 있을 때만 검사 진행
                if not series.empty:
                    # 3. 중요: float(1.0) 형태를 정수형 문자열('1')로 변환하여 정규식 오판 방지
                    def clean_str(x):
                        s = str(x)
                        if s.endswith('.0'): return s[:-2]
                        return s

                    # 정규식 매칭 수행 (문자열 변환 후 패턴 대조)
                    # 매칭되지 않는(None인) 경우를 invalid로 카운트
                    matches = series.apply(clean_str).apply(lambda x: re.match(pattern, x) is not None)
                    invalid_count += (~matches).sum()
                    total_checks += len(series)
        
        # 4. 최종 점수 계산 (검사 대상이 없으면 100점, 있으면 비율 계산)
        if total_checks == 0:
            return 100.0
            
        score = (1 - (invalid_count / total_checks)) * 100
        return max(0, score) # 음수 방지
    
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
                # 숫자형 변환 시도 후 범위 체크
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
                # formula 예: "HIRE_DATE <= RETIRE_DATE"
                valid_count = len(self.df.query(rule["formula"], engine='python'))
                total_violations += (len(self.df) - valid_count)
            except Exception as e:
                print(f"Formula Error: {e}")
                continue
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

# --- 2. 메인 UI 클래스 ---
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Data Quality Pro - Studio")
        self.setMinimumSize(1000, 700)
        self.data_df = None
        self.rules = None
        
        self.init_ui()
        self.apply_style()

    def apply_style(self):
        self.setStyleSheet("""
            QMainWindow { background-color: #121212; }
            QWidget { color: #E0E0E0; font-family: 'Segoe UI', Arial; }
            QPushButton {
                background-color: #2D2D2D; border: 1px solid #3D3D3D;
                border-radius: 6px; padding: 12px; font-weight: bold;
            }
            QPushButton:hover { background-color: #3D3D3D; border-color: #0078D4; }
            QPushButton#run_btn {
                background-color: #0078D4; color: white; font-size: 15px; margin-top: 10px;
            }
            QPushButton#run_btn:hover { background-color: #1086E8; }
            QCheckBox { spacing: 8px; font-size: 13px; padding: 4px; }
            QTableWidget {
                background-color: #1E1E1E; border: 1px solid #333333;
                gridline-color: #2D2D2D; border-radius: 8px; font-size: 13px;
            }
            QHeaderView::section {
                background-color: #2D2D2D; color: #AAAAAA; 
                padding: 10px; border: none; font-weight: bold;
            }
            QLabel#status_bar { color: #888888; font-size: 12px; padding: 5px; }
        """)

    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)

        # --- Sidebar (Settings) ---
        sidebar = QVBoxLayout()
        sidebar.setContentsMargins(20, 20, 20, 20)
        
        logo = QLabel("DQ ANALYZER")
        logo.setStyleSheet("font-size: 22px; font-weight: 900; color: #0078D4; margin-bottom: 20px;")
        sidebar.addWidget(logo)

        self.btn_data = QPushButton("📁 Load Dataset")
        self.btn_json = QPushButton("⚙️ Load Rules (JSON)")
        self.btn_data.clicked.connect(self.load_file)
        self.btn_json.clicked.connect(self.load_json)
        sidebar.addWidget(self.btn_data)
        sidebar.addWidget(self.btn_json)

        sidebar.addSpacing(30)
        sidebar.addWidget(QLabel("METRIC SELECTION"))
        
        self.checks = {
            "Value": QCheckBox("Value Completeness"),
            "Record": QCheckBox("Record Integrity"),
            "Syntax": QCheckBox("Syntax Validity"),
            "Semantic": QCheckBox("Semantic Validity"),
            "Range": QCheckBox("Range Validity"),
            "Rel": QCheckBox("Relational Logic"),
            "Ref": QCheckBox("Referential Integrity")
        }
        for cb in self.checks.values():
            cb.setChecked(True)
            sidebar.addWidget(cb)

        sidebar.addStretch()
        
        self.btn_run = QPushButton("START ANALYSIS")
        self.btn_run.setObjectName("run_btn")
        self.btn_run.clicked.connect(self.run_eval)
        sidebar.addWidget(self.btn_run)
        
        self.status_bar = QLabel("Waiting for files...")
        self.status_bar.setObjectName("status_bar")
        sidebar.addWidget(self.status_bar)

        # --- Content (Results) ---
        content = QVBoxLayout()
        self.result_table = QTableWidget(0, 2)
        self.result_table.setHorizontalHeaderLabels(["Quality Dimension", "Score (%)"])
        self.result_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        content.addWidget(self.result_table)

        main_layout.addLayout(sidebar, 1)
        main_layout.addLayout(content, 3)

    def load_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open Data", "", "Data (*.csv *.xlsx)")
        if path:
            try:
                self.data_df = pd.read_csv(path) if path.endswith('.csv') else pd.read_excel(path)
                self.status_bar.setText(f"Data Loaded: {os.path.basename(path)}")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to load data: {e}")

    def load_json(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open Rules", "", "JSON (*.json)")
        if path:
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    self.rules = json.load(f)
                self.status_bar.setText(f"Rules Loaded: {os.path.basename(path)}")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Invalid JSON: {e}")

    def run_eval(self):
        if self.data_df is None or self.rules is None:
            QMessageBox.warning(self, "Warning", "Please load both Data and JSON files first.")
            return
        
        self.status_bar.setText("Analyzing...")
        QApplication.processEvents() # UI 업데이트 강제 실행
        
        checker = DQChecker(self.data_df, self.rules)
        mapping = {
            "Value": ("Data Value Completeness", checker.check_value_completeness),
            "Record": ("Record Level Completeness", checker.check_record_completeness),
            "Syntax": ("Syntactic Validity (Regex)", checker.check_syntax_validity),
            "Semantic": ("Semantic Domain Validity", checker.check_semantic_validity),
            "Range": ("Numeric Range Validity", checker.check_range_validity),
            "Rel": ("Relational Consistency", checker.check_relationship_validity),
            "Ref": ("Referential Integrity", checker.check_referential_integrity)
        }

        self.result_table.setRowCount(0)
        for i, (key, (name, func)) in enumerate(mapping.items()):
            if self.checks[key].isChecked():
                row_idx = self.result_table.rowCount()
                self.result_table.insertRow(row_idx)
                
                score = func()
                name_item = QTableWidgetItem(name)
                score_item = QTableWidgetItem(f"{score:.2f} %")
                
                # 점수에 따른 색상 강조 (80점 미만 오렌지, 60점 미만 레드)
                if score < 60: score_item.setForeground(QColor("#FF5252"))
                elif score < 90: score_item.setForeground(QColor("#FFAB40"))
                else: score_item.setForeground(QColor("#69F0AE"))
                
                score_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.result_table.setItem(row_idx, 0, name_item)
                self.result_table.setItem(row_idx, 1, score_item)

        self.status_bar.setText("Analysis Finished Successfully.")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
