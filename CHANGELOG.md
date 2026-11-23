# Changelog

All notable changes to Melodine are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and the project adheres to [Semantic Versioning](https://semver.org/).

## [2.0.0] - Flagship Overhaul / Флагманский релиз

### Added - six killer features / Шесть киллер-фич

- **Anti-MV Studio Scorer** - search results are ranked 0-100 so official
  studio audio (`- Topic` channels, `Official Audio`, duration matches) wins
  while story-driven music videos, lives, covers, slowed/8d edits, reactions
  and Shorts sink. Explicit user intent (`--live`, `--remix`, `--cover`,
  `--instrumental`) overrides the penalties. Every decision is explained in
  the UI with a per-candidate scoring trail.
- **SponsorBlock Studio Cut** - native yt-dlp `SponsorBlock` + `ModifyChapters`
  postprocessors (strictly before `FFmpegExtractAudio`) automatically remove
  non-music segments: `music_offtopic`, `sponsor`, `intro`, `outro`,
  `selfpromo`. Configurable categories and keyframe precision.
- **Synced Karaoke Lyrics Engine (LRCLIB)** - polite client for the free
  lrclib.net API (proper `User-Agent`, 350 ms rate limit), exact `/api/get`
  lookup with fuzzy `/api/search` fallback, duration-aware matching and
  preference for synced lyrics. Embeds `USLT` + `SYLT` (MP3), `LYRICS` /
  `SYNCEDLYRICS` (FLAC/Opus/OGG), `\xa9lyr` (M4A) via mutagen and saves a
  paired `.lrc` file for players and karaoke.
- **Smart Artwork Cropper + Metadata Enricher** - 16:9 YouTube thumbnails
  with black bars are auto-cropped to perfect 1:1 covers (default 1000x1000)
  via Pillow; metadata (album, year, genre, track number, clean 1000x1000
  artwork) is enriched through the iTunes Search API with a MusicBrainz
  fallback and a cleaned-source-tags last resort.
- **EBU R128 Normalization & Multi-Codec Profiles** - one-click quality
  presets (Opus 160k transparent, MP3 320k CBR, M4A AAC 256k, FLAC lossless)
  plus optional two-pass ffmpeg `loudnorm` (I=-14 LUFS, TP=-1.5, LRA=11) so
  every track in a playlist plays at the same loudness.
- **Smart Dedup, Watchlist Sync & M3U8 Playlists** - unique index by
  `source_id` plus fuzzy `normalized artist + title + duration` matching so
  duplicates are never re-downloaded; subscribe to playlists/channels and
  `melodine sync` pulls only the new tracks, organizing them with templates
  like `{artist}/{album}/{track_num} - {title}.{ext}` and refreshing local
  `.m3u8` playlist files.

### Added - platform

- Dual UX: a premium interactive TUI (dashboard, live Anti-MV search,
  download queue with per-track progress bars, speed and ETA, history and
  library, watchlist screen, lyrics tool, doctor, export, settings) and a
  fully headless CLI (`melodine get | sync | lyrics | doctor | export`,
  `watchlist add/list/remove`) plus the short `mld` alias.
- Live theme (12 themes incl. all 7 v1 themes) and RU/EN language switching
  via hotkeys (`t` / `g`) with 100% translation parity enforced by tests.
- Non-blocking rotating file logger - yt-dlp and ffmpeg chatter can never
  corrupt the TUI rendering.
- Graceful shutdown (Ctrl+C / SIGTERM) with queue-state persistence and
  resume-on-start.
- `melodine doctor` environment diagnostics (ffmpeg/ffprobe, yt-dlp,
  database integrity, broken file paths, network reachability).
- `melodine export` to M3U8 / JSON for the library or the download history.
- CI: ruff + pytest matrix on Linux/Windows for Python 3.10-3.13.
- 201 automated tests covering scoring, title parsing, LRCLIB client,
  artwork cropping, SQLite migrations, locale parity and CLI commands.

### Changed

- Packaging migrated from `setup.py` to `pyproject.toml` (PEP 621,
  hatchling) with `melodine` + `mld` console scripts (v1's broken
  `melodine=main:main` entry point is fixed).
- Layered architecture: `core` (config/logging/shutdown), `db`, `services`,
  `i18n`, `ui`, `cli`; strict type hints throughout; `py.typed` marker.
- `config.yaml` is fully backward compatible - v1 files migrate on load
  (`paths.*`, `download.quality`, `metadata.add_tags`,
  `metadata.download_covers` are mapped transparently).

### Migrated

- SQLite databases are migrated in place: v1 `downloads`/`sessions` rows
  survive, new tables (`tracks`, `watchlist`, `watchlist_items`,
  `queue_state`) are added, and successful v1 downloads are backfilled into
  the dedup-aware library.

## [1.0.0]

- Initial release: playlist-driven downloader with Smart Search, auto-retry,
  ID3 tagging, statistics, 7 themes and RU/EN localization.
