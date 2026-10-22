from ..models import CollectionDraft, ItemDraft, SourceInfo
from ..vocabulary import slugify
from .base import register

NICE = "https://raw.githubusercontent.com/Experience-Monks/nice-color-palettes/master/1000.json"
UIG = "https://raw.githubusercontent.com/ghosh/uiGradients/master/gradients.json"


class GithubDataAdapter:
    info = SourceInfo("github-data", "GitHub palette datasets", "https://github.com/Experience-Monks/nice-color-palettes", 1,
                      notes="nice-color-palettes (1000 palettes, MIT) and uiGradients (MIT)")

    def collections(self, fetch):
        nice = fetch.get_json(NICE)
        yield CollectionDraft("github-data/nice-color-palettes", "palette", "nice-color-palettes (top 1000 from ColourLovers)"), [
            ItemDraft(f"github-data:nice:{i}", "palette", f"nice palette #{i}", "https://github.com/Experience-Monks/nice-color-palettes",
                      NICE, meta={"colors": [c.lower() for c in cols], "count": len(cols)}, license="MIT")
            for i, cols in enumerate(nice)]
        grads = fetch.get_json(UIG)
        yield CollectionDraft("github-data/uigradients", "palette", "uiGradients"), [
            ItemDraft(f"github-data:uigradients:{slugify(g['name'])}", "palette", g["name"], "https://uigradients.com/#" + g["name"].replace(" ", ""),
                      UIG, tags=["gradient"], meta={"colors": [c.lower() for c in g["colors"]], "count": len(g["colors"]),
                                                    "css": f"linear-gradient(90deg, {', '.join(c.lower() for c in g['colors'])})"},
                      license="MIT")
            for g in grads if g.get("colors")]


ADAPTER = register(GithubDataAdapter())
