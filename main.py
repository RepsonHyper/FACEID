import sys
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from core.config import load_config
from core.db_utils import init_db_pool
from core.engine import FaceEngine
from gui.main_window import MainWindow

def main():
    config = load_config()
    init_db_pool(minconn=2, maxconn=10, dsn=config["db_conn"])

    engine = FaceEngine(
        embeddings_dir=config["paths"]["embeddings"],
        threshold=config["threshold"]
    )

    app = QApplication(sys.argv)
    window = MainWindow(config, engine)
    window.showMaximized()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()

# main.py
"""
import sys
from PySide6.QtWidgets import QApplication
from core.config import load_config
from core.db_utils import init_db_pool
from core.engine import FaceEngine
from gui.register_face import RegisterFaceWindow

def main():
    config = load_config()
    init_db_pool(minconn=2, maxconn=10, dsn=config["db_conn"])

    engine = FaceEngine(
        embeddings_dir=config["paths"]["embeddings"],
        threshold=config["threshold"]
    )

    app = QApplication(sys.argv)
    window = RegisterFaceWindow(config, engine)
    window.showMaximized()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
"""
#pyinstaller --onedir --noconfirm --windowed --name FACEID --icon Resources/app.ico --add-data "config.json;." --add-data "sample;sample" --add-data "embeddings;embeddings" main.py
