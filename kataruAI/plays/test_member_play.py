"""会員のプレイ（api.py の会員分岐・member_play.py）のテスト

Gemini は本物を呼ばず、unittest.mock で差し替える。
実行：docker compose exec web python manage.py test plays
"""
import json
from unittest import mock

from django.test import TestCase

from accounts.models import User, UserSetting
from scenarios.models import Scenario

from .gemini import GeminiError
from .models import Play, PlayTurn

SCENARIO = {
    "title": "閉店を延ばして", "description": "喫茶店の閉店間際", "character_name": "マスター",
    "character_intro": "頑固な店主", "goal": "閉店を30分延ばしてもらう", "condition": "値引きは頼まない",
}


def reply(delta=(5, -5, 10), expression="happy"):
    return {
        "reply": "うーん……", "state": "迷っている", "expression": expression, "reason": "理由",
        "delta": {"mood": delta[0], "suspicion": delta[1], "understanding": delta[2]},
    }


class MemberPlayTestBase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("a@example.com", "pass1234", username="たろう")
        self.client.force_login(self.user)
        # 表情 SVG の生成は本物の Gemini を呼ばない（失敗扱い＝固定の SVG で始まる）
        patcher = mock.patch("plays.api.gemini.generate_expressions",
                             side_effect=GeminiError("AI_ERROR"))
        patcher.start()
        self.addCleanup(patcher.stop)

    def post(self, url, body=None):
        return self.client.post(url, data=json.dumps(body or {}), content_type="application/json")

    def start(self, difficulty="beginner"):
        with mock.patch("plays.api.gemini.generate_scenario", return_value=SCENARIO):
            res = self.post("/api/plays/", {"difficulty": difficulty})
        self.assertEqual(res.status_code, 201, res.content)
        return res.json()["play_id"]

    def turn(self, play_id, turn_no, delta=(5, -5, 10), text="おねがい"):
        with mock.patch("plays.api.gemini.generate_reply", return_value=reply(delta)):
            return self.post(f"/api/plays/{play_id}/turns/", {"text": text, "turn_no": turn_no})


class StartTest(MemberPlayTestBase):
    def test_start_saves_random_private_scenario_and_play(self):
        """お題はシナリオ（ランダム・非公開・作成者は本人）として保存され、プレイ中のプレイができる"""
        play_id = self.start("intermediate")
        play = Play.objects.get(pk=play_id)
        self.assertEqual(play.user, self.user)
        self.assertEqual(play.status, "playing")
        self.assertEqual(play.turn_limit, 12)
        self.assertEqual((play.mood, play.suspicion, play.understanding), (50, 50, 0))
        scenario = play.scenario
        self.assertEqual(scenario.kind, "random")
        self.assertEqual(scenario.difficulty, "intermediate")
        self.assertFalse(scenario.is_public)
        self.assertEqual(scenario.creator, self.user)
        self.assertIsNone(scenario.share_code)
        self.assertEqual(scenario.title, SCENARIO["title"])

    def test_start_returns_play_url(self):
        with mock.patch("plays.api.gemini.generate_scenario", return_value=SCENARIO):
            res = self.post("/api/plays/", {"difficulty": "beginner"})
        data = res.json()
        self.assertEqual(data["play_url"], f"/plays/{data['play_id']}/")

    def test_invalid_difficulty_is_rejected(self):
        for body in ({}, {"difficulty": "hard"}, {"difficulty": 1}):
            res = self.post("/api/plays/", body)
            self.assertEqual(res.status_code, 400)
            self.assertEqual(res.json()["error"]["code"], "BAD_REQUEST")
        self.assertFalse(Play.objects.exists())

    def test_previous_playing_is_aborted(self):
        """プレイ中があるときに新しく始めると、前のプレイは中断（終了日時あり、スコアなし）"""
        first = self.start()
        second = self.start()
        old = Play.objects.get(pk=first)
        self.assertEqual(old.status, "aborted")
        self.assertIsNotNone(old.finished_at)
        self.assertIsNone(old.score)
        self.assertEqual(Play.objects.get(pk=second).status, "playing")

    def test_generation_failure_keeps_previous_play(self):
        """お題の生成に失敗したら、前のプレイは中断にしない（②-a）"""
        first = self.start()
        with mock.patch("plays.api.gemini.generate_scenario", side_effect=GeminiError("AI_ERROR")):
            res = self.post("/api/plays/", {"difficulty": "beginner"})
        self.assertEqual(res.status_code, 502)
        self.assertEqual(res.json()["error"]["code"], "AI_ERROR")
        self.assertEqual(Play.objects.get(pk=first).status, "playing")
        self.assertEqual(Scenario.objects.count(), 1)

    def test_save_chat_log_is_copied_from_setting(self):
        UserSetting.objects.create(user=self.user, auto_save_chat=False)
        play_id = self.start()
        self.assertFalse(Play.objects.get(pk=play_id).save_chat_log)

    def test_save_chat_log_defaults_to_on_without_setting(self):
        """設定の行がない古いユーザーでも、初期値（ON）で始められる"""
        play_id = self.start()
        self.assertTrue(Play.objects.get(pk=play_id).save_chat_log)


