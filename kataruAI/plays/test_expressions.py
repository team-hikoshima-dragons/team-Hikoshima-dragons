"""表情差分 SVG（生成・サニタイズ・保存・表示）のテスト

ユースケース記述テスト仕様書 07「表情SVGのサニタイズ」：script 要素・on〜属性・外部参照を除去する。
"""
import base64
import json
from unittest import TestCase as PlainTestCase
from unittest import mock

from django.test import TestCase

from accounts.models import User
from scenarios.models import ScenarioExpression

from . import gemini
from .gemini import GeminiError
from .svg_sanitize import sanitize_svg, to_data_url

SCENARIO = {
    "title": "閉店を延ばして", "description": "喫茶店の閉店間際", "character_name": "マスター",
    "character_intro": "頑固な店主", "goal": "閉店を30分延ばしてもらう", "condition": "値引きは頼まない",
}
FACE = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><circle cx="50" cy="50" r="40" fill="#ffcc99"/></svg>'
EXPRESSIONS = {name: FACE.replace("#ffcc99", color) for name, color in
               (("normal", "#ffcc99"), ("happy", "#ffdd88"), ("angry", "#ff8888"), ("doubt", "#ccbbff"))}


class SanitizeTest(PlainTestCase):
    def test_keeps_shapes_and_safe_attributes(self):
        svg = sanitize_svg(FACE)
        self.assertIn("<circle", svg)
        self.assertIn('fill="#ffcc99"', svg)
        self.assertIn('viewBox="0 0 100 100"', svg)

    def test_removes_script_event_handlers_and_external_refs(self):
        dirty = (
            '<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
            'viewBox="0 0 100 100" onload="alert(1)">'
            '<script>alert(1)</script>'
            '<image href="https://evil.example/x.png" xlink:href="https://evil.example/x.png"/>'
            '<use href="#a"/><foreignObject><div>x</div></foreignObject><style>*{}</style>'
            '<circle cx="50" cy="50" r="40" fill="url(https://evil.example/#g)" onclick="x()" style="fill:red"/>'
            '<rect x="1" y="1" width="5" height="5" fill="javascript:alert(1)"/>'
            '<path d="M10 10 L20 20" stroke="#000000"/></svg>'
        )
        svg = sanitize_svg(dirty)
        for bad in ("script", "onload", "onclick", "image", "href", "use", "foreignObject", "style", "url(", "javascript", "evil"):
            self.assertNotIn(bad, svg)
        self.assertIn("<path", svg)

    def test_rejects_doctype_entities_non_svg_and_too_large(self):
        for text in (
            '<!DOCTYPE svg [<!ENTITY a "x">]><svg xmlns="http://www.w3.org/2000/svg"><circle r="1"/></svg>',
            "<html><body/></html>",
            "not xml",
            "",
            None,
            '<svg xmlns="http://www.w3.org/2000/svg"><script>x</script></svg>',  # 図形が残らない
            '<svg xmlns="http://www.w3.org/2000/svg">' + '<circle r="1"/>' * 1000 + "</svg>",
        ):
            self.assertIsNone(sanitize_svg(text))

    def test_data_url(self):
        url = to_data_url(sanitize_svg(FACE))
        self.assertTrue(url.startswith("data:image/svg+xml;base64,"))
        self.assertIn(b"<circle", base64.b64decode(url.split(",", 1)[1]))

    def test_generate_expressions_validates_all_four(self):
        with mock.patch("plays.gemini._call", return_value=EXPRESSIONS):
            self.assertEqual(set(gemini.generate_expressions("beginner")), {"normal", "happy", "angry", "doubt"})
        broken = dict(EXPRESSIONS, doubt="<script>x</script>")
        with mock.patch("plays.gemini._call", return_value=broken):
            with self.assertRaises(GeminiError):
                gemini.generate_expressions("beginner")


class ExpressionPlayTest(TestCase):
    def post(self, url, body=None):
        return self.client.post(url, data=json.dumps(body or {}), content_type="application/json")

    def start(self, expressions=EXPRESSIONS, error=None):
        with mock.patch("plays.api.gemini.generate_scenario", return_value=SCENARIO), \
                mock.patch("plays.api.gemini.generate_expressions", return_value=expressions, side_effect=error):
            res = self.post("/api/plays/", {"difficulty": "beginner"})
        self.assertEqual(res.status_code, 201)
        return res.json()["play_id"]

    def test_member_saves_sanitized_svgs_and_returns_images(self):
        self.client.force_login(User.objects.create_user("a@example.com", "pass1234"))
        play_id = self.start()
        self.assertEqual(ScenarioExpression.objects.count(), 4)
        images = self.client.get(f"/api/plays/{play_id}/").json()["expression_images"]
        self.assertEqual(set(images), {"normal", "happy", "angry", "doubt"})
        self.assertTrue(images["angry"].startswith("data:image/svg+xml;base64,"))
        # リザルト（失敗＝怒り顔）と履歴詳細にも生成した顔が出る
        self.post(f"/api/plays/{play_id}/give-up/")
        self.assertContains(self.client.get(f"/plays/{play_id}/result/"), images["angry"])
        self.assertContains(self.client.get(f"/plays/history/{play_id}/"), images["angry"])

    def test_member_svg_failure_still_starts_with_fixed_faces(self):
        self.client.force_login(User.objects.create_user("a@example.com", "pass1234"))
        play_id = self.start(error=GeminiError("AI_ERROR"))
        self.assertFalse(ScenarioExpression.objects.exists())
        self.assertIsNone(self.client.get(f"/api/plays/{play_id}/").json()["expression_images"])

    def test_guest_keeps_svgs_in_session_only(self):
        play_id = self.start()
        self.assertFalse(ScenarioExpression.objects.exists())  # ゲストは DB に保存しない
        images = self.client.get(f"/api/plays/{play_id}/").json()["expression_images"]
        self.assertEqual(set(images), {"normal", "happy", "angry", "doubt"})

    def test_scenario_failure_is_still_ai_error(self):
        with mock.patch("plays.api.gemini.generate_scenario", side_effect=GeminiError("AI_ERROR")), \
                mock.patch("plays.api.gemini.generate_expressions", return_value=EXPRESSIONS):
            res = self.post("/api/plays/")
        self.assertEqual(res.json()["error"]["code"], "AI_ERROR")
