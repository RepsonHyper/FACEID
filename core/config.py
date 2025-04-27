import json
from pathlib import Path
from json import JSONDecodeError

CONFIG_PATH = Path(__file__).parent.parent / "config.json"

DEFAULT_CONFIG = {
    "db_conn": "postgresql://postgres:ilkilk3213@localhost:5432/pickplace_db",
    "paths": {
        "embeddings": "embeddings/",
        "sample": "sample/"
    },
    "threshold": 1.07
}

def save_config(cfg: dict):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)

def merge_defaults(default: dict, current: dict):
    for key, val in default.items():
        if key not in current or not isinstance(current[key], type(val)):
            current[key] = val
        elif isinstance(val, dict):
            merge_defaults(val, current[key])

def validate_paths(cfg: dict):
    base_dir = Path(__file__).parent.parent
    for _, rel_path in cfg["paths"].items():
        p = base_dir / rel_path
        if not p.exists():
            p.mkdir(parents=True, exist_ok=True)

def load_config() -> dict:
    try:
        raw = CONFIG_PATH.read_text(encoding="utf-8")
        cfg = json.loads(raw)
    except (FileNotFoundError, JSONDecodeError):
        cfg = {}
    merge_defaults(DEFAULT_CONFIG, cfg)
    validate_paths(cfg)
    save_config(cfg)
    return cfg
