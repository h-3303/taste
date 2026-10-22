import pytest

from taste.library.models import CollectionDraft, ItemDraft, SourceInfo
from taste.library.sources import base


class Dummy:
    info = SourceInfo("dummy", "Dummy", "https://d.test", 1)

    def collections(self, fetch):
        yield CollectionDraft("dummy/all", "image", "All"), [ItemDraft("dummy:1", "image", "One", "https://d.test/1", "https://d.test/1.jpg")]


def test_register_and_get(monkeypatch):
    monkeypatch.setattr(base, "REGISTRY", {})
    base.register(Dummy())
    assert base.get("dummy").info.title == "Dummy"
    assert [a.info.slug for a in base.all_adapters()] == ["dummy"]
    with pytest.raises(KeyError, match="dummy"):
        base.get("nope")


def test_package_import_registers_real_adapters():
    import taste.library.sources   # noqa: F401
    assert {"polyhaven", "ambientcg"} <= set(base.REGISTRY)
    assert all(hasattr(a, "collections") and a.info.slug for a in base.all_adapters())
