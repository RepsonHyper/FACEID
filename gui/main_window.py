from PySide6.QtWidgets import (
    QMainWindow, QWidget, QLabel, QVBoxLayout, QHBoxLayout,
    QFrame, QPushButton
)
from PySide6.QtCore import Qt, QTimer, QObject, Signal, Slot, QThread
from PySide6.QtGui import QImage, QPixmap, QIcon

import numpy as np
import cv2
import time
from pathlib import Path

from core.camera import CameraHandler
from core.db_utils import update_last_attendance_time
from gui.register_face import RegisterFaceWindow

class RecognitionWorker(QObject):
    recognized = Signal(int, str, float, float)  # state, id, dist, ts

    def __init__(self, engine, cooldown: int):
        super().__init__()
        self.engine = engine
        self.cooldown = cooldown
        self.current_id = None
        self.last_absence = None
        self.last_update_ts = None

    @Slot(object)
    def process_frame(self, frame):
        state, cid, dist = self.engine.recognize(frame)
        now = time.time()
        do_update = False
        if state == 1:
            if cid != self.current_id and (
               self.last_absence is None or now - self.last_absence >= self.cooldown):
                do_update = True
                self.current_id = cid
                self.last_absence = None
        elif state == 0 and self.current_id is not None:
            self.last_absence = now
            self.current_id = None

        if do_update:
            ts = update_last_attendance_time(cid)
            self.last_update_ts = time.mktime(ts.timetuple())
        self.recognized.emit(state, cid or "", dist or 0.0, self.last_update_ts or 0.0)

