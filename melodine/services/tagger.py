"""Multi-format tagging via mutagen.

Supported containers and the lyrics strategy:

* MP3  - ID3 ``USLT`` (plain) + ``SYLT`` (synced, ms) + ``APIC`` artwork
* FLAC - VorbisComment ``LYRICS`` / ``SYNCEDLYRICS`` + Picture block
* OGG  - VorbisComment (same keys) + METADATA_BLOCK_PICTURE (base64)
* OPUS - same as OGG
* M4A  - MP4 ``\xa9lyr`` + freeform ``----:com.apple.iTunes:SYNCEDLYRICS``
         + ``covr`` artwork
"""

from __future__ import annotations

import base64
from pathlib import Path

from mutagen.flac import FLAC, Picture
from mutagen.id3 import (
    APIC,
    ID3,
    SYLT,
    TALB,
    TCON,
    TDRC,
    TIT2,
    TPE1,
    TPE2,
    TRCK,
    USLT,
    Encoding,
    ID3NoHeaderError,
)
from mutagen.mp3 import MP3
from mutagen.mp4 import MP4, MP4Cover, MP4FreeForm
from mutagen.oggopus import OggOpus
from mutagen.oggvorbis import OggVorbis

from melodine.core.logging import get_logger
from melodine.models import LyricsRecord, TrackMeta
from melodine.services.lrclib import parse_lrc

logger = get_logger("tagger")

AUDIO_EXTENSIONS = {".mp3", ".flac", ".ogg", ".opus", ".m4a", ".mp4"}


def is_audio_file(path: str | Path) -> bool:
    return Path(path).suffix.lower() in AUDIO_EXTENSIONS