class DetailTest(MemberPlayTestBase):
    def test_detail_hides_numbers(self):
        play_id = self.start()
        self.turn(play_id, 1)
        res = self.client.get(f"/api/plays/{play_id}/")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["turns_left"], 14)
        self.assertEqual(len(data["messages"]), 2)
        self.assertEqual(data["expression"], "happy")
        for forbidden in ("mood", "suspicion", "understanding", "delta", "score"):
            self.assertNotIn(forbidden, json.dumps(data))

    def test_text_speed_comes_from_setting(self):
        UserSetting.objects.create(user=self.user, text_speed="fast")
        play_id = self.start()
        self.assertEqual(self.client.get(f"/api/plays/{play_id}/").json()["text_speed"], "fast")

    def test_other_users_play_is_not_found(self):
        """他人のプレイは存在を隠して NOT_FOUND（IDOR対策）"""
        play_id = self.start()
        other = User.objects.create_user("b@example.com", "pass1234")
        self.client.force_login(other)
        for res in (
            self.client.get(f"/api/plays/{play_id}/"),
            self.turn(play_id, 1),
            self.post(f"/api/plays/{play_id}/give-up/"),
            self.post(f"/api/plays/{play_id}/abort/"),
        ):
            self.assertEqual(res.status_code, 404)
            self.assertEqual(res.json()["error"]["code"], "NOT_FOUND")
        self.assertEqual(Play.objects.get(pk=play_id).status, "playing")

    def test_unknown_id_is_not_found(self):
        for play_id in ("999", "abc"):
            self.assertEqual(self.client.get(f"/api/plays/{play_id}/").status_code, 404)


class TurnTest(MemberPlayTestBase):
    def test_turn_is_saved(self):
        play_id = self.start()
        res = self.turn(play_id, 1, delta=(30, -30, 10))  # ±15 に丸められる
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["turns_left"], 14)
        play = Play.objects.get(pk=play_id)
        self.assertEqual((play.mood, play.suspicion, play.understanding, play.turns_used), (65, 35, 10, 1))
        turn = PlayTurn.objects.get(play=play)
        self.assertEqual((turn.turn_no, turn.user_message, turn.ai_reply), (1, "おねがい", "うーん……"))
        self.assertEqual((turn.delta_mood, turn.delta_suspicion, turn.delta_understanding), (15, -15, 10))
        self.assertEqual((turn.mood_after, turn.suspicion_after, turn.understanding_after), (65, 35, 10))
        self.assertEqual((turn.state_text, turn.expression, turn.reason), ("迷っている", "happy", "理由"))

    def test_history_is_passed_to_ai(self):
        """2ターン目には、1ターン目の会話がサーバーから渡される"""
        play_id = self.start()
        self.turn(play_id, 1, text="はじめまして")
        with mock.patch("plays.api.gemini.generate_reply", return_value=reply()) as gen:
            self.post(f"/api/plays/{play_id}/turns/", {"text": "つぎ", "turn_no": 2})
        history = gen.call_args.args[2]
        self.assertEqual(history, [{"role": "user", "text": "はじめまして"}, {"role": "model", "text": "うーん……"}])

    def test_turn_mismatch_returns_current_state(self):
        play_id = self.start()
        self.turn(play_id, 1)
        res = self.turn(play_id, 1)  # 二重送信
        self.assertEqual(res.status_code, 409)
        self.assertEqual(res.json()["error"]["code"], "TURN_MISMATCH")
        self.assertEqual(res.json()["play"]["turns_left"], 14)
        self.assertEqual(PlayTurn.objects.count(), 1)

    def test_too_long_message_is_rejected(self):
        play_id = self.start()
        res = self.turn(play_id, 1, text="あ" * 121)
        self.assertEqual(res.status_code, 400)
        self.assertFalse(PlayTurn.objects.exists())

    def test_blocked_does_not_consume_turn(self):
        play_id = self.start()
        with mock.patch("plays.api.gemini.generate_reply", side_effect=GeminiError("BLOCKED")):
            res = self.post(f"/api/plays/{play_id}/turns/", {"text": "ひどいこと", "turn_no": 1})
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["error"]["code"], "BLOCKED")
        self.assertEqual(Play.objects.get(pk=play_id).turns_used, 0)

    def test_ai_error_does_not_consume_turn(self):
        play_id = self.start()
        with mock.patch("plays.api.gemini.generate_reply", return_value=reply(delta=("x", 0, 0))):
            res = self.post(f"/api/plays/{play_id}/turns/", {"text": "こんにちは", "turn_no": 1})
        self.assertEqual(res.status_code, 502)
        self.assertEqual(res.json()["error"]["code"], "AI_ERROR")
        self.assertFalse(PlayTurn.objects.exists())

    def test_clear_saves_score_and_finished_at(self):
        play_id = self.start()  # 初級：機嫌70・理解度70以上、疑い30以下
        for no in range(1, 6):
            res = self.turn(play_id, no, delta=(5, -5, 15))
        data = res.json()
        self.assertEqual(data["status"], "cleared")
        self.assertEqual(data["result_url"], f"/plays/{play_id}/result/")
        play = Play.objects.get(pk=play_id)
        self.assertEqual(play.status, "cleared")
        self.assertGreater(play.score, 0)
        self.assertIsNotNone(play.finished_at)
        # クリアしたプレイには、もう発言できない
        self.assertEqual(self.turn(play_id, 6).json()["error"]["code"], "NOT_PLAYING")

    def test_running_out_of_turns_fails_with_zero(self):
        play_id = self.start("advanced")  # 10ターン
        for no in range(1, 11):
            res = self.turn(play_id, no, delta=(0, 0, 0))
        self.assertEqual(res.json()["status"], "failed")
        play = Play.objects.get(pk=play_id)
        self.assertEqual((play.status, play.score), ("failed", 0))
        self.assertIsNotNone(play.finished_at)


