import numpy as np
from pathlib import Path
from insightface.app import FaceAnalysis
from core.db_utils import get_all_users
import psycopg2

class FaceEngine:
    def __init__(self, embeddings_dir: str, threshold: float):
        self.face_analyzer = FaceAnalysis(
            name='buffalo_l',
            providers=['CUDAExecutionProvider', 'CPUExecutionProvider']
        )
        self.face_analyzer.prepare(ctx_id=0, det_size=(640, 640))

        self.threshold = threshold

        self.embeddings_map = {}
        self._load_embeddings(embeddings_dir)

        self.id_to_name = {}
        self._load_user_data()

    def _load_embeddings(self, embeddings_dir: str):
        base = Path(embeddings_dir)
        for pid_dir in base.iterdir():
            if not pid_dir.is_dir(): continue
            vecs = []
            for npf in pid_dir.glob('*.npy'):
                v = np.load(npf).astype(np.float32)
                n = np.linalg.norm(v)
                if n > 0:
                    vecs.append(v / n)
            if vecs:
                self.embeddings_map[pid_dir.name] = vecs

    def _load_user_data(self):
        rows = get_all_users()
        for pid, name, _ in rows:
            self.id_to_name[str(pid)] = name

    def recognize(self, frame):
        faces = self.face_analyzer.get(frame)
        if not faces:
            return 0, None, None

        emb = faces[0].embedding.astype(np.float32)
        norm = np.linalg.norm(emb)
        if norm > 0:
            emb = emb / norm

        best_dist, best_id = float('inf'), None
        for pid, vecs in self.embeddings_map.items():
            for v in vecs:
                d = np.linalg.norm(emb - v)
                if d < best_dist:
                    best_dist, best_id = d, pid

        if best_id is None:
            return 0, None, None

        if best_dist <= self.threshold:
            return 1, best_id, best_dist
        else:
            return 2, best_id, best_dist

    def get_embedding(self, image: np.ndarray) -> np.ndarray:
        faces = self.face_analyzer.get(image)
        if not faces:
            raise ValueError("Brak twarzy na obrazie")
        emb = faces[0].embedding.astype(np.float32)
        norm = np.linalg.norm(emb)
        return emb / norm if norm > 0 else emb
