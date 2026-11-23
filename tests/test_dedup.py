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


class TestVariantSignature:
    """Variant keywords are part of track identity (live/remix/cover/...)."""

    def test_studio_has_no_variants(self):
        from melodine.services.dedup import variant_signature

        assert variant_signature("Song") == frozenset()
        assert variant_signature("Song (Remastered 2011)") == frozenset()

    def test_live_detected(self):
        from melodine.services.dedup import variant_signature

        assert variant_signature("Song (Live at Wembley)") == frozenset({"live"})
        assert variant_signature("Песня (вживую)") == frozenset({"live"})

    def test_remix_and_mashup_detected(self):
        from melodine.services.dedup import variant_signature

        assert variant_signature("Song (Remix)") == frozenset({"remix"})
        assert variant_signature("Song (Mashup)") == frozenset({"remix"})

    def test_cover_and_instrumental_detected(self):
        from melodine.services.dedup import variant_signature

        assert variant_signature("Song (Cover)") == frozenset({"cover"})
        assert variant_signature("Song (Instrumental)") == frozenset(
            {"instrumental"}
        )

    def test_remaster_is_not_a_variant(self):
        """Remaster/radio/edit/version keep the studio-recording identity."""
        from melodine.services.dedup import variant_signature

        assert variant_signature("Song (Remastered 2011)") == frozenset()
        assert variant_signature("Song (Radio Edit)") == frozenset()
        assert variant_signature("Song (Album Version)") == frozenset()

    def test_multiple_variants_combine(self):
        from melodine.services.dedup import variant_signature

        assert variant_signature("Song (Live Acoustic)") == frozenset(
            {"live", "acoustic"}
        )


class TestVariantAwareDedup:
    """`Song` and `Song (Live)` are different recordings, never duplicates."""

    def test_live_is_not_studio_duplicate(self):
        assert not is_same_track(
            "Artist", "Song", "Artist", "Song (Live)", 200, 205
        )

    def test_live_vs_live_is_duplicate(self):
        assert is_same_track(
            "Artist", "Song (Live)", "Artist", "Song (Live at Wembley)", 200, 203
        )

    def test_remix_is_not_studio_duplicate(self):
        assert not is_same_track(
            "Artist", "Song", "Artist", "Song (Remix)", 200, 200
        )

    def test_cover_is_not_studio_duplicate(self):
        assert not is_same_track(
            "Artist", "Song", "Artist", "Song (Cover)", 200, 200
        )

    def test_remaster_is_studio_duplicate(self):
        """Same recording, just re-mastered: still a duplicate."""
        assert is_same_track(
            "Artist", "Song", "Artist", "Song (Remastered 2011)", 200, 200
        )

    def test_radio_edit_is_studio_duplicate(self):
        assert is_same_track(
            "Artist", "Song", "Artist", "Song (Radio Edit)", 200, 203
        )
