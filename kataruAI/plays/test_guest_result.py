"""guest_play.py の「開始・終了時刻」と「リザルト用データ」のテスト（Django なしで動く）"""
from datetime import datetime, timedelta, timezone
from unittest import TestCase

from . import game
from .guest_play import apply_turn, give_up, new_play, result_view

SCENARIO = {
    "title": "閉店を延ばして", "description": "喫茶店の閉店間際", "character_name": "マスター",
    "character_intro": "頑固な店主", "goal": "閉店を30分延ばしてもらう", "condition": "値引きは頼まない",
}
START = datetime(2026, 11, 24, 12, 0, 0, tzinfo=timezone.utc)


def fake_reply(delta):
    """テスト用：決まった増減を返す generate_reply の代わり"""
    def generate(scenario, difficulty, history, user_text, state):
        return {
            "reply": "……わかった", "state": "納得した", "expression": "happy", "reason": "",
            "delta": {"mood": delta[0], "suspicion": delta[1], "understanding": delta[2]},
        }
    return generate


class TimeTest(TestCase):
    def test_start_time_is_recorded(self):
        """開始時刻が記録され、終了時刻はまだ空"""
        play = new_play(SCENARIO, now=START)
        self.assertEqual(play["started_at"], START.isoformat())
        self.assertIsNone(play["finished_at"])

    def test_no_time_recorded_when_now_is_omitted(self):
        """時刻を渡さなければ記録しない（従来どおり動く）"""
        play = new_play(SCENARIO)
        self.assertIsNone(play["started_at"])

    def test_finish_time_is_recorded_on_clear(self):
        """クリアしたとき終了時刻が入る"""
        play = new_play(SCENARIO, now=START)
        play["state"].update(mood=65, suspicion=35, understanding=65, turns_used=4)
        end = START + timedelta(seconds=83)
        apply_turn(play, "おねがい", 5, fake_reply((10, -10, 10)), now=end)
        self.assertEqual(play["finished_at"], end.isoformat())

    def test_finish_time_is_recorded_on_give_up(self):
        play = new_play(SCENARIO, now=START)
        end = START + timedelta(seconds=10)
        give_up(play, now=end)
        self.assertEqual(play["finished_at"], end.isoformat())


class ResultViewTest(TestCase):
    def cleared_play(self, seconds=83):
        play = new_play(SCENARIO, now=START)
        play["state"].update(mood=65, suspicion=35, understanding=65, turns_used=4)
        apply_turn(play, "おねがい", 5, fake_reply((10, -10, 10)), now=START + timedelta(seconds=seconds))
        return play

    def test_cleared_result(self):
        """クリア：スコア・ターン数・「1:23」（分:秒）の形のクリアタイムが入る"""
        r = result_view(self.cleared_play(83))
        self.assertTrue(r["cleared"])
        self.assertGreater(r["score"], 0)
        self.assertEqual((r["turns_used"], r["turn_limit"]), (5, 15))
        self.assertEqual(r["clear_time_text"], "1:23")
        self.assertEqual(r["difficulty_label"], "初級")
        self.assertEqual(r["face_path"], "img/face-happy.svg")

    def test_failed_result_has_zero_score_and_no_clear_time(self):
        """失敗：0点で、クリアタイムは「—」"""
        play = new_play(SCENARIO, now=START)
        give_up(play, now=START + timedelta(seconds=30))
        r = result_view(play)
        self.assertFalse(r["cleared"])
        self.assertEqual((r["score"], r["clear_time_text"]), (0, "—"))
        self.assertEqual(r["face_path"], "img/face-angry.svg")  # 失敗は怒り顔

    def test_clear_time_pads_seconds(self):
        """秒は2桁にそろえる（4分5秒 → 4:05）"""
        self.assertEqual(result_view(self.cleared_play(245))["clear_time_text"], "4:05")

    def test_clear_time_is_dash_without_timestamps(self):
        """時刻が記録されていなければ「—」"""
        play = new_play(SCENARIO)
        play["state"].update(mood=65, suspicion=35, understanding=65, turns_used=4)
        apply_turn(play, "おねがい", 5, fake_reply((10, -10, 10)))
        self.assertEqual(result_view(play)["clear_time_text"], "—")

    def test_result_has_no_hidden_numbers(self):
        """リザルト用データに、機嫌・疑い・理解度の数値は入らない"""
        text = repr(result_view(self.cleared_play()))
        for forbidden in ("mood", "suspicion", "understanding", "delta"):
            self.assertNotIn(forbidden, text)
