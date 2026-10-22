from pathlib import Path

from .models import Candidate

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".gif"}


def vault_media(vault: Path, codes: list[str]) -> list[Candidate]:
    media = Path(vault) / "Sources" / "media"
    out = []
    for code in codes:
        for p in sorted(media.glob(f"*/{code}_*")):
            if p.suffix.lower() in IMAGE_SUFFIXES:
                out.append(Candidate("vault", p, f"https://www.instagram.com/p/{code}/", f"ig-{code}", f"@{p.parent.name} {code}"))
    return out
