import sys
import json
import pandas as pd
import re
import os
from PyQt6.QtWidgets import (QApplication, QMainWindow, QPushButton, QVBoxLayout, 
                             QHBoxLayout, QWidget, QFileDialog, QLabel, QTableWidget, 
                             QTableWidgetItem, QCheckBox, QMessageBox, QTextEdit)
from PyQt6.QtCore import Qt

class DQChecker:
    def __init__(self, df, rules):
        self.df = df
        self.rules = rules.get("evaluation_rules", {})

    def check_value_completeness(self):
        # 1. 데이터값완전성: 전체 셀 중 Null이 아닌 비율
        total_cells = self.df.size
        null_count = self.df.isnull().sum().sum()
        return (1 - (null_count / total_cells)) * 100 if total_cells > 0 else 100

    def check_record_completeness(self):
        # 2. 데이터레코드완전성: 모든 값이 Null인 행 제외
        empty_rows = self.df.isnull().all(axis=1).sum()
        return (1 - (empty_rows / len(self.df))) * 100 if len(self.df) > 0 else 100

    def check_syntax_validity(self):
        # 3. 구문유효성: Regex 패턴 매칭
        syntax_rules = self.rules.get("3_syntax_validity", {}).get("columns", {})
        if not syntax_rules: return 100.0
        invalid_count, total_checks = 0, 0
        for col, pattern in syntax_rules.items():
            if col in self.df.columns:
                invalid_count += self.df[col].astype(str).apply(lambda x: re.match(pattern, x) is None).sum()
                total_checks += len(self.df)
        return (1 - (invalid_count / total_checks)) * 100 if total_checks > 0 else 100

    def check_semantic_validity(self):
        # 4. 의미유효성: 허용 리스트(List) 포함 여부
        semantic_rules = self.rules.get("4_semantic_validity", {}).get("columns", {})
        if not semantic_rules: return 100.0
        invalid_count, total_checks = 0, 0
        for col, valid_list in semantic_rules.items():
            if col in self.df.columns:
                invalid_count += (~self.df[col].isin(valid_list)).sum()
                total_checks += len(self.df)
        return (1 - (invalid_count / total_checks)) * 100 if total_checks > 0 else 100

    def check_range_validity(self):
        # 5. 범위유효성: Min/Max 범위 준수
        range_rules = self.rules.get("5_range_validity", {}).get("columns", {})
        if not range_rules: return 100.0
        invalid_count, total_checks = 0, 0
        for col, limits in range_rules.items():
            if col in self.df.columns:
                invalid_count += ((self.df[col] < limits['min']) | (self.df[col] > limits['max'])).sum()
                total_checks += len(self.df)
        return (1 - (invalid_count / total_checks)) * 100 if total_checks > 0 else 100

    def check_relationship_validity(self):
        # 6. 관계유효성: 컬럼 간 논리 수식(Formula)
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
        # 7. 참조무결성: 외부 파일 대조
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
        self.setWindowTitle("Data Quality Pro v1.0")
        self.data_df = None
        self.rules = None
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()
        h_layout = QHBoxLayout()
        
        self.btn_data = QPushButton("1. 데이터 파일 로드")
        self.btn_json = QPushButton("2. 규칙 JSON 로드")
        self.btn_data.clicked.connect(self.load_file)
        self.btn_json.clicked.connect(self.load_json)
        h_layout.addWidget(self.btn_data)
        h_layout.addWidget(self.btn_json)
        layout.addLayout(h_layout)

        self.checks = {
            "Value": QCheckBox("데이터값완전성"), "Record": QCheckBox("데이터레코드완전성"),
            "Syntax": QCheckBox("구문유효성"), "Semantic": QCheckBox("의미유효성"),
            "Range": QCheckBox("범위유효성"), "Rel": QCheckBox("관계유효성"), "Ref": QCheckBox("참조무결성")
        }
        for cb in self.checks.values():
            cb.setChecked(True)
            layout.addWidget(cb)

        self.btn_run = QPushButton("품질 평가 시작")
        self.btn_run.setStyleSheet("background-color: #2c3e50; color: white; height: 40px;")
        self.btn_run.clicked.connect(self.run_eval)
        layout.addWidget(self.btn_run)

        self.result_table = QTableWidget(7, 2)
        self.result_table.setHorizontalHeaderLabels(["평가 항목", "점수"])
        layout.addWidget(self.result_table)

        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)

    def load_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open Data", "", "Data (*.csv *.xlsx)")
        if path: self.data_df = pd.read_csv(path) if path.endswith('.csv') else pd.read_excel(path)

    def load_json(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open Rules", "", "JSON (*.json)")
        if path:
            with open(path, 'r', encoding='utf-8') as f: self.rules = json.load(f)

    def run_eval(self):
        if self.data_df is None or self.rules is None:
            QMessageBox.warning(self, "경고", "파일을 모두 로드해주세요.")
            return
        
        checker = DQChecker(self.data_df, self.rules)
        mapping = {
            "Value": ("데이터값완전성", checker.check_value_completeness),
            "Record": ("데이터레코드완전성", checker.check_record_completeness),
            "Syntax": ("구문유효성", checker.check_syntax_validity),
            "Semantic": ("의미유효성", checker.check_semantic_validity),
            "Range": ("범위유효성", checker.check_range_validity),
            "Rel": ("관계유효성", checker.check_relationship_validity),
            "Ref": ("참조무결성", checker.check_referential_integrity)
        }

        row = 0
        for key, (name, func) in mapping.items():
            if self.checks[key].isChecked():
                score = func()
                self.result_table.setItem(row, 0, QTableWidgetItem(name))
                self.result_table.setItem(row, 1, QTableWidgetItem(f"{score:.2f}"))
                row += 1

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
