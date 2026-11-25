"""ページ（リザルト）のテスト。Django のテストクライアントを使う。

実行：docker compose exec web python manage.py test plays
（プレイ画面 /plays/<id>/ は frontend/dist/index.html が必要なため、ここではテストしない）
"""
import json
from unittest import mock

from django.test import TestCase

from .gemini import GeminiError
from .guest_play import GUEST_SESSION_KEY

SCENARIO = {
    "title": "閉店を延ばして", "description": "喫茶店の閉店間際", "character_name": "マスター",
    "character_intro": "頑固な店主", "goal": "閉店を30分延ばしてもらう", "condition": "値引きは頼まない",
}


class ResultPageTest(TestCase):
    def setUp(self):
        super().setUp()
        # 表情 SVG の生成は本物の Gemini を呼ばない（失敗扱い＝固定の SVG で始まる）
        patcher = mock.patch("plays.api.gemini.generate_expressions",
                             side_effect=GeminiError("AI_ERROR"))
        patcher.start()
        self.addCleanup(patcher.stop)

    def start_play(self):
        """テスト用：プレイを開始して play_id を返す"""
        with mock.patch("plays.api.gemini.generate_scenario", return_value=SCENARIO):
            res = self.client.post("/api/plays/", data=json.dumps({}), content_type="application/json")
        return res.json()["play_id"]

    def set_status(self, status, score):
        """テスト用：セッションの中のプレイの状態を書き換える"""
        session = self.client.session
        play = session[GUEST_SESSION_KEY]
        play["status"], play["score"] = status, score
        session[GUEST_SESSION_KEY] = play
        session.save()

    def test_cleared_result_is_shown(self):
        play_id = self.start_play()
        self.set_status("cleared", 500)
        res = self.client.get(f"/plays/{play_id}/result/")
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "500")
        self.assertContains(res, "説得成功")

    def test_failed_result_is_shown(self):
        play_id = self.start_play()
        self.set_status("failed", 0)
        self.assertContains(self.client.get(f"/plays/{play_id}/result/"), "説得失敗")

    def test_guest_result_hides_member_only_parts(self):
        """ゲストの結果には、順位・会話を見返す・ランキングを見る・会員メニューを出さない"""
        play_id = self.start_play()
        self.set_status("cleared", 500)
        res = self.client.get(f"/plays/{play_id}/result/")
        for hidden in ("今日のランキング", "btn-log", "btn-ranking", "マイページ", "自己ベスト"):
            self.assertNotContains(res, hidden)

    def test_failed_result_hides_clear_time(self):
        """失敗のときはクリアタイムのカードを出さない"""
        play_id = self.start_play()
        self.set_status("failed", 0)
        self.assertNotContains(self.client.get(f"/plays/{play_id}/result/"), "time-card")

    def test_result_sets_csrf_cookie_for_retry_button(self):
        """「もう一度挑戦する」(top.js) が使う csrftoken の Cookie が配られる"""
        play_id = self.start_play()
        self.set_status("cleared", 500)
        self.assertIn("csrftoken", self.client.get(f"/plays/{play_id}/result/").cookies)

    def test_playing_redirects_to_play_screen(self):
        play_id = self.start_play()
        res = self.client.get(f"/plays/{play_id}/result/")
        self.assertRedirects(res, f"/plays/{play_id}/", fetch_redirect_response=False)

    def test_aborted_or_other_session_is_404(self):
        play_id = self.start_play()
        self.set_status("aborted", None)
        self.assertEqual(self.client.get(f"/plays/{play_id}/result/").status_code, 404)
        other = self.client_class()
        self.assertEqual(other.get(f"/plays/{play_id}/result/").status_code, 404)

    def test_title_is_escaped(self):
        """お題のタイトルに HTML が入っていても、そのまま実行されずエスケープされる"""
        play_id = self.start_play()
        session = self.client.session
        play = session[GUEST_SESSION_KEY]
        play["scenario"]["title"] = "<script>alert(1)</script>"
        play["status"], play["score"] = "cleared", 1
        session[GUEST_SESSION_KEY] = play
        session.save()
        res = self.client.get(f"/plays/{play_id}/result/")
        self.assertNotContains(res, "<script>alert(1)</script>")
