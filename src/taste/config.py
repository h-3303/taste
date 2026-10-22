import json

from . import paths


def load() -> dict:
    p = paths.config_path()
    cfg = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    cfg.setdefault("connectors", {})
    return cfg


def save(cfg: dict):
    p = paths.config_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")
    return p


def connector(name: str) -> dict | None:
    c = load()["connectors"].get(name)
    return c if c and c.get("enabled") else None
