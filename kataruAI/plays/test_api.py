"""api.py のテスト（Django のテストクライアントを使う）

Gemini は本物を呼ばず、unittest.mock で差し替える。
実行：docker compose exec web python manage.py test plays
"""
import json
from unittest import mock

from django.test import TestCase

from .gemini import GeminiError

SCENARIO = {
    "title": "閉店を延ばして", "description": "喫茶店の閉店間際", "character_name": "マスター",
    "character_intro": "頑固な店主", "goal": "閉店を30分延ばしてもらう", "condition": "値引きは頼まない",
}


def reply(delta=(5, -5, 10)):
    """テスト用：決まった返答"""
    return {
        "reply": "うーん……", "state": "迷っている", "expression": "normal", "reason": "",
        "delta": {"mood": delta[0], "suspicion": delta[1], "understanding": delta[2]},
    }


class ApiTest(TestCase):
    def post(self, url, body=None):
        return self.client.post(url, data=json.dumps(body or {}), content_type="application/json")

    def start_play(self):
        """テスト用：プレイを開始して play_id を返す"""
        with mock.patch("plays.api.gemini.generate_scenario", return_value=SCENARIO):
            res = self.post("/api/plays/")
        self.assertEqual(res.status_code, 201)
        return res.json()["play_id"]

    def test_start_creates_play(self):
        play_id = self.start_play()
        res = self.client.get(f"/api/plays/{play_id}/")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["turns_left"], 15)
        self.assertEqual(data["status"], "playing")
        for forbidden in ("mood", "suspicion", "understanding", "delta", "score"):
            self.assertNotIn(forbidden, json.dumps(data))  # 数値は返さない

    def test_start_failure_returns_ai_error(self):
        with mock.patch("plays.api.gemini.generate_scenario", side_effect=GeminiError("AI_ERROR")):
            res = self.post("/api/plays/")
        self.assertEqual(res.status_code, 502)
        self.assertEqual(res.json()["error"]["code"], "AI_ERROR")

    def test_turn_flow(self):
        play_id = self.start_play()
        with mock.patch("plays.api.gemini.generate_reply", return_value=reply()):
            res = self.post(f"/api/plays/{play_id}/turns/", {"text": "おねがい", "turn_no": 1})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["turns_left"], 14)

    def test_turn_mismatch_returns_409_with_current_state(self):
        play_id = self.start_play()
        res = self.post(f"/api/plays/{play_id}/turns/", {"text": "おねがい", "turn_no": 5})
        self.assertEqual(res.status_code, 409)
        self.assertEqual(res.json()["error"]["code"], "TURN_MISMATCH")
        self.assertIn("play", res.json())

    def test_blocked_returns_400(self):
        play_id = self.start_play()
        with mock.patch("plays.api.gemini.generate_reply", side_effect=GeminiError("BLOCKED")):
            res = self.post(f"/api/plays/{play_id}/turns/", {"text": "こんにちは", "turn_no": 1})
        self.assertEqual((res.status_code, res.json()["error"]["code"]), (400, "BLOCKED"))

    def test_other_session_gets_not_found(self):
        """別のセッション（別の人）からは、存在を隠して NOT_FOUND"""
        play_id = self.start_play()
        other = self.client_class()
        res = other.get(f"/api/plays/{play_id}/")
        self.assertEqual((res.status_code, res.json()["error"]["code"]), (404, "NOT_FOUND"))

    def test_give_up_then_not_playing(self):
        play_id = self.start_play()
        res = self.post(f"/api/plays/{play_id}/give-up/")
        self.assertEqual(res.status_code, 200)
        self.assertIn("result_url", res.json())
        res = self.post(f"/api/plays/{play_id}/give-up/")
        self.assertEqual((res.status_code, res.json()["error"]["code"]), (409, "NOT_PLAYING"))

    def test_abort_returns_top(self):
        play_id = self.start_play()
        res = self.post(f"/api/plays/{play_id}/abort/")
        self.assertEqual(res.json()["redirect_url"], "/")

    def test_wrong_method_is_rejected(self):
        play_id = self.start_play()
        self.assertEqual(self.client.get(f"/api/plays/{play_id}/turns/").status_code, 405)

    def test_csrf_is_enforced(self):
        """CSRFトークンなしのPOSTは拒否される（@csrf_exempt を使っていない確認）"""
        from django.test import Client
        strict = Client(enforce_csrf_checks=True)
        res = strict.post("/api/plays/", data="{}", content_type="application/json")
        self.assertEqual(res.status_code, 403)
