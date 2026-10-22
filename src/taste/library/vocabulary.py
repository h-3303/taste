import re
import unicodedata

TERMS = [
    "neumorphism", "glassmorphism", "skeuomorphism", "flat design", "material design", "swiss international",
    "bauhaus", "brutalist web", "brutalist poster", "neo-brutalism", "minimalism", "maximalism", "memphis design",
    "de stijl", "constructivism", "art deco", "art nouveau", "psychedelic poster", "risograph", "letterpress",
    "zine collage", "punk collage", "cut-out collage", "vaporwave", "synthwave", "y2k chrome", "frutiger aero",
    "web 1.0", "pixel art ui", "terminal ui", "ascii art", "generative art", "data visualisation poster",
    "isometric illustration", "line art illustration", "editorial grid", "magazine layout", "typographic poster",
    "kinetic typography", "grotesk type specimen", "serif editorial", "monospace ui", "dark mode ui", "bento grid",
    "dashboard ui", "mobile app ui", "e-commerce ui", "landing page hero", "3d render abstract", "claymorphism",
    "liquid chrome", "holographic foil", "grain texture", "paper texture", "scandinavian interior",
    "japanese minimal", "wabi sabi", "mid-century modern", "industrial", "cyberpunk", "solarpunk", "cottagecore",
    "dark academia", "luxury fashion editorial", "streetwear lookbook",
]
assert len(TERMS) == 65


def slugify(text: str) -> str:
    text = unicodedata.normalize("NFKD", str(text or "")).encode("ascii", "ignore").decode()
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return text or "untitled"


def term_slug(term: str) -> str:
    return slugify(term)
