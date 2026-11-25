"""会員のリザルト画面と「もう一度挑戦する」（scenario_id で開始）のテスト"""
from datetime import timedelta

from django.utils import timezone

from accounts.models import User
from scenarios.models import Scenario

from .models import Play
from .test_member_play import MemberPlayTestBase


def make_cleared_play(user, score, difficulty="beginner", kind="random", finished_at=None):
    scenario = Scenario.objects.create(creator=user, kind=kind, difficulty=difficulty, title="t")
    return Play.objects.create(
        user=user, scenario=scenario, status="cleared", score=score, turn_limit=15,
        save_chat_log=True, finished_at=finished_at or timezone.now(),
    )


class MemberResultPageTest(MemberPlayTestBase):
    def clear(self, play_id):
        for no in range(1, 6):
            self.turn(play_id, no, delta=(5, -5, 15))

    def test_cleared_result_shows_score_rank_and_member_buttons(self):
        play_id = self.start()
        self.clear(play_id)
        res = self.client.get(f"/plays/{play_id}/result/")
        self.assertEqual(res.status_code, 200)
        play = Play.objects.get(pk=play_id)
        self.assertContains(res, "説得成功！")
        self.assertContains(res, f'<span id="score">{play.score}</span>', html=False)
        self.assertContains(res, "今日のランキング <strong>1位</strong>", html=False)
        self.assertContains(res, f'data-scenario-id="{play.scenario_id}"', html=False)
        self.assertContains(res, f'href="/plays/history/{play_id}/"', html=False)
        self.assertContains(res, 'href="/rankings/"', html=False)
        self.assertContains(res, "マイページ")  # 会員用の共通ヘッダー
        self.assertNotContains(res, "guest-btn-home")

    def test_failed_result_hides_rank_and_time(self):
        play_id = self.start()
        self.post(f"/api/plays/{play_id}/give-up/")
        res = self.client.get(f"/plays/{play_id}/result/")
        self.assertContains(res, "説得失敗…")
        self.assertNotContains(res, 'id="rank"')
        self.assertNotContains(res, 'id="time-card"')

    def test_playing_redirects_to_play_page(self):
        play_id = self.start()
        res = self.client.get(f"/plays/{play_id}/result/")
        self.assertRedirects(res, f"/plays/{play_id}/", fetch_redirect_response=False)

    def test_aborted_and_others_play_are_404(self):
        play_id = self.start()
        self.post(f"/api/plays/{play_id}/abort/")
        self.assertEqual(self.client.get(f"/plays/{play_id}/result/").status_code, 404)
        other_play = self.start()
        self.post(f"/api/plays/{other_play}/give-up/")
        self.client.force_login(User.objects.create_user("b@example.com", "pass1234"))
        self.assertEqual(self.client.get(f"/plays/{other_play}/result/").status_code, 404)

    def test_retry_button_is_disabled_when_scenario_deleted(self):
        play_id = self.start()
        self.post(f"/api/plays/{play_id}/give-up/")
        Scenario.objects.update(deleted_at=timezone.now())
        res = self.client.get(f"/plays/{play_id}/result/")
        self.assertContains(res, "disabled>もう一度挑戦する", html=False)


class TodayRankTest(MemberPlayTestBase):
    def rank_of(self, play):
        from . import member_play
        return member_play.today_rank(Play.objects.select_related("scenario").get(pk=play.pk))

    def test_rank_by_total_of_today_same_difficulty(self):
        other = User.objects.create_user("b@example.com", "pass1234")
        make_cleared_play(other, 500)
        mine = make_cleared_play(self.user, 300)
        self.assertEqual(self.rank_of(mine), 2)
        make_cleared_play(self.user, 300)  # 合計600で抜く
        self.assertEqual(self.rank_of(mine), 1)

    def test_other_difficulty_and_yesterday_and_user_scenarios_are_ignored(self):
        other = User.objects.create_user("b@example.com", "pass1234")
        make_cleared_play(other, 900, difficulty="advanced")
        make_cleared_play(other, 900, finished_at=timezone.now() - timedelta(days=2))
        make_cleared_play(other, 900, kind="user")
        mine = make_cleared_play(self.user, 100)
        self.assertEqual(self.rank_of(mine), 1)

    def test_inactive_users_are_ignored(self):
        other = User.objects.create_user("b@example.com", "pass1234", is_active=False)
        make_cleared_play(other, 900)
        self.assertEqual(self.rank_of(make_cleared_play(self.user, 100)), 1)

    def test_no_rank_for_user_scenario(self):
        self.assertIsNone(self.rank_of(make_cleared_play(self.user, 100, kind="user")))


class RetryWithScenarioTest(MemberPlayTestBase):
    def test_retry_uses_same_scenario_without_generation(self):
        first = self.start("advanced")
        self.post(f"/api/plays/{first}/give-up/")
        scenario_id = Play.objects.get(pk=first).scenario_id
        res = self.post("/api/plays/", {"scenario_id": scenario_id})  # Gemini を差し替えていない＝呼ばれない
        self.assertEqual(res.status_code, 201)
        play = Play.objects.get(pk=res.json()["play_id"])
        self.assertEqual(play.scenario_id, scenario_id)
        self.assertEqual(play.turn_limit, 10)  # 同じ難易度
        self.assertEqual(Scenario.objects.count(), 1)

    def test_retry_aborts_current_playing(self):
        first = self.start()
        scenario_id = Play.objects.get(pk=first).scenario_id
        self.post("/api/plays/", {"scenario_id": scenario_id})
        self.assertEqual(Play.objects.get(pk=first).status, "aborted")

    def test_cannot_start_others_private_or_deleted_scenario(self):
        other = User.objects.create_user("b@example.com", "pass1234")
        private = Scenario.objects.create(creator=other, kind="user", difficulty="beginner", title="t")
        deleted = Scenario.objects.create(
            creator=other, kind="user", difficulty="beginner", title="t",
            is_public=True, deleted_at=timezone.now(),
        )
        for scenario_id in (private.pk, deleted.pk, 99999, "abc", True):
            res = self.post("/api/plays/", {"scenario_id": scenario_id})
            self.assertEqual(res.status_code, 404, scenario_id)
            self.assertEqual(
                res.json()["error"]["message"], "指定したシナリオは存在しないか、削除されています。"
            )
        self.assertFalse(Play.objects.exists())

    def test_can_start_others_public_scenario(self):
        other = User.objects.create_user("b@example.com", "pass1234")
        public = Scenario.objects.create(
            creator=other, kind="user", difficulty="intermediate", title="t", is_public=True
        )
        res = self.post("/api/plays/", {"scenario_id": public.pk})
        self.assertEqual(res.status_code, 201)
        self.assertEqual(Play.objects.get(pk=res.json()["play_id"]).turn_limit, 12)
