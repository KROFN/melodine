"""Configuration tests: v1 compatibility, validation, round-trip."""

from __future__ import annotations

from pathlib import Path

import pytest

from melodine.core.config import (
    AppConfig,
    load_config,
    migrate_legacy_dict,
    save_config,
)
from melodine.core.exceptions import ConfigError

V1_YAML = """\
theme: nord
language: ru
download:
  threads: 6
  pause: 1.0
  retry_attempts: 5
  retry_delay: 3.0
  quality: 192
  max_duration: 600
  timeout: 30
  smart_search: true
  download_covers: true
paths:
  output: ./music
  failed_log: ./failed.txt
metadata:
  add_tags: false
  download_covers: true
"""


class TestV1Migration:
    def test_full_v1_config(self, tmp_path: Path):
        config_file = tmp_path / "config.yaml"
        config_file.write_text(V1_YAML, encoding="utf-8")
        config, created = load_config(config_file)
        assert created is False
        assert config.theme == "nord"
        assert config.language == "ru"
        # download.* preserved
        assert config.download.threads == 6
        assert config.download.retry_attempts == 5
        assert config.download.smart_search is True
        # quality -> audio.bitrate
        assert config.audio.bitrate == 192
        # paths.* -> output.*
        assert config.output.folder == "./music"
        assert config.output.failed_log == "./failed.txt"
        # metadata.add_tags -> tags.enabled
        assert config.tags.enabled is False
        # download_covers -> artwork.embed
        assert config.artwork.embed is True

    def test_partial_v1_config(self, tmp_path: Path):
        config_file = tmp_path / "config.yaml"
        config_file.write_text("theme: ocean\nlanguage: en\n", encoding="utf-8")
        config, _ = load_config(config_file)
        assert config.theme == "ocean"
        assert config.language == "en"
        assert config.download.threads == 4  # defaults for the rest

    def test_migrate_dict_is_pure(self):
        original = {"paths": {"output": "./x"}}
        migrate_legacy_dict(original)
        assert original == {"paths": {"output": "./x"}}


class TestValidation:
    def test_invalid_codec_rejected(self, tmp_path: Path):
        config_file = tmp_path / "config.yaml"
        config_file.write_text("audio:\n  codec: wma\n", encoding="utf-8")
        with pytest.raises(ConfigError):
            load_config(config_file)

    def test_invalid_language_rejected(self, tmp_path: Path):
        config_file = tmp_path / "config.yaml"
        config_file.write_text("language: fr\n", encoding="utf-8")
        with pytest.raises(ConfigError):
            load_config(config_file)

    def test_invalid_template_rejected(self, tmp_path: Path):
        config_file = tmp_path / "config.yaml"
        config_file.write_text("output:\n  template: '{artist}/{title}'\n", encoding="utf-8")
        with pytest.raises(ConfigError):
            load_config(config_file)

    def test_corrupt_yaml_raises_config_error(self, tmp_path: Path):
        config_file = tmp_path / "config.yaml"
        config_file.write_text(":\n  - [broken\n", encoding="utf-8")
        with pytest.raises(ConfigError):
            load_config(config_file)

    def test_unknown_keys_ignored(self, tmp_path: Path):
        config_file = tmp_path / "config.yaml"
        config_file.write_text("future_option: 42\ntheme: forest\n", encoding="utf-8")
        config, _ = load_config(config_file)
        assert config.theme == "forest"


class TestRoundTrip:
    def test_save_and_reload(self, tmp_path: Path):
        config = AppConfig()
        config.audio.codec = "opus"
        config.lyrics.save_lrc = False
        config_file = tmp_path / "config.yaml"
        save_config(config, config_file)
        loaded, created = load_config(config_file)
        assert created is False
        assert loaded.audio.codec == "opus"
        assert loaded.lyrics.save_lrc is False
        assert loaded.model_dump() == config.model_dump()

    def test_missing_file_creates_default(self, tmp_path: Path):
        config_file = tmp_path / "config.yaml"
        config, created = load_config(config_file)
        assert created is True
        assert config_file.exists()
        assert config.theme == "dracula"
        assert config.language == "ru"  # v1 soul: RU by default


class TestSponsorBlockDefaults:
    def test_categories_sanitized(self):
        config = AppConfig()
        config.sponsorblock.categories = ["sponsor", "garbage", "music_offtopic"]
        assert config.sponsorblock.categories == ["sponsor", "music_offtopic"]

    def test_categories_preserve_order_and_dedup(self):
        config = AppConfig()
        config.sponsorblock.categories = ["intro", "intro", "sponsor", "bogus"]
        assert config.sponsorblock.categories == ["intro", "sponsor"]

    def test_default_categories(self):
        config = AppConfig()
        assert "music_offtopic" in config.sponsorblock.categories
        assert "sponsor" in config.sponsorblock.categories
