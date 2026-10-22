"""Stage records: one plain-JSON file per stage pass (rounds/<stage>-<n>.json), page ingest and steering."""
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

from .boards.run import Run, clean_text

STAGES = ("broad", "boards", "directions", "final", "refine", "review")
VOTES = {"broad": ("like", "dislike"), "boards": ("keep", "drop"), "directions": ("keep", "drop"),
         "refine": ("pick",), "review": ("pick",), "final": ()}
NOTE_LIMIT = 600
STALE = "These votes were made on an older version of the page: ask to vote again"


class StalePage(ValueError):
    pass


@dataclass
class ItemState:
    vote: str | None
    note: str = ""


@dataclass
class Round:
    stage: str
    n: int
    repeat_of: int | None
    shown: list[str]
    items: dict[str, ItemState] = field(default_factory=dict)
    combos: list[dict] = field(default_factory=list)
    prompts: list[str] = field(default_factory=list)
    requests: list[dict] = field(default_factory=list)
    note: str = ""
    rendered_at: str = ""
    at: str | None = None


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _when(text: str) -> datetime:
    d = datetime.fromisoformat(str(text).replace("Z", "+00:00"))
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def _check_stage(stage: str) -> None:
    if stage not in STAGES:
        raise ValueError(f"unknown stage {stage!r} (one of {', '.join(STAGES)})")


def _name(stage: str, n: int) -> str:
    return f"rounds/{stage}-{n}.json"


def _numbers(run: Run, stage: str) -> list[int]:
    d = run.path / "rounds"
    pat = re.compile(rf"{re.escape(stage)}-(\d+)\.json")
    return sorted(int(m.group(1)) for p in d.glob(f"{stage}-*.json") if (m := pat.fullmatch(p.name))) if d.is_dir() else []


def next_n(run: Run, stage: str) -> int:
    _check_stage(stage)
    return max(_numbers(run, stage), default=0) + 1


def _save(run: Run, r: Round) -> Round:
    run.write(_name(r.stage, r.n), asdict(r))
    return r


def start(run: Run, stage: str, shown: list[str], repeat_of: int | None = None, rendered_at: str | None = None) -> Round:
    n = next_n(run, stage)
    return _save(run, Round(stage, n, repeat_of, list(shown), rendered_at=rendered_at or _now()))


def load(run: Run, stage: str, n: int) -> Round:
    _check_stage(stage)
    if not run.has(_name(stage, n)):
        raise ValueError(f"no {stage} round {n} has been started")
    d = run.read(_name(stage, n))
    d["items"] = {k: ItemState(**v) for k, v in d["items"].items()}
    return Round(**d)


def all_rounds(run: Run, stage: str | None = None) -> list[Round]:
    if stage is not None:
        _check_stage(stage)
    stages = [stage] if stage else STAGES
    return [load(run, s, n) for s in stages for n in _numbers(run, s)]


def _note(text) -> str:
    return clean_text(text, limit=NOTE_LIMIT, markdown=False)


def ingest(run: Run, stage: str, n: int, doc: dict) -> Round:
    r = load(run, stage, n)
    at = doc.get("at")
    if at and _when(at) < _when(r.rendered_at):
        raise StalePage(STALE)
    allowed = VOTES[stage]
    r.items = {}
    for iid in r.shown:
        v = (doc.get("items") or {}).get(iid)
        if v is None:
            continue
        vote = v.get("vote")
        r.items[iid] = ItemState(vote if vote in allowed else None, _note(v.get("note")))
    r.combos = [{"name": _note(c.get("name")), "parts": {_note(k): _note(v) for k, v in (c.get("parts") or {}).items()},
                 "note": _note(c.get("note"))} for c in doc.get("combos") or []]
    r.prompts = [p for p in (_note(p) for p in doc.get("prompts") or []) if p]
    r.requests = []
    for q in doc.get("requests") or []:
        if q.get("type") == "more-like" and q.get("id"):
            r.requests.append({"type": "more-like", "id": _note(q["id"])})
        elif q.get("type") == "add-url" and q.get("url"):
            r.requests.append({"type": "add-url", "url": str(q["url"]).strip()})
    r.note = _note(doc.get("note"))
    r.at = at
    return _save(run, r)


def record_final(run: Run, comments: list[dict]) -> Round:
    """The final stage lives on a Design canvas: its comments become pins in the next `final` pass."""
    demo = run.read("published.json").get("demo_at") if run.has("published.json") else None
    ids = [f"pin-{k}" for k in range(1, len(comments) + 1)]
    r = start(run, "final", ids, rendered_at=demo or _now())
    r.items = {i: ItemState(None, _note(c.get("text"))) for i, c in zip(ids, comments)}
    r.at = _now()
    return _save(run, r)


def _final_votes(run: Run) -> dict[str, str]:
    votes: dict[str, str] = {}
    for r in all_rounds(run):
        for iid, s in r.items.items():
            if s.vote:
                votes[iid] = s.vote
    return votes


def steering(run: Run) -> dict:
    votes = _final_votes(run)
    out = {"likes": [i for i, v in votes.items() if v == "like"],
           "dislikes": [i for i, v in votes.items() if v == "dislike"],
           "kept": [i for i, v in votes.items() if v == "keep"],
           "dropped": [i for i, v in votes.items() if v == "drop"],
           "notes": [], "combos": [], "prompts": [], "requests": []}
    for r in all_rounds(run):
        for iid in r.shown:
            s = r.items.get(iid)
            if s and s.note:
                out["notes"].append({"stage": r.stage, "n": r.n, "id": iid, "text": s.note})
        if r.note:
            out["notes"].append({"stage": r.stage, "n": r.n, "id": None, "text": r.note})
        out["combos"] += r.combos
        out["prompts"] += r.prompts
        out["requests"] += r.requests
    return out


_KIND_OF_TAG = {"texture": "texture", "type": "font", "font": "font", "typeface": "font", "type specimen": "font",
                "palette": "palette", "colour": "palette", "color": "palette"}
KINDS = ("image", "texture", "font", "palette")
THIN = 8


def _kind(item: dict) -> str:
    return item.get("kind") or _KIND_OF_TAG.get(str(item.get("tag", "")).strip().lower(), "image")


def gaps(run: Run) -> list[str]:
    from .boards import survey
    out = []
    if all_rounds(run, "broad"):
        by_id = {it["id"]: it for it in survey.load(run.path)}
        liked = {_kind(by_id[i]) for i in steering(run)["likes"] if i in by_id}
        out += [f"Nothing liked in {k}s yet: add some, or ask for more" for k in KINDS if k not in liked]
    if run.has("pool.json"):
        counts: dict[str, int] = {}
        for img in run.read("pool.json").get("images", []):
            if img.get("style") is not None:
                counts[str(img["style"])] = counts.get(str(img["style"]), 0) + 1
        out += [f"Direction {d} is thin ({n} images)" for d, n in sorted(counts.items()) if n < THIN]
    return out
