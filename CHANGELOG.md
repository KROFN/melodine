# Changelog

All notable changes to Melodine are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and the project adheres to [Semantic Versioning](https://semver.org/).

## [2.1.0] - Interactive experience and smarter source selection

### Added

- Compact keyboard-driven workspace for modern terminals, with a classic
  console fallback, bilingual onboarding, codec explanations, theme previews
  and a repeatable quick-start guide.
- Dismissible Windows Terminal recommendation and regional connectivity guidance.
- Channel verification and artist matching in the scorer, conservative
  cross-script title matching and corroborated artist-name typo handling.
- Score explanations including the base score, individual signals and final score.
- Explicit download pipeline stages, from source lookup through tagging and
  library persistence.

### Fixed

- Unrelated tracks cannot collect source, artist or duration bonuses when the
  requested track title has insufficient matching evidence. Smart Search
  retries mismatches; automatic selection rejects unresolved mismatches while
  manual result selection remains available.
- Explicit CLI result indexes use a single ranked result set and reject invalid
  indexes rather than silently choosing another result.
- Configured bitrates are respected; a different codec uses its own default
  bitrate unless explicitly overridden.
- Output folder changes show the resolved path, require confirmation and check
  write access before saving.
- Cross-platform offline tests allow the standard library's internal socketpair
  while continuing to block arbitrary network connections.

## [2.0.1] - Review patch: correctness & release hardening

Targeted fixes from the external PR review — no new features, only
correctness, honesty and release readiness.

### Fixed

- **Distribution name**: PyPI's `melodine` belongs to an unrelated project,
  so the distribution is renamed to `krofn-melodine` (import package and
  the `melodine`/`mld` commands are unchanged). README now installs from
  GitHub and warns against `pip install melodine`.
- **SponsorBlock pipeline staged like upstream yt-dlp**: `SponsorBlock` now
  collects segments at `after_filter` (before the download), and
  `ModifyChapters` runs *after* `FFmpegExtractAudio` in the default
  `post_process` phase — it edits `info['filepath']`, so it needs the
  extracted file. The old `pre_process` staging cut nothing real. Tests
  that asserted the old (wrong) order were rewritten against the upstream
  semantics.
- **Ctrl+C → resume no longer loses queued tasks**: `cancel_and_persist()`
  persisted only futures with `not future.done()`, but `Future.cancel()`
  flips queued futures to done instantly — cancelled queued tasks silently
  vanished. Persistence now keys on task results (`success`/`skipped` are
  done, everything else — running, cancelled, failed — is saved). The TUI
  SIGINT handler no longer kills the pool before asking the user; declining
  the stop prompt resets the interrupt flag and keeps downloading. New
  `melodine get --resume` continues a persisted queue.
- **CLI flags now apply to `.txt` batch runs**: `-f/--bitrate/--normalize/
  --no-sponsorblock/--folder/...` were silently dropped for playlists.
- **A missing `.txt` fails fast offline** instead of being treated as a
  search query that would hit YouTube.
- **Scorer: intent no longer short-circuits penalties**: `--live` on
  "LIVE COVER REACTION" used to collect the live bonus while skipping the
  cover/reaction penalties. Each penalty is now waived only by its own
  matching intent.
- **Dedup is variant-aware**: "Song" vs "Song (Live/Remix/Cover)" are
  different recordings and are never merged; remaster/radio-edit/version
  keep the studio identity.
- **LRCLIB**: a synced fuzzy match (within duration tolerance) now beats a
  plain-only exact hit; the 350 ms rate limit is enforced with a lock so it
  holds globally across DownloadPool worker threads.
- **v1 `download.retry_delay`** is honored again via yt-dlp
  `retry_sleep_functions`.

### Added

- Real CI at `.github/workflows/ci.yml` (ruff + pytest matrix, Linux and
  Windows, Python 3.10–3.13; the previous file sat at
  `.github/ci.workflow.example.yml` and never ran).
- Offline guarantee is now enforced, not promised: `tests/conftest.py`
  installs a socket guard that fails any test attempting a real network
  connection (`MELODINE_TEST_ALLOW_NETWORK=1` opts out for live smoke).
- Regression tests for every fix above (232 total, all offline).

### Changed

- Honest FLAC wording: a lossless container for already-lossy YouTube
  audio; it cannot restore what the source threw away.
- Honest compatibility statement: v1 *config and data* migrate in place;
  the v1 internal Python API (`melodine.config/database/downloader/search`)
  is gone — CLI/TUI are the supported interface.

## [2.0.0] - Flagship Overhaul / Флагманский релиз

### Added - six killer features / Шесть киллер-фич

- **Anti-MV Studio Scorer** - search results are ranked 0-100 so official
  studio audio (`- Topic` channels, `Official Audio`, duration matches) wins
  while story-driven music videos, lives, covers, slowed/8d edits, reactions
  and Shorts sink. Explicit user intent (`--live`, `--remix`, `--cover`,
  `--instrumental`) overrides the penalties. Every decision is explained in
  the UI with a per-candidate scoring trail.
- **SponsorBlock Studio Cut** - native yt-dlp `SponsorBlock` + `ModifyChapters`
  postprocessors (staged like the upstream CLI; see the 2.0.1 fix below)
  automatically remove non-music segments: `music_offtopic`, `sponsor`, `intro`, `outro`,
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
- Automated tests covering scoring, title parsing, LRCLIB client,
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
