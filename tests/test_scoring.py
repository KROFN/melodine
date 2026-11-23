"""Anti-MV Studio Scorer tests."""

from __future__ import annotations

from melodine.models import IntentFlags, SearchCandidate
from melodine.services.scoring import detect_intent, rank_candidates, score_candidate


def candidate(title: str, channel: str = "Some Channel", duration: int = 210) -> SearchCandidate:
    return SearchCandidate(
        source_id="abc123",
        url="https://youtu.be/abc123",
        title=title,
        channel=channel,
        duration=duration,
        views=1000,
    )


class TestStudioBonuses:
    def test_topic_channel_gets_big_bonus(self):
        scored = score_candidate(
            candidate("Around the World", channel="Daft Punk - Topic"),
            target_title="Around the World",
        )
        assert scored.score > 80
        assert any(r.key == "score_reason_topic" for r in scored.reasons)

    def test_official_audio_bonus(self):
        scored = score_candidate(candidate("Song (Official Audio)"))
        assert any(r.key == "score_reason_official_audio" for r in scored.reasons)

    def test_plain_audio_word_small_bonus(self):
        scored = score_candidate(candidate("Song audio"))
        assert any(r.key == "score_reason_audio" for r in scored.reasons)

    def test_topic_beats_music_video(self):
        topic = score_candidate(candidate("Around the World", channel="Artist - Topic"))
        video = score_candidate(
            candidate("Around the World (Official Music Video)", channel="Artist")
        )
        assert topic.score > video.score + 40


class TestPenalties:
    def test_music_video_penalized(self):
        scored = score_candidate(candidate("Song (Official Music Video)"))
        assert any(r.key == "score_penalty_music_video" for r in scored.reasons)
        assert scored.score < 50

    def test_live_penalized(self):
        scored = score_candidate(candidate("Song (Live at Wembley)"))
        assert any(r.key == "score_penalty_live" for r in scored.reasons)

    def test_cover_penalized(self):
        scored = score_candidate(candidate("Song (Cover by Band)"))
        assert any(r.key == "score_penalty_cover" for r in scored.reasons)

    def test_alt_mix_penalized_hard(self):
        scored = score_candidate(candidate("Song (Slowed + Reverb)"))
        assert any(r.key == "score_penalty_alt_mix" for r in scored.reasons)
        assert scored.score < 20

    def test_8d_penalized(self):
        scored = score_candidate(candidate("Song 8D Audio"))
        assert any(r.key == "score_penalty_alt_mix" for r in scored.reasons)

    def test_russian_mv_penalized(self):
        scored = score_candidate(candidate("Песня (Официальный клип)"))
        assert any(r.key == "score_penalty_music_video" for r in scored.reasons)

    def test_reaction_penalized(self):
        scored = score_candidate(candidate("Reaction to Song"))
        assert any(r.key == "score_penalty_reaction" for r in scored.reasons)

    def test_shorts_penalized(self):
        scored = score_candidate(candidate("Song #shorts"))
        assert any(r.key == "score_penalty_shorts" for r in scored.reasons)