class Tagger:
    """Write enriched metadata, artwork and lyrics into audio files."""

    # ------------------------------------------------------------------ #
    # writing
    # ------------------------------------------------------------------ #

    def apply(
        self,
        path: str | Path,
        meta: TrackMeta,
        lyrics: LyricsRecord | None = None,
    ) -> bool:
        """Tag ``path``; returns True on success (never raises)."""
        try:
            suffix = Path(path).suffix.lower()
            if suffix == ".mp3":
                return self._apply_mp3(path, meta, lyrics)
            if suffix == ".flac":
                return self._apply_flac(path, meta, lyrics)
            if suffix in {".ogg", ".opus"}:
                return self._apply_vorbis(path, meta, lyrics)
            if suffix in {".m4a", ".mp4"}:
                return self._apply_mp4(path, meta, lyrics)
            logger.warning("unsupported extension for tagging: %s", path)
            return False
        except Exception as exc:
            logger.error("tagging failed for %s: %s", path, exc)
            return False

    # -- MP3 --------------------------------------------------------------- #

    def _apply_mp3(self, path: str | Path, meta: TrackMeta, lyrics: LyricsRecord | None) -> bool:
        file_path = str(path)
        try:
            tags = ID3(file_path)
        except ID3NoHeaderError:
            tags = ID3()

        if meta.title:
            tags["TIT2"] = TIT2(encoding=Encoding.UTF8, text=meta.title)
        if meta.artist:
            tags["TPE1"] = TPE1(encoding=Encoding.UTF8, text=meta.artist)
        if meta.album:
            tags["TALB"] = TALB(encoding=Encoding.UTF8, text=meta.album)
        if meta.album_artist:
            tags["TPE2"] = TPE2(encoding=Encoding.UTF8, text=meta.album_artist)
        if meta.genre:
            tags["TCON"] = TCON(encoding=Encoding.UTF8, text=meta.genre)
        if meta.year:
            tags["TDRC"] = TDRC(encoding=Encoding.UTF8, text=str(meta.year))
        if meta.track_number:
            total = meta.track_total or ""
            value = f"{meta.track_number}/{total}" if total else str(meta.track_number)
            tags["TRCK"] = TRCK(encoding=Encoding.UTF8, text=value)

        # Drop stale lyrics frames before writing fresh ones.
        tags.delall("USLT")
        tags.delall("SYLT")
        if lyrics is not None:
            if lyrics.has_plain:
                tags.add(
                    USLT(
                        encoding=Encoding.UTF8,
                        lang="eng",
                        desc="",
                        text=lyrics.plain,
                    )
                )
            if lyrics.has_synced:
                synced = [(line, ms) for ms, line in parse_lrc(lyrics.synced)]
                tags.add(
                    SYLT(
                        encoding=Encoding.UTF8,
                        lang="eng",
                        format=2,  # milliseconds
                        type=1,  # lyrics
                        desc="",
                        text=synced,
                    )
                )

        if meta.artwork:
            tags.delall("APIC")
            tags.add(
                APIC(
                    encoding=Encoding.UTF8,
                    mime="image/jpeg",
                    type=3,  # front cover
                    desc="Cover",
                    data=meta.artwork,
                )
            )

        tags.save(file_path)
        return True

    # -- FLAC -------------------------------------------------------------- #

    def _apply_flac(self, path: str | Path, meta: TrackMeta, lyrics: LyricsRecord | None) -> bool:
        audio = FLAC(str(path))
        self._fill_vorbis(audio, meta, lyrics)
        if meta.artwork:
            audio.clear_pictures()
            picture = Picture()
            picture.type = 3
            picture.mime = "image/jpeg"
            picture.desc = "Cover"
            picture.data = meta.artwork
            audio.add_picture(picture)
        audio.save()
        return True

    # -- OGG / OPUS --------------------------------------------------------- #

    def _apply_vorbis(
        self, path: str | Path, meta: TrackMeta, lyrics: LyricsRecord | None
    ) -> bool:
        suffix = Path(path).suffix.lower()
        audio = OggOpus(str(path)) if suffix == ".opus" else OggVorbis(str(path))
        self._fill_vorbis(audio, meta, lyrics)
        if meta.artwork:
            picture = Picture()
            picture.type = 3
            picture.mime = "image/jpeg"
            picture.desc = "Cover"
            picture.data = meta.artwork
            audio["metadata_block_picture"] = [
                base64.b64encode(picture.write()).decode("ascii")
            ]
        audio.save()
        return True

    @staticmethod
    def _fill_vorbis(
        audio: FLAC | OggVorbis | OggOpus,
        meta: TrackMeta,
        lyrics: LyricsRecord | None,
    ) -> None:
        mapping = {
            "title": meta.title,
            "artist": meta.artist,
            "album": meta.album,
            "albumartist": meta.album_artist,
            "genre": meta.genre,
            "date": str(meta.year) if meta.year else "",
        }
        if meta.track_number:
            total = f"/{meta.track_total}" if meta.track_total else ""
            mapping["tracknumber"] = f"{meta.track_number}{total}"
        for key, value in mapping.items():
            if value:
                audio[key] = [value]
        if lyrics is not None:
            if lyrics.has_plain:
                audio["LYRICS"] = [lyrics.plain]
            elif lyrics.has_synced:
                audio["LYRICS"] = [lyrics.synced]
            if lyrics.has_synced:
                audio["SYNCEDLYRICS"] = [lyrics.synced]

    # -- M4A ---------------------------------------------------------------- #

    def _apply_mp4(self, path: str | Path, meta: TrackMeta, lyrics: LyricsRecord | None) -> bool:
        audio = MP4(str(path))
        if meta.title:
            audio["\xa9nam"] = [meta.title]
        if meta.artist:
            audio["\xa9ART"] = [meta.artist]
        if meta.album:
            audio["\xa9alb"] = [meta.album]
        if meta.album_artist:
            audio["aART"] = [meta.album_artist]
        if meta.genre:
            audio["\xa9gen"] = [meta.genre]
        if meta.year:
            audio["\xa9day"] = [str(meta.year)]
        if meta.track_number:
            audio["trkn"] = [(meta.track_number, meta.track_total or 0)]
        if lyrics is not None:
            if lyrics.has_plain:
                audio["\xa9lyr"] = [lyrics.plain]
            elif lyrics.has_synced:
                audio["\xa9lyr"] = [lyrics.synced]
            if lyrics.has_synced:
                audio["----:com.apple.iTunes:SYNCEDLYRICS"] = [
                    MP4FreeForm(lyrics.synced.encode("utf-8"))
                ]
        if meta.artwork:
            audio["covr"] = [MP4Cover(meta.artwork, imageformat=MP4Cover.FORMAT_JPEG)]
        audio.save()
        return True

    # ------------------------------------------------------------------ #
    # reading
    # ------------------------------------------------------------------ #

    def read(self, path: str | Path) -> TrackMeta:
        """Read artist/title/album/duration from any supported file."""
        file_path = str(path)
        meta = TrackMeta()
        try:
            audio = MP3(file_path)
            tags = audio.tags
            if tags:
                meta.title = str(tags.get("TIT2", ""))
                meta.artist = str(tags.get("TPE1", ""))
                meta.album = str(tags.get("TALB", ""))
            meta.duration = audio.info.length
            return meta
        except Exception:
            pass

        for loader in (FLAC, OggOpus, OggVorbis, MP4):
            try:
                audio = loader(file_path)
            except Exception:
                continue
            tags = audio.tags or {}
            if isinstance(audio, MP4):
                meta.title = str((tags.get("\xa9nam") or [""])[0])
                meta.artist = str((tags.get("\xa9ART") or [""])[0])
                meta.album = str((tags.get("\xa9alb") or [""])[0])
            else:
                meta.title = str((tags.get("title") or [""])[0])
                meta.artist = str((tags.get("artist") or [""])[0])
                meta.album = str((tags.get("album") or [""])[0])
            try:
                meta.duration = float(audio.info.length)
            except (AttributeError, ValueError):
                meta.duration = 0.0
            return meta

        raise ValueError(f"cannot read audio file: {file_path}")

    @staticmethod
    def has_lyrics(path: str | Path) -> bool:
        """Best-effort check whether the file already carries lyrics."""
        file_path = str(path)
        try:
            tags = ID3(file_path)
            return bool(tags.getall("USLT") or tags.getall("SYLT"))
        except Exception:
            pass
        try:
            audio = MP4(file_path)
            return bool(audio.get("\xa9lyr"))
        except Exception:
            pass
        try:
            audio = FLAC(file_path)
            return bool(audio.get("LYRICS") or audio.get("SYNCEDLYRICS"))
        except Exception:
            pass
        try:
            audio = OggOpus(file_path)
            return bool(audio.get("LYRICS") or audio.get("SYNCEDLYRICS"))
        except Exception:
            pass
        try:
            audio = OggVorbis(file_path)
            return bool(audio.get("LYRICS") or audio.get("SYNCEDLYRICS"))
        except Exception:
            return False
