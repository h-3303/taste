"""boards.net.Http and connector downloads keep the polite-fetch rules: banned hosts refused on every hop, paced per host."""
import httpx
import pytest

from taste.boards import net
from taste.library import fetch as lfetch


def _redirect_to_arena(request: httpx.Request) -> httpx.Response:
    if request.url.host == "ok.example":
        return httpx.Response(302, headers={"Location": "https://cdn.are.na/z.png"})
    if "are.na" in request.url.host:
        raise AssertionError(f"fetched banned {request.url}")
    return httpx.Response(200, content=b"img")


class Limiter:
    def __init__(self):
        self.hosts = []

    def wait(self, url):
        self.hosts.append(lfetch.host(url))


def test_http_refuses_a_redirect_to_a_banned_host(tmp_path):
    http = net.Http(transport=httpx.MockTransport(_redirect_to_arena), limiter=Limiter())
    with pytest.raises(lfetch.FetchError, match="banned"):
        http.download("https://ok.example/a.png", tmp_path / "a.png")
    assert not (tmp_path / "a.png").exists()


def test_http_refuses_a_banned_host_outright(tmp_path):
    http = net.Http(transport=httpx.MockTransport(_redirect_to_arena), limiter=Limiter())
    with pytest.raises(lfetch.FetchError, match="banned"):
        http.get_json("https://www.are.na/api")


def test_http_paces_every_request_per_host(tmp_path):
    lim = Limiter()
    http = net.Http(transport=httpx.MockTransport(lambda r: httpx.Response(200, content=b"x")), limiter=lim)
    http.download("https://a.example/1.png", tmp_path / "1.png")
    http.download("https://b.example/2.png", tmp_path / "2.png")
    assert lim.hosts == ["a.example", "b.example"]


def test_http_uses_the_taste_user_agent():
    assert net.UA == lfetch.UA


def test_connector_downloads_go_through_the_polite_fetcher(tmp_path, monkeypatch):
    from taste.boards.cli import connector_candidates
    from taste.connectors.folders import FolderNotes

    class Notes(FolderNotes):
        def items(self):
            return [{"path": None, "url": "https://ok.example/a.png", "title": "t",
                     "source_url": "https://ok.example/a.png", "note": "n"}]

    f = lfetch.Fetcher(client=httpx.Client(transport=httpx.MockTransport(_redirect_to_arena), follow_redirects=True), limiter=Limiter())
    monkeypatch.setattr(lfetch, "Fetcher", lambda *a, **k: f)
    cands, failures = connector_candidates([Notes(tmp_path)], tmp_path / "raw")
    assert cands == [] and len(failures) == 1 and "banned" in failures[0]
    assert not any((tmp_path / "raw").rglob("*.png"))


def test_inbox_add_refuses_a_banned_host(tmp_path, monkeypatch, capsys):
    from taste.boards.cli import main
    monkeypatch.setenv("TASTE_DATA", str(tmp_path / "data"))
    assert main(["inbox-add", "1", "https://cdn.are.na/x.png", "--source", "https://www.are.na/block/1", "--note", "n"]) == 1
    assert "banned" in capsys.readouterr().out
    assert not any((tmp_path / "data").rglob("*.png"))
