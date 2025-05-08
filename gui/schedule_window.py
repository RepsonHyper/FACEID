# gui/schedule_window.py

import psycopg2
from psycopg2.extras import DictCursor
from datetime import time
from pathlib import Path

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QLabel, QVBoxLayout, QHBoxLayout,
    QPushButton, QFrame, QComboBox, QTableWidget, QTableWidgetItem,
    QAbstractItemView, QHeaderView, QDialog, QDialogButtonBox,
    QFormLayout, QTimeEdit, QListWidget, QListWidgetItem
)
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QIcon

from core.db_utils import get_all_rooms  # lista pokoi z bazy

# pomocnicza tablica nazw dni
DAY_NAMES = ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"]

class ScheduleWindow(QMainWindow):
    finished = Signal()

    def __init__(self, config, engine, parent=None):
        super().__init__(parent)
        self.cfg    = config
        self.engine = engine
        self.dsn    = self.cfg["db_conn"]
        self.rooms  = get_all_rooms(self.dsn)

        # --- UI ---
        self.setWindowTitle("Sebastian Olszak – FACEID | Schedule Editor")
        self.setWindowIcon(QIcon(":/icon.png"))
        # wymuś maksymalizację zaraz po pokazaniu
        QTimer.singleShot(0, self.showMaximized)

        # wybór użytkownika
        self.user_combo = QComboBox(self)
        self._load_users()
        self.user_combo.currentIndexChanged.connect(self._load_schedule)

        # tabela harmonogramu
        self.table = QTableWidget(0, 5, self)
        self.table.setHorizontalHeaderLabels(["Room", "Day", "Start", "End", "Actions"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)

        # przycisk dodawania
        self.add_btn = QPushButton("Add entry", self)
        self.add_btn.clicked.connect(self._add_entry)

        # stopka
        self.footer = QLabel(
            "Sebastian Olszak – Projekt pracy inżynierskiej | FACEID | Schedule Editor",
            self
        )
        self.footer.setFixedHeight(30)
        self.footer.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.footer.setStyleSheet("padding-left:10px;")

        # główny layout
        central = QWidget(self)
        self.setCentralWidget(central)
        main_l = QVBoxLayout(central)
        main_l.setContentsMargins(0,0,0,0)
        main_l.setSpacing(5)
        main_l.addWidget(self.user_combo)
        main_l.addWidget(self.table)
        main_l.addWidget(self.add_btn, alignment=Qt.AlignCenter)
        main_l.addWidget(self.footer)

        # załaduj harmonogram pierwszego użytkownika
        self._load_schedule()

    def _connect(self):
        return psycopg2.connect(self.dsn, cursor_factory=DictCursor)

    def _load_users(self):
        """Wypełnij combobox listą osób z bazy."""
        self.user_combo.clear()
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute("SELECT id, name FROM persons ORDER BY name;")
            for row in cur.fetchall():
                # wyświetlamy "Imię (id)", przechowujemy person_id
                self.user_combo.addItem(f"{row['name']} ({row['id']})", row['id'])

    def _load_schedule(self):
        """Pobierz i pokaż wpisy z tabeli access_schedule dla zaznaczonego użytkownika."""
        person_id = self.user_combo.currentData()
        if person_id is None:
            return

        with self._connect() as conn, conn.cursor() as cur:
            cur.execute("""
                SELECT id, room_name, day_of_week, start_time, end_time
                FROM access_schedule
                WHERE person_id = %s
                ORDER BY room_name, day_of_week, start_time;
            """, (person_id,))
            rows = cur.fetchall()

        self.table.setRowCount(0)
        for entry in rows:
            row = self.table.rowCount()
            self.table.insertRow(row)
            # Room
            self.table.setItem(row, 0,
                QTableWidgetItem(entry["room_name"]))
            # Day name
            dow = entry["day_of_week"]
            day_str = DAY_NAMES[dow] if 0 <= dow < 7 else str(dow)
            self.table.setItem(row, 1,
                QTableWidgetItem(day_str))
            # Start
            self.table.setItem(row, 2,
                QTableWidgetItem(entry["start_time"].strftime("%H:%M")))
            # End
            self.table.setItem(row, 3,
                QTableWidgetItem(entry["end_time"].strftime("%H:%M")))
            # Actions: Edit / Delete
            edit = QPushButton("Edit")
            delete = QPushButton("Delete")
            edit.clicked.connect(lambda _, eid=entry["id"]: self._edit_entry(eid))
            delete.clicked.connect(lambda _, eid=entry["id"]: self._delete_entry(eid))
            buf = QWidget()
            h = QHBoxLayout(buf); h.setContentsMargins(0,0,0,0)
            h.addWidget(edit); h.addWidget(delete)
            buf.setLayout(h)
            self.table.setCellWidget(row, 4, buf)

    def _add_entry(self):
        """Pokaż dialog do dodania nowego wpisu (można wybrać wiele dni)."""
        dlg = EntryDialog(self.rooms, parent=self)
        if dlg.exec() != QDialog.Accepted:
            return
        person_id = self.user_combo.currentData()
        room, days, start, end = dlg.get_data()
        # wstaw kolejne wiersze, jeden na każdy zaznaczony dzień
        with self._connect() as conn, conn.cursor() as cur:
            for dow in days:
                cur.execute("""
                    INSERT INTO access_schedule(person_id, room_name, day_of_week, start_time, end_time)
                    VALUES (%s, %s, %s, %s, %s);
                """, (person_id, room, dow, start, end))
            conn.commit()
        self._load_schedule()

    def _edit_entry(self, entry_id):
        """Edytuj wybrany wpis (jednodniowy)."""
        # pobierz istniejące dane
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute("""
                SELECT room_name, day_of_week, start_time, end_time
                FROM access_schedule
                WHERE id = %s;
            """, (entry_id,))
            row = cur.fetchone()
        # przygotuj dane do dialogu: dni jako lista [day_of_week]
        data = (
            row["room_name"],
            [row["day_of_week"]],
            row["start_time"],
            row["end_time"]
        )
        dlg = EntryDialog(self.rooms, data, parent=self)
        if dlg.exec() != QDialog.Accepted:
            return
        room, days, start, end = dlg.get_data()
        # zaktualizuj (ponieważ było tylko jedno day_of_week w wierszu)
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute("""
                UPDATE access_schedule
                SET room_name = %s,
                    day_of_week = %s,
                    start_time  = %s,
                    end_time    = %s
                WHERE id = %s;
            """, (room, days[0], start, end, entry_id))
            conn.commit()
        self._load_schedule()

    def _delete_entry(self, entry_id):
        """Usuń wpis."""
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM access_schedule WHERE id = %s;", (entry_id,))
            conn.commit()
        self._load_schedule()

    def closeEvent(self, ev):
        self.finished.emit()
        super().closeEvent(ev)


class EntryDialog(QDialog):
    """Dialog do dodawania/edycji wpisu. Pozwala zaznaczyć dowolnie wiele dni."""
    def __init__(self, rooms, data=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add/Edit Schedule Entry")
        self.resize(400, 300)

        form = QFormLayout(self)

        # wybór pokoju
        self.room_cb = QComboBox(self)
        self.room_cb.addItems(rooms)
        form.addRow("Room:", self.room_cb)

        # multi-select dni tygodnia
        self.days_list = QListWidget(self)
        for idx, d in enumerate(DAY_NAMES):
            itm = QListWidgetItem(d)
            itm.setFlags(itm.flags() | Qt.ItemIsUserCheckable)
            itm.setCheckState(Qt.Unchecked)
            self.days_list.addItem(itm)
        form.addRow("Days:", self.days_list)

        # godziny
        self.start_te = QTimeEdit(self)
        self.start_te.setDisplayFormat("HH:mm")
        self.end_te = QTimeEdit(self)
        self.end_te.setDisplayFormat("HH:mm")
        form.addRow("Start time:", self.start_te)
        form.addRow("End time:", self.end_te)

        # OK / Cancel
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, parent=self)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        form.addRow(bb)

        # jeśli edycja, zaznacz istniejące wartości
        if data:
            room, days, st, et = data
            self.room_cb.setCurrentText(room)
            for i in range(self.days_list.count()):
                itm = self.days_list.item(i)
                if i in days:
                    itm.setCheckState(Qt.Checked)
            self.start_te.setTime(st)
            self.end_te.setTime(et)

    def get_data(self):
        """Zwraca (room_name, [day_of_week indices], start_time, end_time)."""
        room = self.room_cb.currentText()
        days = [
            i for i in range(self.days_list.count())
            if self.days_list.item(i).checkState() == Qt.Checked
        ]
        start = self.start_te.time().toPython()
        end = self.end_te.time().toPython()
        return room, days, start, end