class TestIntentOverride:
    def test_live_intent_rewards_live(self):
        intent = IntentFlags(live=True)
        scored = score_candidate(candidate("Song (Live)"), intent=intent)
        assert any(r.key == "score_reason_intent_match" for r in scored.reasons)
        no_intent = score_candidate(candidate("Song (Live)"))
        assert scored.score > no_intent.score

    def test_remix_intent_rewards_remix(self):
        intent = IntentFlags(remix=True)
        scored = score_candidate(candidate("Song (Remix)"), intent=intent)
        assert any(r.key == "score_reason_intent_match" for r in scored.reasons)

    def test_live_intent_waives_only_the_live_penalty(self):
        """`--live` waives the live penalty itself (0 points, 'requested')..."""
        intent = IntentFlags(live=True)
        scored = score_candidate(candidate("Song (Live at Wembley)"), intent=intent)
        live_reason = next(
            r for r in scored.reasons if r.key == "score_penalty_live"
        )
        assert live_reason.points == 0
        assert live_reason.value == "requested"

    def test_live_intent_does_not_waive_cover_reaction_penalties(self):
        """...but it must not silence unrelated penalties.

        Regression: "LIVE COVER REACTION" under `--live` used to collect the
        live bonus while hiding inside the `else` branch that skips every
        penalty when any intent matched.
        """
        intent = IntentFlags(live=True)
        scored = score_candidate(candidate("LIVE COVER REACTION"), intent=intent)
        assert any(r.key == "score_reason_intent_match" for r in scored.reasons)
        cover = next(r for r in scored.reasons if r.key == "score_penalty_cover")
        reaction = next(
            r for r in scored.reasons if r.key == "score_penalty_reaction"
        )
        assert cover.points == -40
        assert reaction.points == -60
        # Net effect: the multi-variant clickbait still loses hard.
        assert scored.score < 30

    def test_remix_intent_does_not_waive_reaction_penalty(self):
        intent = IntentFlags(remix=True)
        scored = score_candidate(
            candidate("Song (Remix) REACTION VIDEO"), intent=intent
        )
        reaction = next(
            r for r in scored.reasons if r.key == "score_penalty_reaction"
        )
        assert reaction.points == -60

    def test_detect_intent_english(self):
        intent = detect_intent("daft punk around the world live remix")
        assert intent.live and intent.remix

    def test_detect_intent_russian(self):
        intent = detect_intent("муза концерт кавер")
        assert intent.live and intent.cover

    def test_detect_intent_none(self):
        assert not detect_intent("daft punk around the world").any


class TestDurationScoring:
    def test_exact_duration_bonus(self):
        scored = score_candidate(
            candidate("Song", duration=200), expected_duration=200
        )
        assert any(r.key == "score_reason_duration_exact" for r in scored.reasons)

    def test_close_duration_bonus(self):
        scored = score_candidate(
            candidate("Song", duration=203), expected_duration=200
        )
        assert any(r.key == "score_reason_duration_close" for r in scored.reasons)

    def test_far_duration_penalty(self):
        scored = score_candidate(
            candidate("Song 1 Hour", duration=3600), expected_duration=200
        )
        assert any(r.key == "score_reason_duration_far" for r in scored.reasons)

    def test_unknown_duration_is_neutral(self):
        scored = score_candidate(candidate("Song", duration=0), expected_duration=200)
        assert not any("duration" in r.key for r in scored.reasons)


class TestTitleSimilarity:
    def test_exact_clean_title_bonus(self):
        scored = score_candidate(
            candidate("Around the World (Official Audio)"),
            target_title="Around the World",
        )
        assert any(r.key == "score_reason_title_exact" for r in scored.reasons)

    def test_similar_title_bonus(self):
        scored = score_candidate(
            candidate("around the world official audio"),
            target_title="Around the World",
        )
        assert any(
            r.key in {"score_reason_title_exact", "score_reason_title_similar"}
            for r in scored.reasons
        )


class TestScoringModes:
    def test_penalize_false_disables_anti_mv(self):
        scored = score_candidate(
            candidate("Song (Official Music Video)"), penalize=False
        )
        assert not any(r.key.startswith("score_penalty") for r in scored.reasons)
        assert not any(r.key in {"score_reason_topic", "score_reason_official_audio"}
                       for r in scored.reasons)

    def test_score_clamped_to_0_100(self):
        low = score_candidate(candidate("Reaction mix slowed 8d"))
        high = score_candidate(
            candidate("Song", channel="Artist - Topic"),
            target_title="Song",
            expected_duration=210,
        )
        assert 0 <= low.score <= 100
        assert 0 <= high.score <= 100

    def test_rank_candidates_sorts_desc(self):
        ranked = rank_candidates(
            [
                candidate("Song (Official Music Video)"),
                candidate("Song", channel="Artist - Topic"),
                candidate("Song (Live)"),
            ]
        )
        scores = [item.score for item in ranked]
        assert scores == sorted(scores, reverse=True)
        assert "Topic" in ranked[0].candidate.channel


class TestBadges:
    def test_badge_studio_for_topic(self):
        scored = score_candidate(candidate("Song", channel="Artist - Topic"))
        assert scored.badge == "studio"

    def test_badge_live(self):
        scored = score_candidate(candidate("Song Live"))
        assert scored.badge == "live"

    def test_badge_video(self):
        scored = score_candidate(candidate("Song Official Music Video"))
        assert scored.badge == "video"
