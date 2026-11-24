"""Search fallback and safe automatic selection regressions."""
from __future__ import annotations

import pytest

from melodine.core.config import AppConfig
from melodine.models import SearchCandidate
from melodine.services.search import SearchService


@pytest.mark.parametrize("smart", [True, False])
def test_wrong_track_only_is_not_automatically_selected(monkeypatch, smart):
    cfg = AppConfig()
    cfg.download.smart_search = smart
    cfg.search.min_score = 0
    service = SearchService(cfg)
    wrong = SearchCandidate(source_id="wrong", title="Muse - Starlight",
                            channel="Muse - Topic", channel_is_verified=True)
    calls = []

    def search(query):
        calls.append(query)
        return [wrong]

    monkeypatch.setattr(service, "search", search)
    best, scored = service.best("Muse - Hysteria", target_artist="Muse", target_title="Hysteria")
    assert best is None
    assert scored[0].candidate is wrong
    assert len(calls) == len(set(calls))
    assert (len(calls) > 1) is smart


def test_fallback_finds_right_song_even_with_zero_minimum_score(monkeypatch):
    cfg = AppConfig()
    cfg.search.min_score = 0
    service = SearchService(cfg)
    wrong = SearchCandidate(source_id="wrong", title="Starlight", channel="Muse - Topic")
    right = SearchCandidate(source_id="right", title="Hysteria", channel="Muse")
    monkeypatch.setattr(service, "search",
                        lambda query: [wrong] if query == "Muse - Hysteria" else [right])
    best, scored = service.best("Muse - Hysteria", target_artist="Muse", target_title="Hysteria")
    assert best.candidate is right
    assert len(scored) == 2