class MainWindow(QMainWindow):
    frame_ready = Signal(object)

    def __init__(self, config, engine):
        super().__init__()
        self.setWindowTitle("Sebastian Olszak - FACEID")
        self.setWindowIcon(QIcon(":/icon.png"))
        self.cfg = config
        self.engine = engine
        self.id_to_name = engine.id_to_name
        self.update_cooldown = 30

        sample_dir = Path(self.cfg['paths']['sample'])
        self.unknown_pix = QPixmap(str(sample_dir / 'unknown.jpg'))
        self.none_pix = QPixmap(str(sample_dir / 'none.jpg'))

        self.camera = CameraHandler(width=1280, height=960)
        self.video_label = QLabel(self)

        self.photo_label = QLabel(self)
        self.photo_label.setFixedSize(525, 700)
        self.photo_label.setStyleSheet('background: black;')
        self.photo_label.setAlignment(Qt.AlignCenter)

        self.caption_label = QLabel(self)
        self.value_label = QLabel(self)
        self.value_label.setAlignment(Qt.AlignCenter)
        self.id_caption = QLabel(self)
        self.id_value = QLabel(self)
        self.id_value.setAlignment(Qt.AlignCenter)

        self.register_button = QPushButton("Register new person", self)
        self.register_button.setEnabled(False)
        self.register_button.setStyleSheet("""
                    QPushButton {
                      background-color: #007ACC;
                      color: white;
                      border-radius: 5px;
                      padding: 8px 16px;
                      font-size: 14px;
                    }
                    QPushButton:disabled {
                      background-color: #555555;
                    }
                    QPushButton:hover:!disabled {
                      background-color: #005F9E;
                    }
                """)
        self.register_button.clicked.connect(self.open_register_window)

        # stopka
        self.footer_label = QLabel(self)

        self._build_ui()

        # worker thread
        self._recog_thread = QThread(self)
        self._recog_worker = RecognitionWorker(self.engine, self.update_cooldown)
        self._recog_worker.moveToThread(self._recog_thread)
        self.frame_ready.connect(self._recog_worker.process_frame, Qt.QueuedConnection)
        self._recog_worker.recognized.connect(self._on_recognized)
        self._recog_thread.start()

        # timer
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._on_frame)
        self.camera.open()
        self.timer.start(30)

    def _build_ui(self):
        central = QWidget(self)
        self.setCentralWidget(central)
        main = QVBoxLayout(central)
        main.setContentsMargins(0,0,0,0)
        main.setSpacing(0)

        content = QHBoxLayout()
        # lewy panel
        left = QWidget(self)
        left_l = QVBoxLayout(left)
        left_l.setContentsMargins(5,5,5,5)
        left_l.setAlignment(Qt.AlignCenter)
        self.video_label.setFixedSize(1280, 960)
        self.video_label.setAlignment(Qt.AlignCenter)
        left_l.addWidget(self.video_label)

        # prawy panel
        right = QFrame(self)
        right.setFrameShape(QFrame.StyledPanel)
        right.setStyleSheet('background: #2E2E2E; border-radius: 10px;')
        right_l = QVBoxLayout(right)
        right_l.setContentsMargins(20,20,20,20)
        right_l.setSpacing(15)

        right_l.addWidget(self.photo_label, alignment=Qt.AlignCenter)

        info_box = QFrame(right)
        info_box.setFrameShape(QFrame.StyledPanel)
        info_box.setStyleSheet('background: #404040; border-radius: 5px;')
        info_layout = QVBoxLayout(info_box)
        info_layout.setContentsMargins(0,0,0,0)
        info_layout.setSpacing(10)

        cap1 = QFrame(info_box)
        cap1.setFrameShape(QFrame.StyledPanel)
        cap1.setStyleSheet('background: #505050; border-radius: 5px;')
        cap1_l = QVBoxLayout(cap1)
        cap1_l.setContentsMargins(8,4,8,4)
        lbl1 = QLabel('Name', cap1)
        lbl1.setAlignment(Qt.AlignCenter)
        lbl1.setStyleSheet('color: white; font-size: 14px;')
        cap1_l.addWidget(lbl1)
        info_layout.addWidget(cap1)

        val1 = QFrame(info_box)
        val1.setFrameShape(QFrame.StyledPanel)
        val1.setStyleSheet('background: #606060; border-radius: 5px;')
        val1_l = QVBoxLayout(val1)
        val1_l.setContentsMargins(8,4,8,4)

        val1_l.addWidget(self.value_label)
        info_layout.addWidget(val1)

        cap2 = QFrame(info_box)
        cap2.setFrameShape(QFrame.StyledPanel)
        cap2.setStyleSheet('background: #505050; border-radius: 5px;')
        cap2_l = QVBoxLayout(cap2)
        cap2_l.setContentsMargins(8,4,8,4)
        lbl2 = QLabel('ID', cap2)
        lbl2.setAlignment(Qt.AlignCenter)
        lbl2.setStyleSheet('color: white; font-size: 14px;')
        cap2_l.addWidget(lbl2)
        info_layout.addWidget(cap2)

        val2 = QFrame(info_box)
        val2.setFrameShape(QFrame.StyledPanel)
        val2.setStyleSheet('background: #606060; border-radius: 5px;')
        val2_l = QVBoxLayout(val2)
        val2_l.setContentsMargins(8,4,8,4)

        val2_l.addWidget(self.id_value)
        info_layout.addWidget(val2)
        info_layout.addStretch()
        right_l.addWidget(info_box)
        right_l.addWidget(self.register_button, alignment=Qt.AlignCenter)


        content.addWidget(left,3)
        content.addWidget(right,2)




        self.footer_label.setFixedHeight(30)
        self.footer_label.setAlignment(Qt.AlignLeft|Qt.AlignVCenter)
        self.footer_label.setStyleSheet('font-size: 14px; padding-left: 10px;')
        self.footer_label.setText(
            'Sebastian Olszak - Projekt pracy inżynierskiej | FACEID | Face_Detected: False | Best: N/A | Distance: N/A'
        )

        main.addLayout(content)
        main.addWidget(self.footer_label)

    def _on_frame(self):
        ret, frame = self.camera.read()
        if not ret: return
        faces = self.engine.face_analyzer.get(frame)
        disp = frame.copy()
        if faces:
            x1,y1,x2,y2 = faces[0].bbox.astype(int)
            cv2.rectangle(disp,(x1,y1),(x2,y2),(0,255,0),2)
        rgb = disp[:,:,::-1]
        rgb = np.ascontiguousarray(rgb)
        h,w,_ = rgb.shape
        bpl = rgb.strides[0]
        img = QImage(rgb.data,w,h,bpl,QImage.Format_RGB888)
        pix = QPixmap.fromImage(img).scaled(
            self.video_label.size(),Qt.KeepAspectRatio,Qt.SmoothTransformation
        )
        self.video_label.setPixmap(pix)

        self.frame_ready.emit(frame.copy())

    @Slot(int,str,float,float)
    def _on_recognized(self,state,cid,dist,ts):
        if state==0:
            self.photo_label.setPixmap(self.none_pix.scaled(
                self.photo_label.size(),Qt.KeepAspectRatio,Qt.SmoothTransformation))
            self.value_label.setText('[Face is not detected]')
            self.id_value.setText('[Face is not detected]')
            best='N/A'
        elif state==2:
            self.photo_label.setPixmap(self.unknown_pix.scaled(
                self.photo_label.size(),Qt.KeepAspectRatio,Qt.SmoothTransformation))
            self.value_label.setText('[Unknown Face]')
            self.id_value.setText(f"[Unknown Face]")
            best=cid
        else:
            sample_dir=Path(self.cfg['paths']['sample'])
            img_path=sample_dir/f"{cid}.jpg"
            pix=QPixmap(str(img_path)) if img_path.exists() else self.none_pix
            self.photo_label.setPixmap(pix.scaled(
                self.photo_label.size(),Qt.KeepAspectRatio,Qt.SmoothTransformation))
            name=self.id_to_name.get(cid,'[Unknown]')
            self.value_label.setText(name)
            self.id_value.setText(f'{cid}')
            best=name

        self.register_button.setEnabled(state == 2)
        fd='True' if state!=0 else 'False'
        d_txt=f"{dist:.2f}" if state>0 else 'N/A'
        self.footer_label.setText(
            f"Sebastian Olszak - Projekt pracy inżynierskiej | FACEID | Face_Detected: {fd} | Best: {best} | Distance: {d_txt}"
        )

    def open_register_window(self):
        self.setEnabled(False)
        self.timer.stop()
        self.camera.close()

        self.reg_win = RegisterFaceWindow(self.cfg, self.engine, parent=self)
        self.reg_win.finished.connect(self._on_register_closed)
        self.reg_win.show()

    def _on_register_closed(self, result=None):
        self.setEnabled(True)
        self.camera.open()
        self.timer.start(30)