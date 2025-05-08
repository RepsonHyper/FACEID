from PySide6.QtWidgets import (
    QMainWindow, QWidget, QLabel, QVBoxLayout, QHBoxLayout,
    QFrame, QPushButton, QComboBox, QInputDialog, QMessageBox, QLineEdit
)
from PySide6.QtCore import Qt, QTimer, QObject, Signal, Slot, QThread
from PySide6.QtGui import QImage, QPixmap, QIcon

import numpy as np
import cv2
import time
from pathlib import Path
from datetime import datetime

from core.camera import CameraHandler
from core.db_utils import update_last_attendance_time, log_access, get_all_rooms
from core.access_control import check_access
from gui.register_face import RegisterFaceWindow
from gui.schedule_window import ScheduleWindow


class RecognitionWorker(QObject):
    recognized = Signal(int, str, float)
    def __init__(self, engine):
        super().__init__()
        self.engine = engine

    @Slot(object)
    def process_frame(self, frame):
        state, cid, dist = self.engine.recognize(frame)
        self.recognized.emit(state, cid or "", dist or 0.0)


class MainWindow(QMainWindow):
    frame_ready = Signal(object)

    def __init__(self, config, engine):
        super().__init__()
        self.setWindowTitle("Sebastian Olszak – FACEID")
        self.setWindowIcon(QIcon(":/icon.png"))

        self.cfg         = config
        self.engine      = engine
        self.id_to_name  = engine.id_to_name
        self.rooms       = get_all_rooms(self.cfg["db_conn"])
        self.current_room= None

        # Grafiki
        sample = Path(self.cfg['paths']['sample'])
        self.unknown_pix = QPixmap(str(sample / "unknown.jpg"))
        self.none_pix    = QPixmap(str(sample / "none.jpg"))

        # LEWY PANEL
        self.camera      = CameraHandler(width=1280, height=960)
        self.video_label = QLabel(self)
        self.video_label.setFixedSize(1280, 960)
        self.video_label.setAlignment(Qt.AlignCenter)

        self.open_button = QPushButton("Open Door", self)
        self.open_button.setStyleSheet("""
            QPushButton { background:#007ACC; color:white;
                         border-radius:5px; padding:8px 16px; font-size:14px; }
            QPushButton:disabled { background:#555; }
            QPushButton:hover:!disabled { background:#005F9E; }
        """)
        self.open_button.clicked.connect(self.start_auth)

        self.access_label = QLabel("", self)
        self.access_label.setFixedSize(200, 50)
        self.access_label.setAlignment(Qt.AlignCenter)
        self.access_label.setStyleSheet("""
            background:#333; color:white;
            border-radius:5px; padding:12px; font-size:18px;
        """)

        # PRAWY PANEL
        self.photo_label = QLabel(self)
        self.photo_label.setFixedSize(525, 700)
        self.photo_label.setAlignment(Qt.AlignCenter)

        self.value_label = QLabel("", self)
        self.value_label.setAlignment(Qt.AlignCenter)
        self.id_value    = QLabel("", self)
        self.id_value.setAlignment(Qt.AlignCenter)

        self.register_button = QPushButton("Register new person", self)
        self.register_button.setStyleSheet("""
            QPushButton { background:#007ACC; color:white;
                         border-radius:5px; padding:8px 16px; font-size:14px; }
            QPushButton:hover { background:#005F9E; }
        """)
        self.register_button.clicked.connect(self.try_register)

        self.edit_schedule_button = QPushButton("Edit Schedule", self)
        self.edit_schedule_button.setStyleSheet("""
            QPushButton { background:#007ACC; color:white;
                         border-radius:5px; padding:8px 16px; font-size:14px; }
            QPushButton:hover { background:#005F9E; }
        """)
        self.edit_schedule_button.clicked.connect(self.try_edit_schedule)

        # ComboBox z pokojami
        self.room_selector = QComboBox(self)
        self.room_selector.addItems(self.rooms)
        self.room_selector.currentTextChanged.connect(
            lambda r: setattr(self, "current_room", r)
        )
        self.current_room = self.room_selector.currentText()

        # Stopka
        self.footer_label = QLabel("Sebastian Olszak – FACEID", self)
        self.footer_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.footer_label.setStyleSheet("padding-left:10px;")

        # Stan autoryzacji
        self.authenticating = False
        self.auth_start     = 0.0
        self.auth_timeout   = 3.0
        self.auth_result    = None

        self._build_ui()

        # Thread do rozpoznawania
        self._recog_thread = QThread(self)
        self._recog_worker = RecognitionWorker(self.engine)
        self._recog_worker.moveToThread(self._recog_thread)
        self.frame_ready.connect(self._recog_worker.process_frame, Qt.QueuedConnection)
        self._recog_worker.recognized.connect(self._on_recognized)
        self._recog_thread.start()

        # Timer kamery
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._on_frame)
        self.camera.open()
        self.timer.start(30)


    def _build_ui(self):
        w = QWidget(self)
        self.setCentralWidget(w)
        main = QVBoxLayout(w)
        main.setContentsMargins(0,0,0,0)
        main.setSpacing(0)

        # ComboBox nad kamerą
        main.addWidget(self.room_selector)

        content = QHBoxLayout()
        # LEWY panel
        left = QWidget(self)
        ll = QVBoxLayout(left)
        ll.setContentsMargins(5,5,5,5)
        ll.setAlignment(Qt.AlignTop | Qt.AlignHCenter)
        ll.addWidget(self.video_label)
        ll.addWidget(self.open_button, alignment=Qt.AlignHCenter)
        ll.addWidget(self.access_label, alignment=Qt.AlignHCenter)
        ll.addStretch()
        content.addWidget(left, 3)

        # PRAWY panel
        right = QFrame(self)
        right.setStyleSheet("background:#2E2E2E; border-radius:10px;")
        rr = QVBoxLayout(right)
        rr.setContentsMargins(20,20,20,20)
        rr.setSpacing(15)

        # 1) Zdjęcie na górze
        rr.addWidget(self.photo_label, alignment=Qt.AlignHCenter)

        # 2) Bloczek Name/ID
        self.info_box = QFrame(right)
        self.info_box.setStyleSheet("background:#404040; border-radius:5px;")
        info_l = QVBoxLayout(self.info_box)
        info_l.setContentsMargins(0,0,0,0)
        info_l.setSpacing(10)

        for title, widget in (("Name", self.value_label),
                              ("ID",   self.id_value)):
            cap = QFrame(self.info_box)
            cap.setStyleSheet("background:#505050; border-radius:5px;")
            cap_l = QVBoxLayout(cap); cap_l.setContentsMargins(8,4,8,4)
            lbl = QLabel(title, cap); lbl.setAlignment(Qt.AlignCenter)
            lbl.setStyleSheet("color:white; font-size:14px;")
            cap_l.addWidget(lbl)
            info_l.addWidget(cap)

            val = QFrame(self.info_box)
            val.setStyleSheet("background:#606060; border-radius:5px;")
            val_l = QVBoxLayout(val); val_l.setContentsMargins(8,4,8,4)
            val_l.addWidget(widget)
            info_l.addWidget(val)

        info_l.addStretch()
        rr.addWidget(self.info_box)

        # 3) Przyciski na dole
        rr.addStretch()  # wypchnij przyciski na dół
        btns = QHBoxLayout()
        btns.addWidget(self.register_button)
        btns.addWidget(self.edit_schedule_button)
        rr.addLayout(btns)

        content.addWidget(right, 2)
        main.addLayout(content, 1)
        main.addWidget(self.footer_label, 0)

        # Stan początkowy: idle
        self._enter_idle_ui()


    def _enter_idle_ui(self):
        self.access_label.hide()
        self.info_box.hide()
        self.photo_label.hide()
        self.register_button.show()
        self.register_button.setEnabled(True)
        self.edit_schedule_button.show()
        self.footer_label.setText("Sebastian Olszak – FACEID")
        self.open_button.setEnabled(True)
        self.value_label.clear()
        self.id_value.clear()


    def start_auth(self):
        self.authenticating = True
        self.auth_start     = time.time()
        self.auth_result    = None

        self.access_label.show()
        self.access_label.setText("Scanning…")
        self.access_label.setStyleSheet(
            "background:#FFA000; color:white; padding:12px; border-radius:5px;"
        )
        self.open_button.setEnabled(False)
        self.register_button.hide()
        self.edit_schedule_button.hide()


    def finish_auth(self):
        cid, dist, granted, reason = self.auth_result or ("",0.0,False,"timeout")

        result = 'granted' if granted else (
            'unknown' if reason=="nieznana twarz" else 'denied'
        )
        log_access(self.cfg["db_conn"],
                   cid if granted else None,
                   self.current_room,
                   result,
                   reason)
        if granted:
            update_last_attendance_time(cid)

        # Wybór obrazka
        if reason == "nieznana twarz":
            pic = self.unknown_pix
        else:
            p = Path(self.cfg["paths"]["sample"])/f"{cid}.jpg"
            pic = QPixmap(str(p)) if p.exists() else self.none_pix

        self.photo_label.setPixmap(pic.scaled(
            self.photo_label.size(),
            Qt.KeepAspectRatio, Qt.SmoothTransformation
        ))

        self.photo_label.show()
        self.info_box.show()

        # Access label
        bg, txt = ("#4CAF50","Access Granted") if granted else ("#F44336",f"Access Denied\n{reason}")
        self.access_label.setText(txt)
        self.access_label.setStyleSheet(
            f"background:{bg}; color:white; padding:12px; border-radius:5px;"
        )

        # Wypełnienie Name/ID
        if reason != "nieznana twarz":
            name = self.id_to_name.get(cid,"[Unknown]")
            self.value_label.setText(name)
            self.id_value.setText(cid)
        else:
            self.value_label.setText("[Unknown Face]")
            self.id_value.setText("[Unknown Face]")

        # stopka z dystansem
        dist_txt = f"{dist:.2f}"
        self.footer_label.setText(f"© 2025 FACEID | Best: {cid or '[Unknown]'} | Distance: {dist_txt}")

        # Po 10 s wrócimy do idle
        QTimer.singleShot(10_000, self._enter_idle_ui)
        self.authenticating = False
        self.open_button.setEnabled(True)


    def _on_frame(self):
        ret, frame = self.camera.read()
        if not ret:
            return

        disp = frame.copy()
        if self.authenticating:
            faces = self.engine.face_analyzer.get(frame)
            if faces:
                x1,y1,x2,y2 = faces[0].bbox.astype(int)
                cv2.rectangle(disp,(x1,y1),(x2,y2),(0,255,0),2)
            self.frame_ready.emit(frame.copy())

            if time.time() - self.auth_start >= self.auth_timeout:
                self.auth_result = ("",0.0,False,"timeout")
                self.finish_auth()

        # render kamery
        rgb = np.ascontiguousarray(disp[:,:,::-1])
        h,w,_ = rgb.shape; bpl = rgb.strides[0]
        img = QImage(rgb.data,w,h,bpl,QImage.Format_RGB888)
        pix = QPixmap.fromImage(img).scaled(
            self.video_label.size(),
            Qt.KeepAspectRatio,Qt.SmoothTransformation
        )
        self.video_label.setPixmap(pix)


    @Slot(int, str, float)
    def _on_recognized(self, state, cid, dist):
        if not self.authenticating:
            return

        if state == 2:
            self.auth_result = (cid, dist, False, "nieznana twarz")
            self.finish_auth()
        elif state == 1:
            granted, reason = check_access(
                self.cfg["db_conn"], cid, self.current_room, datetime.now()
            )
            self.auth_result = (cid, dist, granted, reason)
            self.finish_auth()


    def try_register(self):
        pwd, ok = QInputDialog.getText(
            self, "Admin password", "Enter password:", QLineEdit.Password
        )
        if not ok or pwd != "admin":
            QMessageBox.warning(self, "Denied", "Wrong password")
            return

        self.setEnabled(False)
        self.timer.stop()
        self.camera.close()
        self.reg_win = RegisterFaceWindow(self.cfg, self.engine, parent=self)
        self.reg_win.finished.connect(self._on_register_closed)
        self.reg_win.show()


    def try_edit_schedule(self):
        pwd, ok = QInputDialog.getText(
            self, "Admin password", "Enter password:", QLineEdit.Password
        )
        if not ok or pwd != "admin":
            QMessageBox.warning(self, "Denied", "Wrong password")
            return

        self.setEnabled(False)
        self.timer.stop()
        self.camera.close()
        self.sch_win = ScheduleWindow(self.cfg, self.engine, parent=self)
        self.sch_win.finished.connect(self._on_schedule_closed)
        self.sch_win.show()


    def _on_register_closed(self, *_):
        self.setEnabled(True)
        self.camera.open()
        self.timer.start(30)


    def _on_schedule_closed(self, *_):
        self.setEnabled(True)
        self.camera.open()
        self.timer.start(30)
