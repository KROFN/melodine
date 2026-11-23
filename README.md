<div align="center">

```
  ♫ ♪ ♫ ♪ ♫
  __  __      _           _ _
 |  \/  | ___| | ___   __| (_)_ __   ___
 | |\/| |/ _ \ |/ _ \ / _` | | '_ \ / _ \
 | |  | |  __/ | (_) | (_| | | | | |  __/
 |_|  |_|\___|_|\___/ \__,_|_|_| |_|\___|
```

**Your playlist. Downloaded. Beautifully. — Studio-grade music downloader for the terminal.**

[![CI](https://github.com/KROFN/melodine/actions/workflows/ci.yml/badge.svg)](https://github.com/KROFN/melodine/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/Python-3.10%20%7C%203.11%20%7C%203.12%20%7C%203.13-3776AB?style=flat&logo=python&logoColor=white)](https://python.org)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![Tests](https://img.shields.io/badge/tests-201%20passed-brightgreen)]()
[![License](https://img.shields.io/badge/License-MIT-green)](LICENSE)
[![Platforms](https://img.shields.io/badge/platform-Linux%20%7C%20Windows%20%7C%20macOS-lightgrey)]()

[English](#english) · [Русский](#русский)

</div>

---

## English

**Melodine v2** downloads music from YouTube the way a self-respecting music hoarder wants it:
**studio audio instead of music videos**, non-music segments cut out, **synced karaoke lyrics**,
square high-res covers, correct album/year/genre tags, one-click codec presets and optional
**EBU R128 loudness normalization** — through a premium TUI *or* a fast headless CLI.

### Why Melodine?

| Feature | Melodine v2 | raw yt-dlp | spotDL | ytmdl |
|---|:---:|:---:|:---:|:---:|
| Anti-MV studio scoring (picks `- Topic` / `Official Audio`) | ✔ | – | partial | partial |
| SponsorBlock cut of intros/skits/outros | ✔ | manual flags | – | – |
| Synced karaoke `.lrc` (LRCLIB) embedded + sidecar | ✔ | – | – | plain only |
| 16:9 → 1:1 smart artwork cropping | ✔ | – | ✔ | ✔ |
| iTunes / MusicBrainz metadata enrichment | ✔ | – | Spotify | ✔ |
| EBU R128 two-pass loudness normalization | ✔ | manual | – | – |
| Opus / MP3 / M4A / FLAC profiles in one click | ✔ | manual | ✔ | ✔ |
| Smart dedup (source_id + fuzzy artist/title/duration) | ✔ | – | – | – |
| Watchlist subscriptions → M3U8 playlists | ✔ | – | – | – |
| Beautiful TUI with 12 themes + RU/EN hotkeys | ✔ | – | – | – |
| Headless CLI (`get/sync/lyrics/doctor/export`) | ✔ | CLI only | CLI | CLI |

### The six killer features

1. **Anti-MV Studio Scorer.** Every search candidate is scored 0–100. Official audio
   channels (`Artist - Topic`), `Official Audio` uploads and duration matches rise to the top;
   story-driven music videos, lives, covers, `slowed + reverb`, 8D, reactions and Shorts sink —
   unless you explicitly ask (`--live`, `--remix`, `--cover`, `--instrumental`). The TUI shows
   the full scoring trail for every candidate.
2. **SponsorBlock Studio Cut.** `SponsorBlock` + `ModifyChapters` postprocessors run strictly
   before audio extraction and automatically remove `music_offtopic`, `sponsor`, `intro`,
   `outro` and `selfpromo` segments, so skits and sponsor reads never reach your library.
3. **Synced Karaoke Lyrics (LRCLIB).** Polite client for the free [lrclib.net](https://lrclib.net)
   API: exact lookup, fuzzy fallback, duration filtering, synced preferred over plain. Lyrics are
   embedded as `USLT`/`SYLT` (MP3), `LYRICS`/`SYNCEDLYRICS` (FLAC/Opus) or `©lyr` (M4A) **and**
   saved as a sidecar `.lrc` for players and karaoke nights.
4. **Smart Artwork Cropper + Metadata Enricher.** YouTube's 16:9 thumbnails with black bars are
   auto-cropped to a perfect 1000×1000 cover before embedding. Album, year, genre and track
   number come from the iTunes Search API with a MusicBrainz fallback, falling back to
   cleaned source tags (no more `(Official Video)` in your library).
5. **EBU R128 Normalization & Codec Profiles.** `Opus 160k transparent`, `MP3 320k CBR`,
   `M4A AAC 256k` or `FLAC lossless` in one flag, plus optional two-pass
   `loudnorm=I=-14:TP=-1.5:LRA=11` so the whole playlist plays at one loudness.
6. **Smart Dedup, Watchlist & M3U8.** A unique index (`source_id` + fuzzy
   `normalized artist + title + duration`) never downloads a track twice. Subscribe to a
   playlist or channel, and `melodine sync` pulls only the new tracks into
   `{artist}/{album}/{track_num} - {title}.{ext}` folders and refreshes a local `.m3u8`.

### Architecture

```
┌──────────────────────────────────────────────────────────────────────────┐
│                            UX  (dual mode)                               │
│  melodine ─ TUI (rich): dashboard │ search │ queue │ library │ settings  │
│  mld ────── CLI (typer): get │ sync │ lyrics │ doctor │ export │ watch   │
└───────────────┬──────────────────────────────────┬───────────────────────┘
                │                                  │
