"""game.py のテスト（設計書の数値どおりに動くか確認する）"""
from unittest import TestCase

from .game import (
    CLEARED, FAILED, PLAYING, State, calculate_score, clamp_delta,
    get_rules, is_cleared, process_turn,
)


def d(mood=0, suspicion=0, understanding=0):
    """テスト用：増減値の dict を手短に作る"""
    return {"mood": mood, "suspicion": suspicion, "understanding": understanding}


class RulesTest(TestCase):
    """難易度ごとの設定と初期値"""

    def test_rules_per_difficulty(self):
        """設計書【難易度ごとの設定】の数値と一致する（大文字小文字は問わない）"""
        b, i, a = get_rules("beginner"), get_rules("INTERMEDIATE"), get_rules("advanced")
        self.assertEqual((b.turn_limit, b.clear_mood, b.clear_understanding, b.clear_suspicion), (15, 70, 70, 30))
        self.assertEqual((i.turn_limit, i.clear_mood, i.clear_understanding, i.clear_suspicion), (12, 75, 75, 25))
        self.assertEqual((a.turn_limit, a.clear_mood, a.clear_understanding, a.clear_suspicion), (10, 80, 80, 20))

    def test_unknown_difficulty_raises(self):
        """知らない難易度名は ValueError"""
        with self.assertRaises(ValueError):
            get_rules("expert")

    def test_initial_values(self):
        """初期値は 機嫌50・疑い50・理解度0・使用ターン0"""
        s = State()
        self.assertEqual((s.mood, s.suspicion, s.understanding, s.turns_used), (50, 50, 0, 0))


class DeltaTest(TestCase):
    """AIの増減値の丸め"""

    def test_delta_is_clamped_to_15(self):
        """±15を超える値は ±15 に丸める"""
        self.assertEqual(clamp_delta(99), 15)
        self.assertEqual(clamp_delta(-99), -15)
        self.assertEqual(clamp_delta(7), 7)

    def test_non_int_delta_raises(self):
        """整数以外（文字列・小数・None・真偽値）は ValueError"""
        for bad in ("5", 5.0, None, True):
            with self.assertRaises(ValueError):
                clamp_delta(bad)


class ClearTest(TestCase):
    """クリア条件の境界値"""

    def test_clear_boundaries_beginner(self):
        """初級：ちょうどの値はクリア、1つでも足りなければ未クリア"""
        r = get_rules("beginner")
        self.assertTrue(is_cleared(State(70, 30, 70), r))
        self.assertFalse(is_cleared(State(69, 30, 70), r))  # 機嫌が1足りない
        self.assertFalse(is_cleared(State(70, 31, 70), r))  # 疑いが1高い
        self.assertFalse(is_cleared(State(70, 30, 69), r))  # 理解度が1足りない

    def test_clear_boundaries_advanced(self):
        """上級：80以上・80以上・20以下"""
        r = get_rules("advanced")
        self.assertTrue(is_cleared(State(80, 20, 80), r))
        self.assertFalse(is_cleared(State(79, 20, 80), r))


class ScoreTest(TestCase):
    """スコア計算（手計算した値と照合する）"""

    def test_score_beginner(self):
        """基本点 70+84+105=259 / ボーナス 10/15*300=200 / 係数1.0 → 459"""
        s = State(70, 30, 70, turns_used=5)
        self.assertEqual(calculate_score(s, get_rules("beginner")), 459)

    def test_score_intermediate_floors_decimals(self):
        """基本点 75+90+112.5=277.5 / ボーナス 150 / 427.5×1.5=641.25 → 切り捨てて641"""
        s = State(75, 25, 75, turns_used=6)
        self.assertEqual(calculate_score(s, get_rules("intermediate")), 641)

    def test_score_advanced(self):
        """基本点 80+96+120=296 / ボーナス 6/10*300=180 / 476×2=952"""
        s = State(80, 20, 80, turns_used=4)
        self.assertEqual(calculate_score(s, get_rules("advanced")), 952)

    def test_score_examples_in_test_spec(self):
        """ユースケース記述テスト仕様書 07「スコア計算」の2例"""
        beginner = State(80, 20, 75, turns_used=5)   # 残り10ターン
        self.assertEqual(calculate_score(beginner, get_rules("beginner")), 490)
        advanced = State(85, 10, 90, turns_used=5)   # 残り5ターン
        self.assertEqual(calculate_score(advanced, get_rules("advanced")), 956)

    def test_score_max_is_1340(self):
        """上級で全パラメータが満点・ターンを使い切っていない場合の最大値は1340"""
        self.assertEqual(calculate_score(State(100, 0, 100, 0), get_rules("advanced")), 1340)


