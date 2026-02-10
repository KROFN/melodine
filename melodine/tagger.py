from pathlib import Path

from mutagen.mp3 import MP3
from mutagen.id3 import ID3, TIT2, TPE1, APIC, ID3NoHeaderError


def add_tags(filepath: str, artist: str, title: str) -> bool:
    try:
        path = Path(filepath)
        if not path.exists():
            return False

        try:
            tags = ID3(str(path))
        except ID3NoHeaderError:
            tags = ID3()

        tags["TIT2"] = TIT2(encoding=3, text=title)
        tags["TPE1"] = TPE1(encoding=3, text=artist)
        tags.save(str(path))
        return True
    except Exception:
        return False


def add_cover(filepath: str, cover_data: bytes, mime: str = "image/jpeg") -> bool:
    try:
        try:
            tags = ID3(filepath)
        except ID3NoHeaderError:
            tags = ID3()

        tags["APIC"] = APIC(
            encoding=3,
            mime=mime,
            type=3,  # Cover (front)
            desc="Cover",
            data=cover_data,
        )
        tags.save(filepath)
        return True
    except Exception:
        return False


def get_info(filepath: str) -> dict | None:
    try:
        audio = MP3(filepath)
        info = {
            "duration": audio.info.length,
            "bitrate": audio.info.bitrate // 1000,
            "artist": "",
            "title": "",
        }

        try:
            tags = ID3(filepath)
            if "TPE1" in tags:
                info["artist"] = str(tags["TPE1"])
            if "TIT2" in tags:
                info["title"] = str(tags["TIT2"])
        except Exception:
            pass

        return info
    except Exception:
        return None