┌───────────────▼──────────────┐   ┌───────────────▼───────────────────────┐
│           core               │   │              services                 │
│  config (pydantic, v1↔v2)    │   │  search + Anti-MV scoring             │
│  logging (queue → rotate)    │   │  downloader (yt-dlp pipeline)         │
│  shutdown (graceful Ctrl+C)  │   │   ├─ SponsorBlock + ModifyChapters    │
└───────────────┬──────────────┘   │   ├─ FFmpegExtractAudio (codecs)      │
                │                  │   ├─ loudnorm (EBU R128, 2-pass)      │
┌───────────────▼──────────────┐   │   ├─ artwork cropper (Pillow 1:1)    │
│            db                │   │   ├─ tagger (mutagen USLT/SYLT/…)    │
│  tracks (dedup index)        │   │   └─ lyrics (LRCLIB client)          │
│  history (v1 compatible)     │   │  metadata (iTunes → MusicBrainz)     │
│  watchlist + queue_state     │   │  watchlist sync → M3U8 │ doctor │ export │
└──────────────────────────────┘   └───────────────────────────────────────┘
```

### Quick start

**Requirements:** Python 3.10+ and FFmpeg (`winget install FFmpeg` / `sudo apt install ffmpeg` / `brew install ffmpeg`).

```bash
# uvx (recommended)
uvx melodine

# pipx
pipx install melodine

# pip
pip install melodine
```

Run `melodine` with no arguments for the interactive TUI, or use the headless CLI:

```bash
melodine get "Daft Punk - Around the World"     # search → best studio audio → full pipeline
melodine get "https://youtu.be/…"               # direct URL
melodine get my_playlist.txt                    # batch: dirty .txt playlists still welcome
melodine get "Muse - Hysteria" --live           # intent: prefer live versions
melodine get "Track" -f opus --normalize        # Opus 160k + EBU R128 normalization
melodine get "Track" -f flac --no-sponsorblock  # lossless, keep all segments

melodine watchlist add "https://www.youtube.com/playlist?list=…" --name "Daily Mix"
melodine sync                                   # pull only the new tracks → M3U8

melodine lyrics ~/Music                         # backfill synced .lrc for a whole folder
melodine doctor                                 # ffmpeg / yt-dlp / DB / network diagnostics
melodine export -f m3u8 --scope library         # export library or history
```

Short alias: `mld get "…"` works everywhere.

### TUI hotkeys & screens

| Key | Action | Screens |
|---|---|---|
| `t` | cycle theme (12 themes) | anywhere in the menu |
| `g` | toggle RU / EN interface | anywhere in the menu |
| `q` | quit (graceful, saves queue) | anywhere in the menu |
| `1`–`9`, `0` | search / playlist / queue / history / watchlist / lyrics / doctor / export / settings / exit | menu |
| `Ctrl+C` | interrupt downloads → cancel remaining & persist queue for resume | queue screen |

### Configuration

`config.yaml` is created on first run and is **fully backward compatible with v1**.
Every v1 option keeps working; new sections unlock the v2 features:

```yaml
theme: dracula          # 12 themes: dracula, dark, nord, monokai, ocean,
language: ru            # cyberpunk, pastel, daybreak, forest, sakura, terminal, gruvbox

audio:
  codec: mp3            # opus | mp3 | m4a | flac
  bitrate: 320
  normalize: false      # EBU R128 two-pass loudnorm
  target_lufs: -14.0
  true_peak: -1.5
  lra: 11

sponsorblock:
  enabled: true
  categories: [music_offtopic, sponsor, intro, outro, selfpromo]
  force_keyframes: true

lyrics:
  enabled: true
  synced: true
  save_lrc: true
  rate_limit_ms: 350

artwork:
  embed: true
  crop: true            # 16:9 → 1:1 smart crop
  size: 1000

metadata:
  enrich: true          # iTunes → MusicBrainz
  providers: [itunes, musicbrainz]

output:
  folder: ./downloads
  template: "{artist}/{album}/{track_num} - {title}.{ext}"

search:
  anti_mv: true         # Anti-MV Studio Scorer
  results: 10
  min_score: 50
  duration_tolerance: 3
