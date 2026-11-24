<div align="center">

# 🎵 Melodine

**Studio-first YouTube music downloader for a clean local library.**

Search the right upload, extract the audio, clean the junk, enrich the tags, attach artwork and lyrics,
and keep the result organized — from an interactive TUI or a scriptable CLI.

[![CI](https://github.com/KROFN/melodine/actions/workflows/ci.yml/badge.svg)](https://github.com/KROFN/melodine/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/KROFN/melodine?label=release)](https://github.com/KROFN/melodine/releases/latest)
[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![License](https://img.shields.io/github/license/KROFN/melodine)](LICENSE)

**English** · [Русский](README.ru.md)

[Quick start](#quick-start) · [Features](#features) · [Recipes](#recipes) · [Configuration](#configuration) · [Releases](https://github.com/KROFN/melodine/releases)

</div>

---

## ✦ Why Melodine

Melodine is built on [yt-dlp](https://github.com/yt-dlp/yt-dlp), but it is intentionally more opinionated.
Its job is not just to turn a YouTube URL into an audio file — it tries to produce a track you can actually
keep in a music library.

```mermaid
flowchart LR
    A["Query or URL"] --> B["Search + score"]
    B --> C["Extract audio"]
    C --> D["Cut non-music segments"]
    D --> E["Metadata + artwork"]
    E --> F["Lyrics + tags"]
    F --> G["Local library"]
```

If you need a universal video/audio downloader with maximum control over YouTube itself, use yt-dlp
directly. Melodine deliberately trades some generality for a music-library workflow.

## ⚡ Quick start

**Requirements:** Python 3.10+ and [FFmpeg](https://ffmpeg.org/download.html) available in `PATH`.

**Windows:** We recommend [Windows Terminal](https://learn.microsoft.com/en-us/windows/terminal/install) for the full color palette and modern terminal rendering. Use either CMD or PowerShell inside it. The classic Windows console remains supported in compact mode.

**Network:** YouTube availability varies by region. If requests time out, check connectivity on the same device, including firewall and existing VPN/proxy settings. Melodine does not manage network restrictions.

```bash
pipx install git+https://github.com/KROFN/melodine.git@v2.1.0
melodine
```

Running `melodine` without arguments opens the TUI. The short alias `mld` is installed too.

<details>
<summary><strong>Other install methods</strong></summary>

With regular `pip`:

```bash
pip install git+https://github.com/KROFN/melodine.git@v2.1.0
```

One-off run with `uvx`:

```bash
uvx --from git+https://github.com/KROFN/melodine.git@v2.1.0 melodine
```

</details>

> [!IMPORTANT]
> The PyPI project named `melodine` belongs to an unrelated project. This project uses the
> distribution name `krofn-melodine`; until it is published on PyPI, install it from GitHub.

## ✦ Features

| | |
|---|---|
| **🎯 Source selection**<br>Anti-MV candidate scoring<br>`Artist - Topic` / `Official Audio` preference<br>title + duration signals<br>`--live`, `--remix`, `--cover`, `--instrumental` | **🧹 Cleanup**<br>SponsorBlock segment removal<br>YouTube-title cleanup<br>square artwork processing<br>optional EBU R128 normalization |
| **🎼 Library**<br>LRCLIB synced `.lrc` lyrics<br>iTunes → MusicBrainz enrichment<br>variant-aware dedup<br>SQLite history, watchlists, M3U8 | **⌨️ Interface**<br>Rich TUI + Typer CLI<br>12 themes, RU / EN UI<br>graceful Ctrl+C<br>persistent queue + `--resume` |

> [!NOTE]
> YouTube audio is already lossy. FLAC output avoids another lossy codec step after decoding,
> but it cannot restore information that was not present in the source.

<!-- Real TUI / CLI screenshots can be inserted here later without changing the README structure. -->

## ⌘ Recipes

### Download one track

```bash
melodine get "Daft Punk - Around the World"
```

<details>
<summary><strong>Versions, formats and direct URLs</strong></summary>

```bash
melodine get "Muse - Hysteria" --live
melodine get "Track" --remix
melodine get "Track" -f opus --normalize
melodine get "https://youtu.be/..." --no-sponsorblock
```

If you need one exact upload instead of heuristic selection, pass its URL directly.

</details>

<details>
<summary><strong>Batch download from a .txt playlist</strong></summary>

```text
Daft Punk - Around the World
Muse — Hysteria
Massive Attack - Teardrop
```

```bash
melodine get playlist.txt
melodine get playlist.txt -f opus --normalize --no-sponsorblock
```

Interrupted batch? Resume the unfinished queue:

```bash
melodine get --resume
```

</details>

<details>
<summary><strong>Watchlists, lyrics and export</strong></summary>

```bash
melodine watchlist add "https://www.youtube.com/playlist?list=..." --name "Daily mix"
melodine sync

melodine lyrics ~/Music
melodine doctor

melodine export -f m3u8 --scope library
melodine export -f json
```

</details>

For every option, run `melodine <command> --help`.

## TUI ↔ CLI

| Interactive TUI | Headless CLI |
|---|---|
| scored search with badges | `melodine get ...` |
| live download queue | batch `.txt` downloads |
| library and history | `export`, `doctor` |
| watchlist manager | `watchlist`, `sync` |
| lyrics tool | `lyrics <folder>` |
| 12 themes and RU/EN | script-friendly exit codes |

TUI shortcuts: `t` changes theme, `g` switches RU/EN, `q` exits, and `Ctrl+C` performs a
cooperative stop while preserving unfinished queue state.

## How track selection works

For text queries, Melodine asks yt-dlp for multiple candidates and ranks them before downloading.

**Positive signals:** `Artist - Topic`, `Official Audio`, title similarity and expected duration.

**Penalties:** music videos, reactions, Shorts, live versions, covers, remixes, slowed/sped and
other alternate versions. An intent flag only waives the matching penalty — for example, `--live`
does not disable the penalty for a reaction video.

The scorer is deliberately heuristic. For absolute control, use a direct URL.

## Audio, tags and lyrics

| Area | Behaviour |
|---|---|
| Audio | Opus, MP3, M4A/AAC and FLAC output profiles |
| Loudness | optional two-pass FFmpeg `loudnorm` |
| Lyrics | LRCLIB exact lookup + fuzzy fallback, synced results preferred |
| Artwork | provider artwork first; YouTube thumbnails can be cropped to a square |
| Metadata | cleaned source metadata with optional iTunes → MusicBrainz enrichment |
| Dedup | source ID + normalized artist/title/duration + variant-aware checks |

## Configuration

Melodine creates `config.yaml` on first run. The defaults are enough to start; most common options
can also be changed from the TUI.

<details>
<summary><strong>Minimal config example</strong></summary>

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

</details>

## Upgrading from v1

- v1 `config.yaml` values are migrated into the v2 configuration model;
- the SQLite database is migrated in place and existing history is preserved;
- all seven original themes remain available;
- `python main.py` remains as a compatibility launcher.

The **internal Python API changed** substantially in v2. The supported user interfaces are the
`melodine` / `mld` CLI and TUI.

For an important existing library, back up `config.yaml` and `melodine.db` before the first v2 run.

## Development

```bash
git clone https://github.com/KROFN/melodine.git
cd melodine
pip install -e ".[dev]"
pytest
ruff check .
```

The test suite blocks accidental real network access by default. For manual live smoke tests, set
`MELODINE_TEST_ALLOW_NETWORK=1`.

<details>
<summary><strong>Project layout</strong></summary>

```text
melodine/
├── core/       configuration, logging, shutdown
├── db/         SQLite library, history, watchlists, queue state
├── services/   search, scoring, download, metadata, lyrics, tagging, export
├── i18n/       Russian and English locale catalog
├── ui/         Rich themes and widgets
└── cli/        Typer CLI and interactive TUI
```

</details>

## Project links

- [Latest release](https://github.com/KROFN/melodine/releases/latest)
- [Changelog](CHANGELOG.md)
- [Issues](https://github.com/KROFN/melodine/issues)
- [v2 overhaul / PR #2](https://github.com/KROFN/melodine/pull/2)

## Credits

Melodine is built with [yt-dlp](https://github.com/yt-dlp/yt-dlp),
[Rich](https://github.com/Textualize/rich), [Typer](https://typer.tiangolo.com/),
[Pydantic](https://docs.pydantic.dev/), [Mutagen](https://github.com/quodlibet/mutagen) and
[Pillow](https://python-pillow.org/).

It integrates [SponsorBlock](https://sponsor.ajay.app/), [LRCLIB](https://lrclib.net/),
[MusicBrainz](https://musicbrainz.org/) and the
[iTunes Search API](https://developer.apple.com/library/archive/documentation/AudioVideo/Conceptual/iTuneSearchAPI/).

## License

[MIT](LICENSE) © KROFN
