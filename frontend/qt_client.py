# frontend/qt_client.py
import sys
import requests
from PyQt5.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QLineEdit, QTableWidget, QTableWidgetItem, QMessageBox, QComboBox)
from PyQt5.QtCore import Qt

API_BASE = "http://127.0.0.1:5000/api"

class OperatorConsole(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Operator Console - Transaction Editor")
        self.resize(900, 500)
        layout = QVBoxLayout()

        # Search row
        row = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search by txn_id / payer / payee")
        row.addWidget(self.search_input)
        btn_search = QPushButton("Search")
        btn_search.clicked.connect(self.search)
        row.addWidget(btn_search)
        btn_refresh = QPushButton("Refresh")
        btn_refresh.clicked.connect(self.load_recent)
        row.addWidget(btn_refresh)
        layout.addLayout(row)

        # Table
        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(["txn_id","payer","payee","amount","channel","status","ts"])
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.cellClicked.connect(self.on_cell_clicked)
        layout.addWidget(self.table)

        # Edit form
        form = QHBoxLayout()
        self.selected_label = QLabel("Selected: None")
        form.addWidget(self.selected_label)

        form.addWidget(QLabel("Payee:"))
        self.payee_input = QLineEdit()
        form.addWidget(self.payee_input)

        form.addWidget(QLabel("Amount:"))
        self.amount_input = QLineEdit()
        form.addWidget(self.amount_input)

        form.addWidget(QLabel("Channel:"))
        self.channel_input = QComboBox()
        self.channel_input.addItems(["UPI","NEFT","RTGS","IMPS"])
        form.addWidget(self.channel_input)

        form.addWidget(QLabel("Status:"))
        self.status_input = QComboBox()
        self.status_input.addItems(["Pending","Success","Failed"])
        form.addWidget(self.status_input)

        self.operator_input = QLineEdit()
        self.operator_input.setPlaceholderText("Operator name")
        self.operator_input.setFixedWidth(150)
        form.addWidget(self.operator_input)

        btn_save = QPushButton("Save Changes")
        btn_save.clicked.connect(self.save_changes)
        form.addWidget(btn_save)

        layout.addLayout(form)
        self.setLayout(layout)

        self.current_txn_id = None
        self.load_recent()

    def load_recent(self):
        try:
            r = requests.get(f"{API_BASE}/recent", timeout=5)
            r.raise_for_status()
            data = r.json()
            self.populate_table(data)
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Could not fetch recent transactions:\n{e}")

    def populate_table(self, data):
        self.table.setRowCount(0)
        for doc in data:
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.table.setItem(row, 0, QTableWidgetItem(doc.get("txn_id","")))
            self.table.setItem(row, 1, QTableWidgetItem(doc.get("payer","")))
            self.table.setItem(row, 2, QTableWidgetItem(doc.get("payee","")))
            self.table.setItem(row, 3, QTableWidgetItem(str(doc.get("amount",""))))
            self.table.setItem(row, 4, QTableWidgetItem(doc.get("channel","")))
            self.table.setItem(row, 5, QTableWidgetItem(doc.get("status","")))
            ts = doc.get("timestamp")
            ts_str = ts if isinstance(ts,str) else (str(ts) if ts else "")
            self.table.setItem(row, 6, QTableWidgetItem(ts_str))

    def search(self):
        q = self.search_input.text().strip()
        if not q:
            self.load_recent()
            return
        params = {"limit": 100}
        # naive decide if it's txn_id-like
        if q.upper().startswith("TXN"):
            params["txn_id"] = q
        else:
            # search payer or payee
            params["payer"] = q
            params["payee"] = q
        try:
            r = requests.get(f"{API_BASE}/transactions", params=params, timeout=5)
            r.raise_for_status()
            data = r.json()
            self.populate_table(data)
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Search failed:\n{e}")

    def on_cell_clicked(self, row, col):
        txn_id = self.table.item(row, 0).text()
        try:
            r = requests.get(f"{API_BASE}/transactions/{txn_id}", timeout=5)
            r.raise_for_status()
            doc = r.json()
            self.current_txn_id = txn_id
            self.selected_label.setText(f"Selected: {txn_id}")
            self.payee_input.setText(doc.get("payee",""))
            self.amount_input.setText(str(doc.get("amount","")))
            ch = doc.get("channel","UPI")
            status = doc.get("status","Pending")
            idx_ch = self.channel_input.findText(ch)
            if idx_ch >= 0: self.channel_input.setCurrentIndex(idx_ch)
            idx_st = self.status_input.findText(status)
            if idx_st >= 0: self.status_input.setCurrentIndex(idx_st)
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Could not load txn:\n{e}")

    def save_changes(self):
        if not self.current_txn_id:
            QMessageBox.information(self, "Info", "Select a transaction first.")
            return
        payload = {
            "payee": self.payee_input.text().strip(),
            "amount": float(self.amount_input.text().strip()) if self.amount_input.text().strip() else None,
            "channel": self.channel_input.currentText(),
            "status": self.status_input.currentText(),
            "operator": self.operator_input.text().strip() or "operator_unknown"
        }
        # remove None values
        payload = {k:v for k,v in payload.items() if v is not None}
        try:
            r = requests.put(f"{API_BASE}/transactions/{self.current_txn_id}", json=payload, timeout=5)
            r.raise_for_status()
            updated = r.json()
            QMessageBox.information(self, "Saved", f"Transaction updated: {updated['txn_id']}")
            self.load_recent()
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Could not save changes:\n{e}")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = OperatorConsole()
    win.show()
    sys.exit(app.exec_())
