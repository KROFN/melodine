<div align="center">

```
  ♫ ♪ ♫ ♪ ♫

 __  __      _           _ _            
|  \/  | ___| | ___   __| (_)_ __   ___ 
| |\/| |/ _ \ |/ _ \ / _` | | '_ \ / _ \
| |  | |  __/ | (_) | (_| | | | | |  __/
|_|  |_|\___|_|\___/ \__,_|_|_| |_|\___|

```

**Your playlist. Downloaded. Beautifully.**

[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![License](https://img.shields.io/badge/License-MIT-green?style=for-the-badge)](LICENSE)
[![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20Linux%20%7C%20macOS-blue?style=for-the-badge)]()

[English](#english) · [Русский](#русский)

</div>

---

## Русский

### 🎵 Что это?

**Melodine** — интерактивный консольный загрузчик музыки. Скачивает треки из текстового плейлиста, конвертирует в MP3, добавляет теги — всё через красивый TUI-интерфейс.

### ✨ Возможности

| Фича | Описание |
|------|----------|
| 📥 **Скачивание плейлистов** | Многопоточная загрузка из `.txt` файлов |
| 🔍 **Поиск треков** | Поиск с превью — выбирай нужный вариант |
| 🧠 **Smart Search** | Если трек не найден — пробует разные варианты запроса |
| 🔄 **Auto-retry** | Повторные попытки при ошибках соединения |
| 🏷️ **ID3-теги** | Автоматически прописывает артиста и название |
| 📊 **Статистика** | Графики, топ артистов, история загрузок |
| 🎨 **7 тем** | Dracula, Nord, Monokai, Cyberpunk и другие |
| 🌐 **RU / EN** | Полная локализация интерфейса |
| ⏸ **Пауза** | Ctrl+C — пауза, не потеря прогресса |
| 📋 **Умный парсер** | Переваривает номера строк, мусор, разные форматы |

### 📦 Установка

**1. Клонируй репозиторий:**

```bash
git clone https://github.com/KROFN/melodine.git
cd melodine
```

**2. Установи зависимости:**

```bash
pip install -r requirements.txt
```

**3. Установи FFmpeg:**

<details>
<summary><b>Windows</b></summary>

```bash
winget install FFmpeg
```
Или скачай с [ffmpeg.org](https://ffmpeg.org/download.html) и добавь в PATH.

</details>

<details>
<summary><b>Linux</b></summary>

```bash
sudo apt install ffmpeg
```

</details>

<details>
<summary><b>macOS</b></summary>

```bash
brew install ffmpeg
```

</details>

**4. Запусти:**

```bash
python main.py
```

### 📝 Формат плейлиста

Создай `.txt` файл со списком треков. Melodine понимает разные форматы:

```
ХАННА - Потеряла голову
Perfect Pitch, Rocco, L'EXAIS - APT.
SEREBRO — Отпусти меня
```

А также справится с «грязными» файлами:

```
# Мой плейлист
1. ХАННА - Потеряла голову
2) SEREBRO — Отпусти меня
3 Руки Вверх! - Только для тебя

Всего: 3 трека
```

### 🎨 Темы

| Тема | Стиль |
|------|-------|
| 🧛 Dracula | Фиолетовая, тёмная |
| 🌑 Dark | Стандартная тёмная |
| ❄️ Nord | Северная, спокойная |
| 🌈 Monokai | Как в Sublime Text |
| 🌊 Ocean | Синие тона |
| 🔥 Cyberpunk | Неон, яркая |
| 🍦 Pastel | Мягкие цвета |

### ⚙️ Конфигурация

При первом запуске создаётся `config.yaml`. Все параметры настраиваются через меню:

```yaml
theme: dracula
language: ru
download:
  threads: 4
  pause: 0.5
  retry_attempts: 3
  quality: 320
  smart_search: true
```

### 🗂 Структура проекта

```
melodine/
├── main.py              # Точка входа
├── requirements.txt
├── config.yaml          # Создаётся при запуске
├── melodine/
│   ├── app.py           # Главный цикл, меню
│   ├── downloader.py    # Движок скачивания
│   ├── config.py        # Управление конфигом
│   ├── database.py      # SQLite история
│   ├── display.py       # Отрисовка UI (Rich)
│   ├── themes.py        # Цветовые схемы
│   ├── locales.py       # Локализация RU/EN
│   ├── search.py        # Поиск на YouTube
│   ├── tagger.py        # ID3-теги
│   └── utils.py         # Парсер плейлистов, утилиты
```

---

## English

### 🎵 What is it?

**Melodine** is an interactive console music downloader. It downloads tracks from a text playlist, converts to MP3, adds tags — all through a beautiful TUI interface.

### ✨ Features

| Feature | Description |
|---------|-------------|
| 📥 **Playlist download** | Multi-threaded downloading from `.txt` files |
| 🔍 **Track search** | Search with preview — pick the right one |
| 🧠 **Smart Search** | Tries different query variations if track not found |
| 🔄 **Auto-retry** | Automatic retries on connection errors |
| 🏷️ **ID3 tags** | Automatically sets artist and title |
| 📊 **Statistics** | Charts, top artists, download history |
| 🎨 **7 themes** | Dracula, Nord, Monokai, Cyberpunk and more |
| 🌐 **RU / EN** | Full interface localization |
| ⏸ **Pause** | Ctrl+C — pause, not lose progress |
| 📋 **Smart parser** | Handles line numbers, junk lines, various formats |

### 📦 Installation

```bash
git clone https://github.com/KROFN/melodine.git
cd melodine
pip install -r requirements.txt
python main.py
```

> ⚠️ **FFmpeg required.** Install: `winget install FFmpeg` (Win) / `sudo apt install ffmpeg` (Linux) / `brew install ffmpeg` (Mac)

### 📝 Playlist format

```
Artist - Song Title
Another Artist — Another Song
```

### ⚙️ Configuration

All settings are configurable through the interactive menu. Config is stored in `config.yaml`.

---

<div align="center">

### 📄 License

MIT © KROFN

---

⭐ **Star this repo if you find it useful!** ⭐

</div>
