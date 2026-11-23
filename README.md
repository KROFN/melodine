<div align="center">

# 🎵 Melodine

**A studio-first YouTube music downloader for people who want a clean local library.**

Melodine searches for the right audio, downloads it, cleans the metadata, embeds artwork and lyrics,
and keeps the result organized — through an interactive TUI or a scriptable CLI.

[![CI](https://github.com/KROFN/melodine/actions/workflows/ci.yml/badge.svg)](https://github.com/KROFN/melodine/actions/workflows/ci.yml)
[![Latest release](https://img.shields.io/github/v/release/KROFN/melodine?label=release)](https://github.com/KROFN/melodine/releases/latest)
[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![License](https://img.shields.io/github/license/KROFN/melodine)](LICENSE)

[Install](#installation) · [Usage](#usage) · [Configuration](#configuration) · [Русский](#русский)

</div>

---

## What Melodine does

Melodine is built on top of [yt-dlp](https://github.com/yt-dlp/yt-dlp), but its job is not merely
to turn a YouTube URL into an audio file. It tries to produce something you can actually keep in a
music library.

- **Studio-first search.** An Anti-MV scorer prefers `Artist - Topic`, official audio and
  duration matches, while pushing music videos, reactions, Shorts, covers and alternate mixes down
  unless you explicitly request them.
- **Cleaner tracks with SponsorBlock.** Optional SponsorBlock integration removes configured
  non-music segments after extraction.
- **Synced lyrics.** Fetches lyrics from [LRCLIB](https://lrclib.net), prefers synced results,
  embeds them where the audio format supports it and can save a sidecar `.lrc`.
- **Artwork and metadata.** Cleans YouTube-style titles, crops artwork to a square cover, and can
  enrich album/year/genre/track metadata through iTunes and MusicBrainz.
- **Useful audio profiles.** Opus, MP3, M4A and FLAC output, with optional two-pass EBU R128
  loudness normalization.
- **A persistent local library.** SQLite history, duplicate detection, resumable queues,
  playlist/channel watchlists and generated M3U8 playlists.

> [!NOTE]
> YouTube audio is already lossy. Choosing FLAC avoids another lossy codec step after decoding,
> but it cannot restore information that was not present in the source.

## Installation

### Requirements

- Python **3.10+**
- [FFmpeg](https://ffmpeg.org/download.html) available in `PATH`

### Recommended: pipx

```bash
pipx install "git+https://github.com/KROFN/melodine.git@v2.0.1"
```

Or install into your current Python environment:

```bash
pip install "git+https://github.com/KROFN/melodine.git@v2.0.1"
```

Then launch the interactive interface:

```bash
melodine
```

The short alias `mld` is installed as well.

> [!IMPORTANT]
> The PyPI project named `melodine` belongs to an unrelated project. Melodine's distribution
> name is `krofn-melodine`; until it is published there, install this project from GitHub as shown
> above.

## Usage

### Download a track

```bash
melodine get "Daft Punk - Around the World"
```

Useful variants:

```bash
melodine get "Muse - Hysteria" --live
melodine get "Track" --remix
melodine get "Track" -f opus --normalize
melodine get "https://youtu.be/..." --no-sponsorblock
```

### Download a text playlist

Melodine keeps the permissive text-playlist workflow from v1:

```text
Daft Punk - Around the World
Muse — Hysteria
Massive Attack - Teardrop
```

```bash
melodine get playlist.txt
```

CLI options also apply to batch runs:

```bash
melodine get playlist.txt -f opus --normalize --no-sponsorblock
```

If a batch is interrupted, the unfinished queue can be resumed:

```bash
melodine get --resume
```

### Watchlists and library tools

```bash
# Subscribe to a playlist or channel
melodine watchlist add "https://www.youtube.com/playlist?list=..." --name "Daily mix"

# Download only newly discovered tracks and refresh the M3U8 playlist
melodine sync

# Backfill lyrics for an existing music folder
melodine lyrics ~/Music

# Check FFmpeg, yt-dlp, the database and connectivity
melodine doctor

# Export the local library
melodine export -f m3u8 --scope library
melodine export -f json
```

Run `melodine <command> --help` for the full option list.

## TUI and headless CLI

Running `melodine` without a subcommand opens the interactive TUI. The same core services are
available from the headless CLI, so the project works both as an everyday terminal app and in scripts.

| TUI | CLI |
|---|---|
| Search with candidate scores and badges | `melodine get ...` |
| Live download queue | batch `.txt` downloads |
| Library and history | `export`, `doctor` |
| Watchlist manager | `watchlist`, `sync` |
| Lyrics tool | `lyrics <folder>` |
| 12 themes, RU/EN UI | script-friendly exit codes |

TUI shortcuts: `t` changes theme, `g` switches RU/EN, `q` exits, and `Ctrl+C` performs a
cooperative stop with queue persistence.

## How track selection works

For search queries, Melodine asks yt-dlp for multiple candidates and scores them before downloading.

Positive signals include:

- `Artist - Topic` channels;
- `Official Audio`;
- title similarity;
- expected duration.

Negative signals include music videos, reactions, Shorts, live versions, covers, remixes and
slowed/sped variants. Intent flags such as `--live`, `--remix`, `--cover` and
`--instrumental` waive the corresponding penalty without disabling unrelated penalties.

The scorer is intentionally heuristic: if you need an exact upload, pass its URL directly.

## Audio, tags and lyrics

| Area | Behaviour |
|---|---|
| Audio | Opus, MP3, M4A/AAC and FLAC output profiles |
| Loudness | optional two-pass FFmpeg `loudnorm` targeting EBU R128-style playback consistency |
| Lyrics | LRCLIB exact lookup + fuzzy fallback, synced lyrics preferred |
| Artwork | provider artwork first; YouTube thumbnails can be cropped to a square |
| Metadata | cleaned source metadata with optional iTunes → MusicBrainz enrichment |
| Dedup | source ID plus normalized artist/title/duration and variant-aware checks |

## Configuration

On first run Melodine creates `config.yaml`. Most users can start with the defaults and change
settings from the TUI.

A compact example:

```yaml
language: ru
theme: dracula

audio:
  codec: mp3
  bitrate: 320
  normalize: false

sponsorblock:
  enabled: true
  categories: [music_offtopic, sponsor, intro, outro, selfpromo]

lyrics:
  enabled: true
  synced: true
  save_lrc: true

metadata:
  enrich: true

output:
  folder: ./downloads
  template: "{artist}/{album}/{track_num} - {title}.{ext}"

search:
  anti_mv: true
  results: 10
  min_score: 50
```

## Upgrading from v1

Melodine v2 keeps the user-facing v1 data path intact:

- v1 `config.yaml` values are migrated into the v2 configuration model;
- the SQLite database is migrated in place and existing history is preserved;
- all seven original themes remain available;
- `python main.py` remains as a compatibility launcher.

The **internal Python API changed** substantially in v2. The supported interfaces are the
`melodine` / `mld` CLI and TUI.

Before upgrading an important library, keeping a backup of `config.yaml` and `melodine.db` is
still a sensible precaution.

## Development

```bash
git clone https://github.com/KROFN/melodine.git
cd melodine

pip install -e ".[dev]"
pytest
ruff check .
```

The test suite blocks accidental real network access by default; live smoke tests can opt out with
`MELODINE_TEST_ALLOW_NETWORK=1`.

Project structure:

```text
melodine/
├── core/       configuration, logging, shutdown
├── db/         SQLite library, history, watchlists, queue state
├── services/   search, scoring, download, metadata, lyrics, tagging, export
├── i18n/       Russian and English locale catalog
├── ui/         Rich themes and widgets
└── cli/        Typer CLI and interactive TUI
```

## Русский

<details>
<summary><strong>Краткая справка на русском</strong></summary>

Melodine — терминальный загрузчик музыки с YouTube, который пытается получить не случайный первый
ролик, а нормальный трек для локальной медиатеки: предпочитает официальное аудио, умеет вырезать
немузыкальные сегменты через SponsorBlock, подтягивает синхронизированные тексты LRCLIB, чистит
метаданные и обложки, поддерживает несколько аудиоформатов и ведёт локальную SQLite-библиотеку.

Для установки нужны Python 3.10+ и FFmpeg:

```bash
pipx install "git+https://github.com/KROFN/melodine.git@v2.0.1"
melodine
```

Основные команды:

```bash
melodine get "Исполнитель - Трек"
melodine get playlist.txt
melodine get --resume
melodine watchlist add "URL" --name "Мой плейлист"
melodine sync
melodine lyrics ~/Music
melodine doctor
```

Запуск без аргументов открывает TUI. `t` меняет тему, `g` переключает русский/английский,
`Ctrl+C` мягко останавливает загрузку и сохраняет незавершённую очередь.

</details>

## Credits

Melodine is built with [yt-dlp](https://github.com/yt-dlp/yt-dlp),
[Rich](https://github.com/Textualize/rich), [Typer](https://typer.tiangolo.com/),
[Pydantic](https://docs.pydantic.dev/), [Mutagen](https://github.com/quodlibet/mutagen) and
[Pillow](https://python-pillow.org/).

It integrates data or services from [SponsorBlock](https://sponsor.ajay.app/),
[LRCLIB](https://lrclib.net/), [MusicBrainz](https://musicbrainz.org/) and the
[iTunes Search API](https://developer.apple.com/library/archive/documentation/AudioVideo/Conceptual/iTuneSearchAPI/).

## License

[MIT](LICENSE) © KROFN
