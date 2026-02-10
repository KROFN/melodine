_lang = "ru"

_strings = {
    "ru": {
        # -- главное меню --
        "menu_prompt": "Что делаем?",
        "menu_download": "📥  Скачать плейлист",
        "menu_retry": "🔄  Докачать неудачные",
        "menu_retry_n": "🔄  Докачать неудачные ({n} треков)",
        "menu_retry_disabled": "нет неудачных",
        "menu_search": "🔍  Найти и скачать трек",
        "menu_stats": "📊  Статистика",
        "menu_settings": "⚙️   Настройки",
        "menu_exit": "❌  Выход",
        "goodbye": "👋 До встречи!",

        # -- скачивание --
        "dl_title": "📥 Скачивание плейлиста",
        "dl_filepath": "Путь к файлу плейлиста:",
        "dl_file_not_found": "Файл не найден",
        "dl_no_tracks": "❌ Не удалось найти треки в файле.",
        "dl_all_done": "✅ Все треки уже скачаны!",
        "dl_confirm": "Начинаем скачивание {n} треков?",
        "dl_stopping": "⏸  Останавливаю...",
        "dl_progress": "Скачивание",
        "dl_progress_title": "⬇ Прогресс",
        "dl_last": "Последний",

        # -- retry --
        "retry_title": "🔄 Докачка неудачных треков",
        "retry_none": "✅ Нет неудачных треков!",
        "retry_found": "Найдено {n} неудачных треков",
        "retry_confirm": "Попробовать скачать {n} треков?",
        "retry_again": "🔄 Попробовать неудачные ещё раз",

        # -- post-download --
        "post_open": "📂 Открыть папку загрузок",
        "post_menu": "🏠 В главное меню",
        "post_prompt": "Что дальше?",

        # -- поиск --
        "search_title": "🔍 Поиск трека",
        "search_prompt": "Введите запрос:",
        "search_empty": "Введите запрос",
        "search_wait": "Ищу...",
        "search_nothing": "😔 Ничего не найдено",
        "search_select": "Выберите трек:",
        "search_cancel": "❌ Отмена",

        # -- статистика --
        "stats_empty": "📭 Пока нет данных. Скачайте что-нибудь! 🎵",
        "stats_title": "📊 Статистика",
        "stats_total": "📦 Всего скачано:",
        "stats_tracks": "треков",
        "stats_success": "✅ Успешно:",
        "stats_failed": "❌ Неудачно:",
        "stats_size": "💾 Общий размер:",
        "stats_time": "⏱  Общее время:",
        "stats_week": "📈 Последние 7 дней:",
        "stats_top": "🏆 Топ артисты:",

        # -- настройки --
        "settings_title": "⚙️  Настройки",
        "settings_prompt": "Раздел настроек",
        "settings_download": "🔧 Параметры скачивания",
        "settings_theme": "🎨 Тема оформления",
        "settings_paths": "📂 Папка загрузок",
        "settings_meta": "🏷️  Метаданные",
        "settings_show": "📋 Показать конфиг",
        "settings_reset": "🔄 Сбросить настройки",
        "settings_lang": "🌐 Язык / Language",
        "settings_back": "🔙 Назад",
        "settings_saved": "✅ Настройки сохранены!",
        "settings_reset_confirm": "Сбросить ВСЕ настройки к дефолтным?",
        "settings_reset_done": "✅ Настройки сброшены!",
        "settings_cancelled": "Отменено",

        # -- параметры скачивания --
        "cfg_threads": "Потоки [{v}]:",
        "cfg_threads_err": "Целое число от 1 до 15",
        "cfg_pause": "Пауза между треками, сек [{v}]:",
        "cfg_pause_err": "Число от 0 до 10",
        "cfg_retry": "Попытки при ошибке [{v}]:",
        "cfg_retry_err": "Целое число от 0 до 10",
        "cfg_retry_delay": "Задержка retry, сек [{v}]:",
        "cfg_retry_delay_err": "Число от 0 до 60",
        "cfg_quality": "Качество MP3:",
        "cfg_duration": "Макс. длительность трека, сек [{v}]:",
        "cfg_duration_err": "Целое число от 60 до 3600",
        "cfg_timeout": "Таймаут соединения, сек [{v}]:",
        "cfg_timeout_err": "Целое число от 5 до 120",
        "cfg_smart": "Smart Search (умный поиск)?",
        "cfg_tags": "Добавлять ID3 теги (артист, название)?",
        "cfg_covers": "Скачивать обложки? (замедляет загрузку)",

        # -- тема --
        "theme_current": "Текущая:",
        "theme_select": "Выберите тему:",
        "theme_changed": "✅ Тема: {name}",

        # -- пути --
        "paths_current": "Текущая:",
        "paths_prompt": "Новая папка загрузок:",
        "paths_set": "✅ Папка: {path}",

        # -- display --
        "subtitle": "Твой плейлист. Скачан. Красиво.",
        "welcome_title": "✨ Добро пожаловать!",
        "welcome_text": "👋 Первый запуск! Создан config.yaml",
        "welcome_folder": "📂 Папка загрузок: ./downloads",
        "welcome_theme": "🎨 Тема: Dracula",
        "welcome_hint": "Настройки можно изменить в меню ⚙️  Настройки",
        "press_enter": "Нажми Enter чтобы продолжить...",

        "panel_playlist": "📋 Плейлист",
        "playlist_file": "Файл:",
        "playlist_tracks": "Треков:",
        "playlist_new": "Новых:",
        "playlist_existing": "уже скачаны",

        "panel_result": "📊 Результат",
        "result_ok": "✅ Скачано:",
        "result_fail": "❌ Не удалось:",
        "result_retry": "🔄 С повтором:",
        "result_skip": "⏭  Пропущено:",
        "result_time": "⏱  Время:",
        "result_size": "💾 Размер:",

        "panel_failed": "❌ Неудачные ({n})",
        "failed_more": "... ещё {n}",
        "failed_saved": "💾 Сохранено в failed_tracks.txt",

        "config_title": "⚙️  Текущие настройки",
        "config_param": "Параметр",
        "config_value": "Значение",

        # -- форматирование --
        "time_sec": "{v} сек",
        "time_min": "{m} мин {s} сек",
        "time_hour": "{h}ч {m}мин",
    },

    "en": {
        "menu_prompt": "What to do?",
        "menu_download": "📥  Download playlist",
        "menu_retry": "🔄  Retry failed",
        "menu_retry_n": "🔄  Retry failed ({n} tracks)",
        "menu_retry_disabled": "no failed tracks",
        "menu_search": "🔍  Find and download track",
        "menu_stats": "📊  Statistics",
        "menu_settings": "⚙️   Settings",
        "menu_exit": "❌  Exit",
        "goodbye": "👋 Goodbye!",

        "dl_title": "📥 Download playlist",
        "dl_filepath": "Path to playlist file:",
        "dl_file_not_found": "File not found",
        "dl_no_tracks": "❌ No tracks found in file.",
        "dl_all_done": "✅ All tracks already downloaded!",
        "dl_confirm": "Start downloading {n} tracks?",
        "dl_stopping": "⏸  Stopping...",
        "dl_progress": "Downloading",
        "dl_progress_title": "⬇ Progress",
        "dl_last": "Last",

        "retry_title": "🔄 Retry failed tracks",
        "retry_none": "✅ No failed tracks!",
        "retry_found": "Found {n} failed tracks",
        "retry_confirm": "Try downloading {n} tracks?",
        "retry_again": "🔄 Retry failed again",

        "post_open": "📂 Open downloads folder",
        "post_menu": "🏠 Main menu",
        "post_prompt": "What's next?",

        "search_title": "🔍 Search track",
        "search_prompt": "Enter search query:",
        "search_empty": "Enter a query",
        "search_wait": "Searching...",
        "search_nothing": "😔 Nothing found",
        "search_select": "Select a track:",
        "search_cancel": "❌ Cancel",

        "stats_empty": "📭 No data yet. Download something! 🎵",
        "stats_title": "📊 Statistics",
        "stats_total": "📦 Total downloaded:",
        "stats_tracks": "tracks",
        "stats_success": "✅ Success:",
        "stats_failed": "❌ Failed:",
        "stats_size": "💾 Total size:",
        "stats_time": "⏱  Total time:",
        "stats_week": "📈 Last 7 days:",
        "stats_top": "🏆 Top artists:",

        "settings_title": "⚙️  Settings",
        "settings_prompt": "Settings section",
        "settings_download": "🔧 Download parameters",
        "settings_theme": "🎨 Theme",
        "settings_paths": "📂 Downloads folder",
        "settings_meta": "🏷️  Metadata",
        "settings_show": "📋 Show config",
        "settings_reset": "🔄 Reset settings",
        "settings_lang": "🌐 Язык / Language",
        "settings_back": "🔙 Back",
        "settings_saved": "✅ Settings saved!",
        "settings_reset_confirm": "Reset ALL settings to defaults?",
        "settings_reset_done": "✅ Settings reset!",
        "settings_cancelled": "Cancelled",

        "cfg_threads": "Threads [{v}]:",
        "cfg_threads_err": "Integer from 1 to 15",
        "cfg_pause": "Pause between tracks, sec [{v}]:",
        "cfg_pause_err": "Number from 0 to 10",
        "cfg_retry": "Retries on error [{v}]:",
        "cfg_retry_err": "Integer from 0 to 10",
        "cfg_retry_delay": "Retry delay, sec [{v}]:",
        "cfg_retry_delay_err": "Number from 0 to 60",
        "cfg_quality": "MP3 quality:",
        "cfg_duration": "Max track duration, sec [{v}]:",
        "cfg_duration_err": "Integer from 60 to 3600",
        "cfg_timeout": "Connection timeout, sec [{v}]:",
        "cfg_timeout_err": "Integer from 5 to 120",
        "cfg_smart": "Smart Search?",
        "cfg_tags": "Add ID3 tags (artist, title)?",
        "cfg_covers": "Download covers? (slower)",

        "theme_current": "Current:",
        "theme_select": "Select theme:",
        "theme_changed": "✅ Theme: {name}",

        "paths_current": "Current:",
        "paths_prompt": "New downloads folder:",
        "paths_set": "✅ Folder: {path}",

        "subtitle": "Your playlist. Downloaded. Beautifully.",
        "welcome_title": "✨ Welcome!",
        "welcome_text": "👋 First run! Created config.yaml",
        "welcome_folder": "📂 Downloads folder: ./downloads",
        "welcome_theme": "🎨 Theme: Dracula",
        "welcome_hint": "Settings can be changed in ⚙️  Settings",
        "press_enter": "Press Enter to continue...",

        "panel_playlist": "📋 Playlist",
        "playlist_file": "File:",
        "playlist_tracks": "Tracks:",
        "playlist_new": "New:",
        "playlist_existing": "already downloaded",

        "panel_result": "📊 Result",
        "result_ok": "✅ Downloaded:",
        "result_fail": "❌ Failed:",
        "result_retry": "🔄 Retried:",
        "result_skip": "⏭  Skipped:",
        "result_time": "⏱  Time:",
        "result_size": "💾 Size:",

        "panel_failed": "❌ Failed ({n})",
        "failed_more": "... and {n} more",
        "failed_saved": "💾 Saved to failed_tracks.txt",

        "config_title": "⚙️  Current settings",
        "config_param": "Parameter",
        "config_value": "Value",

        "time_sec": "{v} sec",
        "time_min": "{m} min {s} sec",
        "time_hour": "{h}h {m}min",
    },
}


def set_language(lang: str):
    global _lang
    if lang in _strings:
        _lang = lang


def get_language() -> str:
    return _lang


def t(key: str, **kwargs) -> str:
    s = _strings.get(_lang, _strings["en"]).get(key, key)
    if kwargs:
        try:
            return s.format(**kwargs)
        except (KeyError, IndexError):
            return s
    return s