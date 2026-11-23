"""Deduplication normalization tests."""

from __future__ import annotations

from melodine.services.dedup import is_same_track, normalize_name


class TestNormalizeName:
    def test_lowercase_and_collapse(self):
        assert normalize_name("  Daft   PUNK ") == "daft punk"

    def test_removes_feat(self):
        assert normalize_name("Artist feat. Someone - Song") == "artist song"

    def test_removes_brackets(self):
        assert normalize_name("Song (Remastered 2011)") == "song"

    def test_removes_noise_words(self):
        assert normalize_name("Song (Official Video)") == "song"

    def test_removes_punctuation(self):
        assert normalize_name("Don't Stop Me Now!") == "dont stop me now"

    def test_strips_latin_accents(self):
        assert normalize_name("Björk") == "bjork"

    def test_cyrillic_preserved(self):
        assert normalize_name("Песня (Официальный клип)") == "песня"

    def test_equivalent_variants_match(self):
        a = normalize_name("Song (Official Audio)")
        b = normalize_name("song official audio")
        assert a == b

    def test_different_titles_differ(self):
        assert normalize_name("Song One") != normalize_name("Song Two")

    def test_empty(self):
        assert normalize_name("") == ""


class TestIsSameTrack:
    def test_identical(self):
        assert is_same_track("Artist", "Song", "Artist", "Song", 200, 200)

    def test_noise_tolerant(self):
        assert is_same_track(
            "Artist", "Song (Official Video)", "artist", "song", 200, 201
        )

    def test_duration_tolerance(self):
        assert is_same_track("Artist", "Song", "Artist", "Song", 200, 203, tolerance=3)
        assert not is_same_track(
            "Artist", "Song", "Artist", "Song", 200, 210, tolerance=3
        )

    def test_unknown_duration_is_duplicate(self):
        assert is_same_track("Artist", "Song", "Artist", "Song", 0, 0)

    def test_different_artist_not_duplicate(self):
        assert not is_same_track("Artist A", "Song", "Artist B", "Song", 200, 200)

    def test_missing_reference_not_duplicate(self):
        assert not is_same_track("Artist", "Song", "", "", 200, 200)