class ProcessTurnTest(TestCase):
    """1ターンの処理（加算・丸め・判定）"""

    def test_turn_applies_delta_and_advances(self):
        """増減が加算され、使用ターンが1進み、まだプレイ中"""
        res = process_turn(State(), d(10, -5, 8), get_rules("beginner"))
        self.assertEqual((res.state.mood, res.state.suspicion, res.state.understanding), (60, 45, 8))
        self.assertEqual(res.state.turns_used, 1)
        self.assertEqual(res.status, PLAYING)
        self.assertEqual(res.remaining_turns, 14)
        self.assertIsNone(res.score)  # プレイ中はスコアなし

    def test_ai_delta_is_clamped_and_recorded(self):
        """AIが±99を返しても±15に丸められ、丸めた値が記録される"""
        res = process_turn(State(), d(99, -99, 40), get_rules("beginner"))
        self.assertEqual(res.delta, d(15, -15, 15))
        self.assertEqual((res.state.mood, res.state.suspicion, res.state.understanding), (65, 35, 15))

    def test_params_stay_within_0_to_100(self):
        """加算しても 0〜100 の範囲に収まる"""
        res = process_turn(State(95, 5, 98), d(15, -15, 15), get_rules("beginner"))
        self.assertEqual((res.state.mood, res.state.suspicion, res.state.understanding), (100, 0, 100))
        res = process_turn(State(5, 95, 2), d(-15, 15, -15), get_rules("beginner"))
        self.assertEqual((res.state.mood, res.state.suspicion, res.state.understanding), (0, 100, 0))

    def test_cleared_when_conditions_met_with_score(self):
        """条件を満たすとクリアになり、スコアが計算される"""
        res = process_turn(State(65, 35, 65, turns_used=4), d(10, -10, 10), get_rules("beginner"))
        self.assertEqual(res.status, CLEARED)
        self.assertEqual(res.remaining_turns, 10)
        self.assertEqual(res.score, calculate_score(res.state, get_rules("beginner")))

    def test_failed_with_zero_score_when_turns_run_out(self):
        """条件未達でターンが尽きると失敗（0点）"""
        res = process_turn(State(turns_used=14), d(), get_rules("beginner"))
        self.assertEqual((res.status, res.remaining_turns, res.score), (FAILED, 0, 0))

    def test_clear_on_last_turn_takes_priority(self):
        """最終ターンでも、クリア条件を満たしていればクリアが優先される"""
        # 上級の条件(80/20/80)に届かないので、最終ターンは失敗
        res = process_turn(State(65, 35, 65, turns_used=9), d(10, -10, 10), get_rules("advanced"))
        self.assertEqual(res.status, FAILED)
        # 条件に届く場合は、残りターンが0でもクリア
        res = process_turn(State(75, 25, 75, turns_used=9), d(10, -10, 10), get_rules("advanced"))
        self.assertEqual(res.status, CLEARED)
        self.assertEqual(res.remaining_turns, 0)

    def test_invalid_delta_raises(self):
        """増減が整数でなければ ValueError（呼び出し側で AI_ERROR にする）"""
        with self.assertRaises(ValueError):
            process_turn(State(), {"mood": "5", "suspicion": 0, "understanding": 0}, get_rules("beginner"))
