from PySide6.QtWidgets import (
    QDialog, QWidget, QLabel, QLineEdit, QPushButton,
    QListWidget, QListWidgetItem, QAbstractItemView,
    QVBoxLayout, QHBoxLayout, QFrame, QApplication, QMessageBox
)
from PySide6.QtCore import Qt, QTimer, QRect, QEvent, QSize
from PySide6.QtGui import QImage, QPixmap, QIcon, QPainter, QPen, QColor


import numpy as np
from pathlib import Path
from core.camera import CameraHandler

class RegisterFaceWindow(QDialog):
    def __init__(self, config, engine, parent=None):
        super().__init__(parent)
        self.engine = engine
        self.cfg = config

        self.setWindowFlags(
            Qt.Window
            | Qt.WindowSystemMenuHint
            | Qt.WindowMinimizeButtonHint
            | Qt.WindowMaximizeButtonHint
            | Qt.WindowCloseButtonHint
        )

        self.setWindowTitle("Sebastian Olszak - FACEID | Register Panel")
        self.setWindowIcon(QIcon(":/icon.png"))
        QTimer.singleShot(0, self._force_maximize)

        self.camera = CameraHandler(width=1280, height=960)
        self.video_label = QLabel(self)
        self.video_label.setFixedSize(1280, 960)
        self.video_label.setAlignment(Qt.AlignCenter)

        self.snap_btn = QPushButton("Take Photo", self)
        self.snap_btn.setEnabled(False)  # tylko gdy twarz
        self.snap_btn.setStyleSheet("""
            QPushButton {
                background-color: #404040; color: white;
                border-radius: 5px; padding: 8px; font-size: 14px;
            }
            QPushButton:disabled { background-color: #282828; }
            QPushButton:hover:!disabled { background-color: #005F9E; }
        """)
        self.snap_btn.clicked.connect(self._take_photo)

        self.right_frame = QFrame(self)
        self.right_frame.setFrameShape(QFrame.StyledPanel)
        self.right_frame.setStyleSheet('background: #2E2E2E; border-radius: 10px;')
        self.right_layout = QVBoxLayout(self.right_frame)
        self.right_layout.setContentsMargins(20,20,20,20)
        self.right_layout.setSpacing(15)

        self.name_label = QLabel("Name", self.right_frame)
        self.name_label.setStyleSheet(
            'color: white; background: #404040; border-radius: 5px; padding: 8px; font-size: 16px;'
        )
        self.name_input = QLineEdit(self.right_frame)
        self.name_input.setPlaceholderText("Type your name here...")
        self.name_input.setStyleSheet(
            'color: white; background: #606060; border-radius: 5px; padding: 8px; font-size: 16px;'
        )
        self.name_input.textChanged.connect(self._update_register_enabled)
        self.right_layout.addWidget(self.name_label)
        self.right_layout.addWidget(self.name_input)

        self.photo_list = QListWidget(self.right_frame)
        self.photo_list.setViewMode(QListWidget.IconMode)
        self.photo_list.setIconSize(QSize(128,128))
        self.photo_list.setResizeMode(QListWidget.Adjust)
        self.photo_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.photo_list.setSpacing(10)
        self.photo_list.installEventFilter(self)
        self.right_layout.addWidget(self.photo_list)

        btn_layout = QHBoxLayout()
        self.del_btn = QPushButton("Delete", self.right_frame)
        self.del_btn.setStyleSheet(
            'color: white; background: #404040; border-radius: 5px; padding: 8px; font-size: 14px;'
        )
        self.del_btn.clicked.connect(self._delete_selected_photos)
        btn_layout.addWidget(self.del_btn)

        self.main_btn = QPushButton("Set as main", self.right_frame)
        self.main_btn.setStyleSheet(
            'color: white; background: #404040; border-radius: 5px; padding: 8px; font-size: 14px;'
        )
        self.main_btn.clicked.connect(self._mark_main_photo)
        btn_layout.addWidget(self.main_btn)
        self.right_layout.addLayout(btn_layout)

        self.register_btn = QPushButton("Register", self.right_frame)
        self.register_btn.setEnabled(False)
        self.register_btn.setStyleSheet("""
            QPushButton {
                background-color: #404040; color: white;
                border-radius: 5px; padding: 8px; font-size: 16px;
            }
            QPushButton:enabled {
                background-color: #007ACC;
            }
        """)
        self.register_btn.clicked.connect(self._on_register)
        self.right_layout.addWidget(self.register_btn)

        self.footer_label = QLabel(
            "Sebastian Olszak - Projekt pracy inżynierskiej | FACEID | Register panel", self
        )
        self.footer_label.setFixedHeight(30)
        self.footer_label.setAlignment(Qt.AlignLeft|Qt.AlignVCenter)
        self.footer_label.setStyleSheet('font-size:14px;padding-left:10px;')

        central = QWidget(self); self.setLayout(QVBoxLayout(central))
        self.layout().setContentsMargins(0,0,0,0); self.layout().setSpacing(0)
        content = QHBoxLayout()

        left = QWidget(self); left_l=QVBoxLayout(left)
        left_l.setContentsMargins(5,5,5,5); left_l.setAlignment(Qt.AlignCenter)
        left_l.addWidget(self.video_label); left_l.addWidget(self.snap_btn,alignment=Qt.AlignCenter)
        content.addWidget(left,3)

        content.addWidget(self.right_frame,2)
        self.layout().addLayout(content); self.layout().addWidget(self.footer_label)

        self._temp_photos, self._main_photo_index = [], None

        self.timer=QTimer(self); self.timer.timeout.connect(self._on_frame)
        self.camera.open(); self.timer.start(30)

    def _force_maximize(self):
        geom: QRect = QApplication.primaryScreen().availableGeometry()
        self.setGeometry(geom)

    def _on_frame(self):
        ret, frame = self.camera.read()
        if not ret: return
        faces = self.engine.face_analyzer.get(frame)
        disp = frame.copy()
        # ramka na podgląd
        if faces:
            x1,y1,x2,y2 = faces[0].bbox.astype(int)
            import cv2
            cv2.rectangle(disp,(x1,y1),(x2,y2),(0,255,0),2)
            self.snap_btn.setEnabled(True)
        else:
            self.snap_btn.setEnabled(False)
        rgb=disp[:,:,::-1]; rgb=np.ascontiguousarray(rgb)
        h,w,_=rgb.shape; bpl=rgb.strides[0]
        img=QImage(rgb.data,w,h,bpl,QImage.Format_RGB888)
        pix=QPixmap.fromImage(img).scaled(self.video_label.size(),
                                          Qt.KeepAspectRatio,Qt.SmoothTransformation)
        self.video_label.setPixmap(pix)

    def _take_photo(self):
        pix=self.video_label.pixmap()
        if pix: self._add_photo(pix)

    def _add_photo(self,pixmap):
        item=QListWidgetItem(); item.setIcon(QIcon(pixmap))
        item.setData(Qt.UserRole,pixmap)
        self.photo_list.addItem(item); self._temp_photos.append(pixmap)
        self._refresh_photo_list()

    def _refresh_photo_list(self):
        for idx in range(self.photo_list.count()):
            item=self.photo_list.item(idx)
            base=item.data(Qt.UserRole)
            framed=base.copy()
            if idx==self._main_photo_index:
                painter=QPainter(framed)
                pen=QPen(QColor("#00AEEF"),6)
                painter.setPen(pen)
                painter.drawRect(2,2,framed.width()-4,framed.height()-4)
                painter.end()
            item.setIcon(QIcon(framed))
        self._update_register_enabled()

    def _delete_selected_photos(self):
        for idx in reversed(range(self.photo_list.count())):
            if self.photo_list.item(idx).isSelected():
                self.photo_list.takeItem(idx); del self._temp_photos[idx]
                if self._main_photo_index==idx: self._main_photo_index=None
        self._refresh_photo_list()

    def _mark_main_photo(self):
        sel=self.photo_list.selectedIndexes()
        if sel: self._main_photo_index=sel[0].row()
        self._refresh_photo_list()

    def _update_register_enabled(self):
        ok = (
            bool(self.name_input.text().strip()) and
            len(self._temp_photos) >= 5 and
            self._main_photo_index is not None
        )
        self.register_btn.setEnabled(ok)

    def _on_register(self):
        import uuid
        from datetime import datetime, timezone
        import numpy as np

        new_id = str(uuid.uuid4())
        name = self.name_input.text().strip()
        now = datetime.now(timezone.utc)

        from pathlib import Path
        emb_dir = Path(self.cfg['paths']['embeddings']) / new_id
        emb_dir.mkdir(parents=True, exist_ok=True)

        for idx, pixmap in enumerate(self._temp_photos):
            img = pixmap.toImage().convertToFormat(QImage.Format_RGB888)
            ptr = img.bits()
            bpl = img.bytesPerLine()
            h = img.height()
            total = bpl * h
            buffer = ptr[:total]
            arr = np.frombuffer(buffer, dtype=np.uint8).reshape(h, img.width(), 3)
            embedding = self.engine.get_embedding(arr)
            # zapis
            np.save(emb_dir / f"{idx}.npy", embedding)

        sample_dir = Path(self.cfg['paths']['sample'])
        sample_dir.mkdir(parents=True, exist_ok=True)
        main_pix = self._temp_photos[self._main_photo_index]
        main_pix.save(str(sample_dir / f"{new_id}.jpg"))

        from core.db_utils import create_person
        create_person(new_id, name, now)

        QMessageBox.information(
            self, "Registered",
            f"User {name}\nID: {new_id}\nwas registered successfully."
        )
        self.close()


    def eventFilter(self,obj,ev):
        if obj is self.photo_list and ev.type()==QEvent.KeyPress and ev.key()==Qt.Key_Delete:
            self._delete_selected_photos(); return True
        return super().eventFilter(obj,ev)

    def closeEvent(self,ev):
        self.timer.stop(); self.camera.close()
        super().closeEvent(ev)
