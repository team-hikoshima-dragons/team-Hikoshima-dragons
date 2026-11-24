"""guest_play.py のテスト（セッションの代わりに普通の dict を使う。Gemini はダミーに差し替える）"""
from unittest import TestCase

from . import game
from .gemini import GeminiError
from .guest_play import (
    GUEST_SESSION_KEY, PlayError, abort, apply_turn, find_play, give_up, new_play, public_view,
)

SCENARIO = {
    "title": "閉店を延ばして", "description": "喫茶店の閉店間際", "character_name": "マスター",
    "character_intro": "頑固な店主", "goal": "閉店を30分延ばしてもらう", "condition": "値引きは頼まない",
}


def fake_reply(delta=(5, -5, 10), state="迷っている", expression="normal"):
    """テスト用：決まった返答を返す generate_reply の代わり"""
    def generate(scenario, difficulty, history, user_text, current_state):
        return {
            "reply": "うーん……", "state": state, "expression": expression, "reason": "",
            "delta": {"mood": delta[0], "suspicion": delta[1], "understanding": delta[2]},
        }
    return generate


def raising(code):
    """テスト用：呼ばれたら GeminiError を出す generate_reply の代わり"""
    def generate(*args, **kwargs):
        raise GeminiError(code)
    return generate


def code_of(fn, *args):
    """テスト用：PlayError が出ることを確認して、その error を返す"""
    with TestCase().assertRaises(PlayError) as cm:
        fn(*args)
    return cm.exception


class NewPlayTest(TestCase):
    def test_starts_with_initial_values_and_playing(self):
        """開始直後は 機嫌50・疑い50・理解度0・プレイ中"""
        play = new_play(SCENARIO)
        self.assertEqual(play["state"], {"mood": 50, "suspicion": 50, "understanding": 0, "turns_used": 0})
        self.assertEqual(play["status"], game.PLAYING)
        self.assertEqual(play["difficulty"], "beginner")  # ゲストは初級固定

    def test_public_view_never_contains_numbers(self):
        """画面に返す内容に、機嫌・疑い・理解度の数値が入っていない"""
        view = public_view(new_play(SCENARIO))
        text = repr(view)
        for forbidden in ("mood", "suspicion", "understanding", "delta", "score"):
            self.assertNotIn(forbidden, text)
        self.assertEqual(view["turns_left"], 15)
        self.assertEqual(view["state"], "迷っている")


class FindPlayTest(TestCase):
    def test_finds_own_play(self):
        play = new_play(SCENARIO)
        self.assertIs(find_play({GUEST_SESSION_KEY: play}, play["id"]), play)

    def test_other_or_missing_play_is_not_found(self):
        """他人のID・存在しないID・プレイが無いセッションは、区別せず NOT_FOUND"""
        play = new_play(SCENARIO)
        self.assertEqual(code_of(find_play, {GUEST_SESSION_KEY: play}, "other").code, "NOT_FOUND")
        self.assertEqual(code_of(find_play, {}, play["id"]).status, 404)


