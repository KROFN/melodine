"""Locales RU/EN parity tests - no feature may ship half-translated."""

from __future__ import annotations

import re

from melodine.i18n import get_language, set_language, t
from melodine.i18n.locales import LOCALES

PLACEHOLDER_RE = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")


class TestParity:
    def test_same_key_sets(self):
        assert set(LOCALES["ru"]) == set(LOCALES["en"])

    def test_placeholders_match_per_key(self):
        for key in LOCALES["ru"]:
            ru_placeholders = set(PLACEHOLDER_RE.findall(LOCALES["ru"][key]))
            en_placeholders = set(PLACEHOLDER_RE.findall(LOCALES["en"][key]))
            assert ru_placeholders == en_placeholders, (
                f"placeholder mismatch for {key!r}: ru={ru_placeholders} en={en_placeholders}"
            )

    def test_minimum_catalog_size(self):
        # The v2 UI needs a rich catalog; guard against accidental mass removal.
        assert len(LOCALES["ru"]) >= 200
        assert len(LOCALES["ru"]) == len(LOCALES["en"])

    def test_no_empty_values(self):
        for lang, catalog in LOCALES.items():
            for key, value in catalog.items():
                assert value.strip(), f"empty translation: {lang}.{key}"


class TestTranslate:
    def test_translation_switch(self):
        set_language("ru")
        assert t("menu_prompt") == "Выберите действие"
        set_language("en")
        assert t("menu_prompt") == "Choose an action"

    def test_format_kwargs(self):
        set_language("en")
        assert t("pl_confirm", n=5) == "Start downloading 5 tracks?"
        set_language("ru")
        assert t("pl_confirm", n=5) == "Начать загрузку 5 треков?"

    def test_unknown_key_returns_key(self):
        set_language("en")
        assert t("definitely_not_a_key") == "definitely_not_a_key"

    def test_invalid_language_ignored(self):
        set_language("en")
        set_language("klingon")
        assert get_language() == "en"

    def test_all_score_reasons_exist(self):
        """Every reason key the scorer can emit must be translated."""
        from melodine.services.scoring import _INTENT_PATTERNS  # noqa: F401

        reason_keys = [
            "score_reason_topic",
            "score_reason_official_audio",
            "score_reason_audio",
            "score_reason_lyrics",
            "score_reason_duration_exact",
            "score_reason_duration_close",
            "score_reason_duration_far",
            "score_reason_title_exact",
            "score_reason_title_similar",
            "score_reason_intent_match",
            "score_penalty_music_video",
            "score_penalty_official_video",
            "score_penalty_live",
            "score_penalty_cover",
            "score_penalty_alt_mix",
            "score_penalty_remix",
            "score_penalty_instrumental",
            "score_penalty_reaction",
            "score_penalty_shorts",
            "score_penalty_longform",
            "score_penalty_quality_markers",
        ]
        for key in reason_keys:
            assert key in LOCALES["ru"], key
            assert key in LOCALES["en"], key
