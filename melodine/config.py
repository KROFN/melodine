import os
from pathlib import Path
import yaml
from pydantic import BaseModel, Field

CONFIG_PATH = Path("config.yaml")


class DownloadConfig(BaseModel):
    threads: int = Field(default=4, ge=1, le=15)
    pause: float = Field(default=0.5, ge=0.0, le=10.0)
    retry_attempts: int = Field(default=3, ge=0, le=10)
    retry_delay: float = Field(default=5.0, ge=0.0, le=60.0)
    quality: int = Field(default=320)
    max_duration: int = Field(default=600, ge=60, le=3600)
    timeout: int = Field(default=30, ge=5, le=120)
    smart_search: bool = True
    download_covers: bool = False


class PathsConfig(BaseModel):
    output: str = "./downloads"
    failed_log: str = "./failed_tracks.txt"


class MetadataConfig(BaseModel):
    add_tags: bool = True
    download_covers: bool = False


class AppConfig(BaseModel):
    theme: str = "dracula"
    language: str = "ru"
    download: DownloadConfig = DownloadConfig()
    paths: PathsConfig = PathsConfig()
    metadata: MetadataConfig = MetadataConfig()


def load_config() -> AppConfig:
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            return AppConfig(**data)
        except Exception:
            return AppConfig()

    config = AppConfig()
    save_config(config)
    return config


def save_config(config: AppConfig):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        yaml.dump(
            config.model_dump(),
            f, default_flow_style=False,
            allow_unicode=True, sort_keys=False,
        )


def reset_config() -> AppConfig:
    config = AppConfig()
    save_config(config)
    return config