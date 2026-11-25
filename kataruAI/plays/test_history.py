"""プレイ履歴（一覧・詳細）のテスト"""
from django.test import TestCase
from django.utils import timezone

from accounts.models import User
from scenarios.models import Scenario

from .models import Play, PlayTurn


def make_play(user, status="cleared", difficulty="beginner", score=500, title="お題", **extra):
    scenario = Scenario.objects.create(creator=user, kind="random", difficulty=difficulty, title=title)
    return Play.objects.create(
        user=user, scenario=scenario, status=status, score=score, turn_limit=15,
        save_chat_log=True, turns_used=extra.pop("turns_used", 2), **extra,
    )


def add_turn(play, no, state, delta=(5, -5, 5), reason="", message="こんにちは", reply="……", expression="normal"):
    return PlayTurn.objects.create(
        play=play, turn_no=no, user_message=message, ai_reply=reply,
        delta_mood=delta[0], delta_suspicion=delta[1], delta_understanding=delta[2],
        mood_after=50, suspicion_after=50, understanding_after=10,
        state_text=state, expression=expression, reason=reason,
    )


class HistoryListTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("a@example.com", "abcd1234", username="たろう")
        self.client.force_login(self.user)

    def test_login_required(self):
        self.client.logout()
        self.assertEqual(self.client.get("/plays/history/").status_code, 302)

    def test_shows_own_cleared_failed_playing_but_not_aborted(self):
        make_play(self.user, "cleared", title="クリアのお題")
        make_play(self.user, "failed", score=0, title="失敗のお題")
        playing = make_play(self.user, "playing", score=None, title="プレイ中のお題")
        make_play(self.user, "aborted", score=None, title="中断のお題")
        make_play(User.objects.create_user("b@example.com", "abcd1234"), title="他人のお題")
        res = self.client.get("/plays/history/")
        self.assertContains(res, "クリアのお題")
        self.assertContains(res, "失敗のお題")
        self.assertContains(res, "プレイ中のお題")
        self.assertNotContains(res, "中断のお題")
        self.assertNotContains(res, "他人のお題")
        self.assertContains(res, f'href="/plays/{playing.pk}/"', html=False)  # 再開
        self.assertContains(res, "・・・")

    def test_newest_first(self):
        old = make_play(self.user, title="古い")
        Play.objects.filter(pk=old.pk).update(started_at=timezone.now() - timezone.timedelta(days=1))
        make_play(self.user, title="新しい")
        content = self.client.get("/plays/history/").content.decode()
        self.assertLess(content.index("新しい"), content.index("古い"))

    def test_filter_by_difficulty(self):
        make_play(self.user, difficulty="beginner", title="初級のお題")
        make_play(self.user, difficulty="advanced", title="上級のお題")
        res = self.client.get("/plays/history/?difficulty=advanced")
        self.assertContains(res, "上級のお題")
        self.assertNotContains(res, "初級のお題")
        # 知らない値は「すべて」
        res = self.client.get("/plays/history/?difficulty=xxx")
        self.assertContains(res, "初級のお題")

    def test_empty_message(self):
        self.assertContains(self.client.get("/plays/history/"), "表示できるプレイ履歴がありません")

    def test_pagination_20_per_page(self):
        for i in range(21):
            make_play(self.user, title=f"お題{i:02d}")
        res = self.client.get("/plays/history/")
        self.assertEqual(len(res.context["rows"]), 20)
        self.assertContains(res, "1 / 2")
        res = self.client.get("/plays/history/?difficulty=all&page=2")
        self.assertEqual(len(res.context["rows"]), 1)


class HistoryDetailTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("a@example.com", "abcd1234", username="たろう")
        self.client.force_login(self.user)

    def test_detail_shows_log_timeline_and_explanation(self):
        play = make_play(self.user, turns_used=3)
        add_turn(play, 1, "警戒している", delta=(2, 0, 2), message="はじめまして", reply="なんだい")
        add_turn(play, 2, "警戒している", delta=(15, -15, 15), reason="具体的な提案が響いた")
        add_turn(play, 3, "納得した", delta=(5, -5, 5), expression="happy")
        res = self.client.get(f"/plays/history/{play.pk}/")
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "はじめまして")
        self.assertContains(res, "なんだい")
        timeline = res.context["timeline"]
        self.assertEqual([item["turn_no"] for item in timeline], [1, 3])  # 様子が変わったターン＋最後
        self.assertTrue(timeline[-1]["is_final"])
        self.assertContains(res, "2ターン目がポイント")
        self.assertContains(res, "具体的な提案が響いた")
        self.assertContains(res, f'data-scenario-id="{play.scenario_id}"', html=False)

    def test_log_not_saved_message(self):
        play = make_play(self.user)
        add_turn(play, 1, "迷っている", message=None, reply=None)
        self.assertContains(self.client.get(f"/plays/history/{play.pk}/"), "このプレイの会話は保存されていません")

    def test_others_and_aborted_are_not_found(self):
        other_play = make_play(User.objects.create_user("b@example.com", "abcd1234"))
        aborted = make_play(self.user, "aborted", score=None)
        for pk in (other_play.pk, aborted.pk, 99999):
            res = self.client.get(f"/plays/history/{pk}/")
            self.assertContains(res, "指定された履歴データが見つかりません", status_code=404)

    def test_playing_redirects_to_play_page(self):
        play = make_play(self.user, "playing", score=None)
        self.assertRedirects(self.client.get(f"/plays/history/{play.pk}/"), f"/plays/{play.pk}/",
                             fetch_redirect_response=False)

    def test_retry_disabled_when_scenario_deleted(self):
        play = make_play(self.user)
        Scenario.objects.update(deleted_at=timezone.now())
        self.assertContains(self.client.get(f"/plays/history/{play.pk}/"), "disabled>もう一度挑戦する", html=False)