```

### Development

```bash
git clone https://github.com/KROFN/melodine.git && cd melodine
pip install -e ".[dev]"
pytest            # 201 tests
ruff check .      # lint
```

<details>
<summary><b>Project layout</b></summary>

```
melodine/
├── core/       config (pydantic + v1 migration), logging, shutdown, exceptions
├── db/         SQLite: tracks (dedup), history (v1), watchlist, queue_state
├── services/   scoring, search, titles, dedup, lrclib, tagger, artwork,
│               metadata, downloader, normalize, playlists, doctor, exporter
├── i18n/       RU/EN catalog with test-enforced parity
├── ui/         12 themes + rich widgets (progress, score bars, tables)
└── cli/        typer CLI + the interactive TUI
tests/          201 tests (all offline, providers mocked)
```

</details>

---

## Русский

**Melodine v2** скачивает музыку с YouTube так, как этого хочет настоящий меломан:
**студийное звучание вместо клипов**, вырезанные немузыкальные вставки, **синхронизированный
караоке-текст**, квадратные обложки высокого разрешения, правильные теги (альбом/год/жанр),
пресеты кодеков в один клик и опциональная **нормализация громкости EBU R128** — через
роскошный TUI или быстрый headless-CLI.

### Шесть киллер-фич

1. **Anti-MV Studio Scorer.** Каждый кандидат в поиске получает скор 0–100: официальные
   аудио-каналы (`Artist - Topic`), `Official Audio` и совпадения длительности поднимаются
   наверх, а клипы с сюжетом, лайвы, каверы, `slowed + reverb`, 8D, реакции и Shorts тонут —
   если вы сами явно не попросили (`--live`, `--remix`, `--cover`, `--instrumental`). TUI
   показывает полную расшифровку скоринга для каждого кандидата.
2. **SponsorBlock Studio Cut.** Постпроцессоры `SponsorBlock` + `ModifyChapters` работают
   строго до извлечения аудио и автоматически вырезают `music_offtopic`, `sponsor`, `intro`,
   `outro` и `selfpromo` — скиты и реклама больше не попадут в вашу медиатеку.
3. **Синхронизированный караоке-текст (LRCLIB).** Вежливый клиент бесплатного API
   [lrclib.net](https://lrclib.net): точный поиск, нечёткий фоллбэк, фильтр по длительности,
   приоритет синхронизированного текста. Текст вшивается в теги (`USLT`/`SYLT` для MP3,
   `LYRICS`/`SYNCEDLYRICS` для FLAC/Opus, `©lyr` для M4A) **и** сохраняется парным файлом
   `.lrc` для плееров и караоке.
4. **Умная обрезка обложек + обогащение метаданных.** Горизонтальные 16:9 превью с чёрными
   полосами автоматически превращаются в идеальный квадрат 1000×1000. Альбом, год, жанр и
   номер трека подтягиваются из iTunes Search API (фоллбэк — MusicBrainz), а при недоступности
   используются очищенные теги источника — никаких `(Official Video)` в библиотеке.
5. **Нормализация EBU R128 и профили кодеков.** `Opus 160k transparent`, `MP3 320k CBR`,
   `M4A AAC 256k` или `FLAC lossless` одним флагом, плюс опциональный двухпроходный
   `loudnorm=I=-14:TP=-1.5:LRA=11` — весь плейлист играет на одной громкости.
6. **Умный дедуп, вотчлист и M3U8.** Уникальный индекс (`source_id` + нечёткое совпадение
   `артист + название + длительность`) никогда не качает дубликаты. Подпишитесь на плейлист
   или канал — `melodine sync` докачает только новые треки в папки по шаблону
   `{artist}/{album}/{track_num} - {title}.{ext}` и обновит локальный `.m3u8`.

### Быстрый старт

```bash
# Требуются Python 3.10+ и FFmpeg
uvx melodine            # или: pipx install melodine / pip install melodine
```

```bash
melodine                          # интерактивный TUI
melodine get "ХАННА - Потеряла голову"
melodine get playlist.txt         # пакетная загрузка из грязного .txt
melodine watchlist add "https://www.youtube.com/playlist?list=…" --name "Мой микс"
melodine sync                     # только новые треки + M3U8
melodine lyrics ~/Музыка          # докачка синхронизированных текстов
melodine doctor                   # диагностика окружения
melodine export -f json           # экспорт библиотеки
```

Горячие клавиши TUI: `t` — смена темы, `g` — переключение RU/EN, `q` — выход,
`Ctrl+C` — мягкая остановка загрузок с сохранением очереди.

### Совместимость

- `config.yaml` v1 загружается без изменений (старые ключи `paths.*`,
  `download.quality`, `metadata.add_tags` мигрируют автоматически).
- База данных v1 мигрирует на месте: история `downloads`/`sessions` сохраняется,
  успешные загрузки попадают в новую дедуплицированную медиатеку.
- Все 7 тем v1 на месте, плюс 5 новых: daybreak, forest, sakura, terminal, gruvbox.

---

<div align="center">

**Built with** [yt-dlp](https://github.com/yt-dlp/yt-dlp) · [rich](https://github.com/Textualize/rich) ·
[typer](https://typer.tiangolo.com) · [pydantic](https://docs.pydantic.dev) ·
[mutagen](https://github.com/quodlibet/mutagen) · [Pillow](https://python-pillow.org) ·
data from [LRCLIB](https://lrclib.net) · [SponsorBlock](https://sponsor.ajay.app) ·
[iTunes Search](https://developer.apple.com/library/archive/documentation/AudioVideo/Conceptual/iTuneSearchAPI/) · [MusicBrainz](https://musicbrainz.org)

### License — MIT © KROFN

⭐ **Star this repo if you find it useful** ⭐

</div>
