"""Track title cleaning tests (EN + RU noise)."""

from __future__ import annotations

from melodine.services.titles import (
    clean_artist,
    clean_track_title,
    parse_artist_title,
    token_similarity,
)


class TestCleanTrackTitle:
    def test_strips_official_video(self):
        result = clean_track_title("Around the World (Official Music Video)")
        assert result.title == "Around the World"

    def test_strips_square_brackets(self):
        result = clean_track_title("Song [Official Audio]")
        assert result.title == "Song"

    def test_strips_prod_by(self):
        result = clean_track_title("Song (Prod. by Rick Rubin)")
        assert result.title == "Song"

    def test_strips_hd_4k(self):
        result = clean_track_title("Song (HD) [4K]")
        assert result.title == "Song"

    def test_strips_mv(self):
        result = clean_track_title("Song MV")
        assert result.title == "Song"

    def test_strips_russian_noise(self):
        result = clean_track_title("Песня (Официальный клип)")
        assert result.title == "Песня"

    def test_strips_russian_audio(self):
        result = clean_track_title("Песня (аудиоверсия)")
        assert result.title == "Песня"

    def test_keeps_meaningful_brackets(self):
        result = clean_track_title("Song (Remastered 2011)")
        # remaster groups are noise -> stripped
        assert result.title == "Song"

    def test_extract_featured_artists(self):
        result = clean_track_title("Song (feat. Artist Two & Artist Three)")
        assert result.title == "Song"
        assert "Artist Two" in result.featured
        assert "Artist Three" in result.featured

    def test_unbracketed_feat(self):
        result = clean_track_title("Song ft. Someone")
        assert result.title == "Song"
        assert "Someone" in result.featured

    def test_trailing_pipe_noise(self):
        result = clean_track_title("Song | Official Video")
        assert result.title == "Song"

    def test_plain_title_untouched(self):
        result = clean_track_title("Bohemian Rhapsody")
        assert result.title == "Bohemian Rhapsody"
        assert result.featured == []

    def test_empty(self):
        assert clean_track_title("").title == ""


class TestCleanArtist:
    def test_strips_feat(self):
        assert clean_artist("Artist A feat. Artist B") == "Artist A"

    def test_strips_ft(self):
        assert clean_artist("Artist A ft. Artist B") == "Artist A"

    def test_bracketed_feat(self):
        assert clean_artist("Artist A (feat. Artist B)") == "Artist A"

    def test_plain(self):
        assert clean_artist("Daft Punk") == "Daft Punk"

    def test_empty(self):
        assert clean_artist("") == ""


class TestParseArtistTitle:
    def test_hyphen(self):
        assert parse_artist_title("Artist - Title") == ("Artist", "Title")

    def test_em_dash(self):
        assert parse_artist_title("Artist — Title") == ("Artist", "Title")

    def test_en_dash(self):
        assert parse_artist_title("Artist – Title") == ("Artist", "Title")

    def test_no_separator(self):
        artist, title = parse_artist_title("Only Title")
        assert artist == ""
        assert title == "Only Title"


class TestTokenSimilarity:
    def test_identical(self):
        assert token_similarity("hello world", "hello world") == 1.0

    def test_disjoint(self):
        assert token_similarity("alpha beta", "gamma delta") == 0.0

    def test_partial(self):
        similarity = token_similarity("one two three", "one two four")
        assert 0.0 < similarity < 1.0

    def test_empty(self):
        assert token_similarity("", "x") == 0.0