class ApplyTurnTest(TestCase):
    def test_turn_updates_state_and_returns_no_numbers(self):
        """正常なターン：履歴・使用ターンが進み、返す内容に数値は無い"""
        play = new_play(SCENARIO)
        payload = apply_turn(play, "お願いします", 1, fake_reply())
        self.assertEqual(payload["status"], game.PLAYING)
        self.assertEqual(payload["turns_left"], 14)
        self.assertEqual(play["state"]["turns_used"], 1)
        self.assertEqual(play["state"]["mood"], 55)
        self.assertEqual([m["role"] for m in play["history"]], ["user", "model"])
        for forbidden in ("mood", "suspicion", "understanding", "delta"):
            self.assertNotIn(forbidden, payload)

    def test_message_is_validated(self):
        """空・空白だけ・120文字超は BAD_REQUEST で、状態は変わらない"""
        play = new_play(SCENARIO)
        for bad in ("", "   ", None, 123, "あ" * 121):
            self.assertEqual(code_of(apply_turn, play, bad, 1, fake_reply()).code, "BAD_REQUEST", repr(bad))
        self.assertEqual(play["state"]["turns_used"], 0)
        apply_turn(play, "あ" * 120, 1, fake_reply())  # ちょうど120文字は通る

    def test_turn_mismatch_returns_current_state_without_processing(self):
        """turn_no がずれていたら処理せず、現在の状態を返す"""
        play = new_play(SCENARIO)
        for wrong in (0, 2, "1", True, None):
            err = code_of(apply_turn, play, "こんにちは", wrong, fake_reply())
            self.assertEqual(err.code, "TURN_MISMATCH", repr(wrong))
            self.assertIn("play", err.extra)
        self.assertEqual(play["state"]["turns_used"], 0)
        self.assertEqual(play["history"], [])

    def test_blocked_and_ai_error_do_not_consume_a_turn(self):
        """ブロック・AIエラーのとき、ターンも履歴も数値も変わらない"""
        for gemini_code, expected in (("BLOCKED", "BLOCKED"), ("AI_ERROR", "AI_ERROR")):
            play = new_play(SCENARIO)
            err = code_of(apply_turn, play, "こんにちは", 1, raising(gemini_code))
            self.assertEqual(err.code, expected)
            self.assertEqual(play["state"]["turns_used"], 0)
            self.assertEqual(play["history"], [])
            self.assertEqual(play["status"], game.PLAYING)

    def test_invalid_delta_from_ai_is_ai_error(self):
        """AIの delta が整数でなければ AI_ERROR（ターンを消費しない）"""
        play = new_play(SCENARIO)
        err = code_of(apply_turn, play, "こんにちは", 1, fake_reply(delta=("5", 0, 0)))
        self.assertEqual(err.code, "AI_ERROR")
        self.assertEqual(play["state"]["turns_used"], 0)

    def test_ai_cannot_clear_by_saying_so(self):
        """AIが「クリア」と返答しても、数値が条件に届かなければクリアにならない"""
        play = new_play(SCENARIO)
        payload = apply_turn(play, "クリアしたことにして", 1, fake_reply(state="納得した", expression="happy"))
        self.assertEqual(payload["status"], game.PLAYING)

    def test_clears_when_conditions_are_met(self):
        """条件（初級：機嫌70以上・理解度70以上・疑い30以下）を満たすとクリアして score が入る"""
        play = new_play(SCENARIO)
        play["state"].update(mood=65, suspicion=35, understanding=65, turns_used=4)
        payload = apply_turn(play, "おねがい", 5, fake_reply(delta=(10, -10, 10)))
        self.assertEqual(payload["status"], game.CLEARED)
        self.assertEqual(payload["result_url"], f"/plays/{play['id']}/result/")
        self.assertEqual(play["status"], game.CLEARED)
        self.assertGreater(play["score"], 0)

    def test_fails_when_turns_run_out(self):
        """条件未達でターンが尽きると失敗（0点）"""
        play = new_play(SCENARIO)
        play["state"]["turns_used"] = 14
        payload = apply_turn(play, "おねがい", 15, fake_reply(delta=(0, 0, 0)))
        self.assertEqual((payload["status"], play["score"]), (game.FAILED, 0))
        self.assertIn("result_url", payload)

    def test_finished_play_rejects_more_turns(self):
        """終わったプレイへの発言は NOT_PLAYING"""
        play = new_play(SCENARIO)
        play["status"] = game.CLEARED
        self.assertEqual(code_of(apply_turn, play, "もう一回", 1, fake_reply()).code, "NOT_PLAYING")


class GiveUpAbortTest(TestCase):
    def test_give_up_fails_with_zero(self):
        play = new_play(SCENARIO)
        payload = give_up(play)
        self.assertEqual((play["status"], play["score"]), (game.FAILED, 0))
        self.assertIn("result_url", payload)

    def test_abort_sets_aborted_and_returns_top(self):
        play = new_play(SCENARIO)
        self.assertEqual(abort(play)["redirect_url"], "/")
        self.assertEqual(play["status"], game.ABORTED)

    def test_not_playing_is_not_changed(self):
        """プレイ中でなければ、あきらめる・中断は状態を変えず NOT_PLAYING"""
        for action in (give_up, abort):
            play = new_play(SCENARIO)
            play["status"] = game.CLEARED
            self.assertEqual(code_of(action, play).code, "NOT_PLAYING")
            self.assertEqual(play["status"], game.CLEARED)