class ChatLogOffTest(MemberPlayTestBase):
    """自動保存OFF：プレイ中は会話を持ち、終わったら消す（スコア・様子は残す）"""

    def setUp(self):
        super().setUp()
        UserSetting.objects.create(user=self.user, auto_save_chat=False)

    def test_log_is_kept_while_playing_and_removed_when_finished(self):
        play_id = self.start()
        self.turn(play_id, 1)
        turn = PlayTurn.objects.get(play_id=play_id)
        self.assertEqual(turn.user_message, "おねがい")  # プレイ中は再開できるように持つ
        self.post(f"/api/plays/{play_id}/give-up/")
        turn.refresh_from_db()
        self.assertIsNone(turn.user_message)
        self.assertIsNone(turn.ai_reply)
        self.assertEqual(turn.state_text, "迷っている")  # 様子は残す
        self.assertEqual(Play.objects.get(pk=play_id).score, 0)

    def test_log_is_removed_when_cleared(self):
        play_id = self.start()
        for no in range(1, 6):
            self.turn(play_id, no, delta=(5, -5, 15))
        self.assertFalse(PlayTurn.objects.filter(play_id=play_id, user_message__isnull=False).exists())

    def test_log_is_removed_when_aborted_by_new_play(self):
        play_id = self.start()
        self.turn(play_id, 1)
        self.start()
        self.assertFalse(PlayTurn.objects.filter(play_id=play_id, ai_reply__isnull=False).exists())

    def test_log_is_kept_when_setting_is_on(self):
        UserSetting.objects.filter(user=self.user).update(auto_save_chat=True)
        play_id = self.start()
        self.turn(play_id, 1)
        self.post(f"/api/plays/{play_id}/give-up/")
        self.assertEqual(PlayTurn.objects.get(play_id=play_id).user_message, "おねがい")


class GiveUpAbortTest(MemberPlayTestBase):
    def test_give_up(self):
        play_id = self.start()
        res = self.post(f"/api/plays/{play_id}/give-up/")
        self.assertEqual(res.json()["result_url"], f"/plays/{play_id}/result/")
        play = Play.objects.get(pk=play_id)
        self.assertEqual((play.status, play.score), ("failed", 0))
        self.assertIsNotNone(play.finished_at)

    def test_abort(self):
        play_id = self.start()
        res = self.post(f"/api/plays/{play_id}/abort/")
        self.assertEqual(res.json()["redirect_url"], "/")
        play = Play.objects.get(pk=play_id)
        self.assertEqual(play.status, "aborted")
        self.assertIsNone(play.score)
        self.assertIsNotNone(play.finished_at)

    def test_finished_play_is_not_changed(self):
        play_id = self.start()
        self.post(f"/api/plays/{play_id}/give-up/")
        for url in (f"/api/plays/{play_id}/give-up/", f"/api/plays/{play_id}/abort/"):
            res = self.post(url)
            self.assertEqual(res.status_code, 409)
            self.assertEqual(res.json()["error"]["code"], "NOT_PLAYING")
        self.assertEqual(Play.objects.get(pk=play_id).status, "failed")


class TopPageTest(MemberPlayTestBase):
    def test_greeting_uses_username(self):
        res = self.client.get("/", HTTP_HOST="localhost")
        self.assertContains(res, "おかえり、たろうさん")
