"""gemini.py の「応答の検証」部分のテスト（ネットワークは使わない）"""
from unittest import TestCase

from .gemini import (
    GeminiError, extract_text, parse_json, validate_scenario, validate_turn,
)


def good_turn(**over):
    """テスト用：正しいターン応答を作る。over で一部の項目だけ差し替えられる"""
    data = {
        "reply": "ふん、そこまで言うなら聞いてやる。",
        "delta": {"mood": 5, "suspicion": -3, "understanding": 8},
        "state": "心が動いている",
        "expression": "happy",
        "reason": "具体的な提案があったから",
    }
    data.update(over)
    return data


def code_of(fn, *args):
    """テスト用：fn が GeminiError を出すことを確認し、その code を返す"""
    with TestCase().assertRaises(GeminiError) as cm:
        fn(*args)
    return cm.exception.code


class ValidateTurnTest(TestCase):
    """ターン応答の検証"""

    def test_valid(self):
        """正しい応答はそのまま通る"""
        out = validate_turn(good_turn())
        self.assertEqual(out["delta"], {"mood": 5, "suspicion": -3, "understanding": 8})
        self.assertEqual(out["expression"], "happy")

    def test_missing_key_is_ai_error(self):
        """必須キー（reply・delta・state）が欠けたら AI_ERROR"""
        for key in ("reply", "delta", "state"):
            data = good_turn()
            del data[key]
            self.assertEqual(code_of(validate_turn, data), "AI_ERROR", key)

    def test_non_int_delta_is_ai_error(self):
        """delta が整数でなければ AI_ERROR（文字列・小数・None・真偽値）"""
        for bad in ("5", 5.5, None, True):
            data = good_turn(delta={"mood": bad, "suspicion": 0, "understanding": 0})
            self.assertEqual(code_of(validate_turn, data), "AI_ERROR", repr(bad))

    def test_missing_delta_key_is_ai_error(self):
        """delta の中のキーが欠けたら AI_ERROR"""
        self.assertEqual(code_of(validate_turn, good_turn(delta={"mood": 1})), "AI_ERROR")

    def test_unknown_expression_becomes_normal(self):
        """想定外の表情はエラーにせず normal にする"""
        self.assertEqual(validate_turn(good_turn(expression="sad"))["expression"], "normal")
        self.assertEqual(validate_turn(good_turn(expression=None))["expression"], "normal")

    def test_long_text_is_truncated(self):
        """長すぎる文字列は上限で切り詰める（state は100字）"""
        out = validate_turn(good_turn(state="あ" * 500, reply="い" * 1000))
        self.assertEqual(len(out["state"]), 100)
        self.assertLessEqual(len(out["reply"]), 300)

    def test_reason_is_optional(self):
        """reason（解説用）は無くてもエラーにしない"""
        data = good_turn()
        del data["reason"]
        self.assertEqual(validate_turn(data)["reason"], "")


class ValidateScenarioTest(TestCase):
    """お題（シナリオ）応答の検証"""

    def test_title_40_and_name_50_are_truncated(self):
        """タイトルは40字、キャラ名は50字に切り詰める"""
        data = {k: "x" for k in ("description", "character_intro", "goal", "condition")}
        data.update(title="あ" * 80, character_name="い" * 80)
        out = validate_scenario(data)
        self.assertEqual(len(out["title"]), 40)
        self.assertEqual(len(out["character_name"]), 50)

    def test_missing_key_is_ai_error(self):
        """必須キーが欠けたら AI_ERROR"""
        self.assertEqual(code_of(validate_scenario, {"title": "t"}), "AI_ERROR")


class ExtractTextTest(TestCase):
    """Gemini の応答から本文を取り出す処理"""

    def test_valid(self):
        """正常な応答から本文が取れる"""
        res = {"candidates": [{"content": {"parts": [{"text": '{"a":1}'}]}, "finishReason": "STOP"}]}
        self.assertEqual(extract_text(res), '{"a":1}')

    def test_blocked_prompt_is_blocked(self):
        """入力がブロックされたら BLOCKED（ターンを消費しない）"""
        self.assertEqual(code_of(extract_text, {"promptFeedback": {"blockReason": "SAFETY"}}), "BLOCKED")

    def test_safety_finish_is_blocked(self):
        """出力がセーフティで止められたら BLOCKED"""
        res = {"candidates": [{"finishReason": "SAFETY"}]}
        self.assertEqual(code_of(extract_text, res), "BLOCKED")

    def test_no_candidates_or_empty_text_is_ai_error(self):
        """候補が無い・本文が空なら AI_ERROR"""
        self.assertEqual(code_of(extract_text, {}), "AI_ERROR")
        res = {"candidates": [{"content": {"parts": [{"text": "  "}]}}]}
        self.assertEqual(code_of(extract_text, res), "AI_ERROR")


class ParseJsonTest(TestCase):
    """本文のJSON読み込み"""

    def test_valid_and_code_fence(self):
        """普通のJSONと、```json で囲まれたJSONの両方を読める"""
        self.assertEqual(parse_json('{"a": 1}'), {"a": 1})
        self.assertEqual(parse_json('```json\n{"a": 1}\n```'), {"a": 1})

    def test_non_json_or_non_object_is_ai_error(self):
        """JSONでない、またはオブジェクトでない場合は AI_ERROR"""
        self.assertEqual(code_of(parse_json, "こんにちは"), "AI_ERROR")
        self.assertEqual(code_of(parse_json, "[1, 2]"), "AI_ERROR")
