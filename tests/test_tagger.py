"""Tagger tests: MP3 round-trip with USLT/SYLT/APIC plus real FLAC/Opus/M4A
files (generated via ffmpeg when available)."""

from __future__ import annotations

from mutagen.flac import FLAC
from mutagen.id3 import ID3
from mutagen.mp4 import MP4

from melodine.models import LyricsRecord, TrackMeta
from melodine.services.tagger import Tagger, is_audio_file

SYNCED = "[00:01.00]Hello\n[00:04.00]World\n"


def meta(artwork: bytes | None = b"\xff\xd8\xff\xe0fakejpeg") -> TrackMeta:
    return TrackMeta(
        title="Song",
        artist="Artist",
        album="Album",
        album_artist="Album Artist",
        genre="Rock",
        year=2020,
        track_number=3,
        track_total=12,
        duration=200.0,
        artwork=artwork,
    )


def lyrics() -> LyricsRecord:
    return LyricsRecord(plain="Hello\nWorld", synced=SYNCED, duration=200.0)


class TestIsAudioFile:
    def test_extensions(self, tmp_path):
        assert is_audio_file(tmp_path / "a.mp3")
        assert is_audio_file(tmp_path / "b.FLAC")
        assert is_audio_file(tmp_path / "c.opus")
        assert is_audio_file(tmp_path / "d.m4a")
        assert not is_audio_file(tmp_path / "e.txt")


class TestMP3:
    def test_full_round_trip(self, tagger: Tagger, mp3_file):
        assert tagger.apply(mp3_file, meta(), lyrics()) is True

        tags = ID3(str(mp3_file))
        assert str(tags["TIT2"]) == "Song"
        assert str(tags["TPE1"]) == "Artist"
        assert str(tags["TALB"]) == "Album"
        assert str(tags["TPE2"]) == "Album Artist"
        assert str(tags["TCON"]) == "Rock"
        assert "2020" in str(tags["TDRC"])
        assert "3/12" in str(tags["TRCK"])

        uslt = tags.getall("USLT")
        assert uslt and uslt[0].text == "Hello\nWorld"

        sylt = tags.getall("SYLT")
        assert sylt, "synced lyrics must be embedded as SYLT"
        synced_text = [text for text, _ts in sylt[0].text]
        assert "Hello" in synced_text

        apic = tags.getall("APIC")
        assert apic and apic[0].data.startswith(b"\xff\xd8")

    def test_has_lyrics(self, tagger: Tagger, mp3_file):
        assert Tagger.has_lyrics(mp3_file) is False
        tagger.apply(mp3_file, meta(), lyrics())
        assert Tagger.has_lyrics(mp3_file) is True

    def test_read_back(self, tagger: Tagger, mp3_file):
        tagger.apply(mp3_file, meta(), lyrics())
        result = tagger.read(mp3_file)
        assert result.title == "Song"
        assert result.artist == "Artist"
        assert result.album == "Album"
        assert result.duration > 0

    def test_no_lyrics_keeps_file_valid(self, tagger: Tagger, mp3_file):
        assert tagger.apply(mp3_file, meta(), None) is True
        assert Tagger.has_lyrics(mp3_file) is False

    def test_artwork_optional(self, tagger: Tagger, mp3_file):
        assert tagger.apply(mp3_file, meta(artwork=None), None) is True
        assert not ID3(str(mp3_file)).getall("APIC")


class TestFLAC:
    def test_round_trip(self, tagger: Tagger, ffmpeg_audio):
        path = ffmpeg_audio("track.flac", "flac")
        assert tagger.apply(path, meta(), lyrics()) is True
        audio = FLAC(str(path))
        assert audio["title"] == ["Song"]
        assert audio["artist"] == ["Artist"]
        assert audio["album"] == ["Album"]
        assert audio["LYRICS"] == ["Hello\nWorld"]
        assert audio["SYNCEDLYRICS"] == [SYNCED]
        assert audio.pictures and audio.pictures[0].data.startswith(b"\xff\xd8")
        assert Tagger.has_lyrics(path) is True

    def test_read_back(self, tagger: Tagger, ffmpeg_audio):
        path = ffmpeg_audio("read.flac", "flac")
        tagger.apply(path, meta(), None)
        result = tagger.read(path)
        assert result.title == "Song"
        assert result.duration > 0


class TestOpus:
    def test_round_trip(self, tagger: Tagger, ffmpeg_audio):
        path = ffmpeg_audio("track.opus", "libopus")
        assert tagger.apply(path, meta(), lyrics()) is True
        from mutagen.oggopus import OggOpus

        audio = OggOpus(str(path))
        assert audio["title"] == ["Song"]
        assert "METADATA_BLOCK_PICTURE" in audio
        assert Tagger.has_lyrics(path) is True


class TestM4A:
    def test_round_trip(self, tagger: Tagger, ffmpeg_audio):
        path = ffmpeg_audio("track.m4a", "aac")
        assert tagger.apply(path, meta(), lyrics()) is True
        audio = MP4(str(path))
        assert audio["\xa9nam"] == ["Song"]
        assert audio["\xa9ART"] == ["Artist"]
        assert audio["\xa9alb"] == ["Album"]
        assert audio["\xa9lyr"] == ["Hello\nWorld"]
        assert audio["trkn"] == [(3, 12)]
        assert audio["covr"]
        assert Tagger.has_lyrics(path) is True


class TestUnsupported:
    def test_unsupported_extension(self, tagger: Tagger, tmp_path):
        path = tmp_path / "song.txt"
        path.write_text("nope")
        assert tagger.apply(path, meta(), None) is False
