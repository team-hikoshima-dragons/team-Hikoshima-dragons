"""シナリオ一覧・お気に入り・コード検索・ユーザー作成シナリオでのプレイのテスト（Phase 4b・4c）"""
import json
from unittest import mock

from django.test import TestCase
from django.utils import timezone

from accounts.models import User
from plays.models import Play

from .models import Favorite, Scenario

REPLY = {"reply": "……", "state": "迷っている", "expression": "happy", "reason": "",
         "delta": {"mood": 5, "suspicion": -5, "understanding": 15}}


class BrowseTestBase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("a@example.com", "abcd1234", username="たろう")
        self.author = User.objects.create_user("b@example.com", "abcd1234", username="さくしゃ")
        self.client.force_login(self.user)

    def make(self, title="t", name="キャラ", public=True, **extra):
        values = dict(creator=self.author, kind="user", difficulty="beginner", title=title,
                      character_name=name, character_intro="紹介", goal="ゴール", condition="条件",
                      is_public=public)
        values.update(extra)
        return Scenario.objects.create(**values)

    def play(self, scenario, status="cleared", score=100, user=None, turns_used=5):
        return Play.objects.create(user=user or self.user, scenario=scenario, status=status, score=score,
                                   turn_limit=15, save_chat_log=True, turns_used=turns_used,
                                   finished_at=timezone.now())


class ListTest(BrowseTestBase):
    def test_only_public_undeleted_user_scenarios(self):
        self.make("公開シナリオ")
        self.make("非公開シナリオ", public=False)
        self.make("削除したシナリオ", deleted_at=timezone.now())
        self.make("ランダムのお題", kind="random")
        res = self.client.get("/scenarios/")
        self.assertContains(res, "公開シナリオ")
        for hidden in ("非公開シナリオ", "削除したシナリオ", "ランダムのお題"):
            self.assertNotContains(res, hidden)
        self.assertContains(res, "作成：さくしゃ")

    def test_empty_messages(self):
        self.assertContains(self.client.get("/scenarios/"), "公開されているシナリオはありません")
        self.make("喫茶店")
        self.assertContains(self.client.get("/scenarios/?q=存在しない"), "条件に合うシナリオはありません")

    def test_search_title_and_character_name(self):
        self.make("喫茶店の延長", name="マスター")
        self.make("家賃交渉", name="大家")
        res = self.client.get("/scenarios/?q=大家")
        self.assertContains(res, "家賃交渉")
        self.assertNotContains(res, "喫茶店の延長")
        self.assertContains(self.client.get("/scenarios/?q=喫茶"), "喫茶店の延長")

    def test_sort(self):
        old = self.make("古いけど人気")
        Scenario.objects.filter(pk=old.pk).update(created_at=timezone.now() - timezone.timedelta(days=3))
        new = self.make("新しい")
        for _ in range(2):
            self.play(old, user=self.author)
        Favorite.objects.create(user=self.author, scenario=new)

        def order(sort):
            return [row["scenario"].pk for row in self.client.get(f"/scenarios/?sort={sort}").context["rows"]]
        self.assertEqual(order("new"), [new.pk, old.pk])
        self.assertEqual(order("popular"), [old.pk, new.pk])
        self.assertEqual(order("favorites"), [new.pk, old.pk])

    def test_self_best_in_detail_data(self):
        scenario = self.make()
        self.play(scenario, score=300, turns_used=8)
        self.play(scenario, score=500, turns_used=6)
        self.play(scenario, status="failed", score=0)
        row = self.client.get("/scenarios/").context["rows"][0]
        self.assertEqual(row["detail"]["best"], "6ターン／スコア500")
        other = self.make("未プレイ")
        rows = {r["scenario"].pk: r for r in self.client.get("/scenarios/").context["rows"]}
        self.assertEqual(rows[other.pk]["detail"]["best"], "-")

    def test_pagination(self):
        for i in range(21):
            self.make(f"s{i}")
        self.assertEqual(len(self.client.get("/scenarios/").context["rows"]), 20)
        self.assertEqual(len(self.client.get("/scenarios/?page=2").context["rows"]), 1)

    def test_login_required(self):
        self.client.logout()
        self.assertEqual(self.client.get("/scenarios/").status_code, 302)


class FavoriteTest(BrowseTestBase):
    def test_toggle(self):
        scenario = self.make()
        res = self.client.post(f"/scenarios/{scenario.pk}/favorite/")
        self.assertEqual(res.json(), {"favorited": True, "favorite_count": 1})
        res = self.client.post(f"/scenarios/{scenario.pk}/favorite/")
        self.assertEqual(res.json(), {"favorited": False, "favorite_count": 0})
        self.assertFalse(Favorite.objects.exists())  # 解除は物理削除

    def test_cannot_favorite_private_or_deleted(self):
        for scenario in (self.make(public=False), self.make(deleted_at=timezone.now())):
            self.assertEqual(self.client.post(f"/scenarios/{scenario.pk}/favorite/").status_code, 404)
        self.assertFalse(Favorite.objects.exists())

    def test_favorites_page_shows_only_my_public_favorites(self):
        liked = self.make("好きなシナリオ")
        self.make("ふつうのシナリオ")
        hidden = self.make("非公開になったシナリオ")
        Favorite.objects.create(user=self.user, scenario=liked)
        Favorite.objects.create(user=self.user, scenario=hidden)
        Scenario.objects.filter(pk=hidden.pk).update(is_public=False)
        res = self.client.get("/scenarios/favorites/")
        self.assertContains(res, "好きなシナリオ")
        self.assertNotContains(res, "ふつうのシナリオ")
        self.assertNotContains(res, "非公開になったシナリオ")
        self.assertContains(res, "表示中（1件）")
        self.assertTrue(res.context["rows"][0]["detail"]["fav"])

    def test_favorites_empty(self):
        self.assertContains(self.client.get("/scenarios/favorites/"), "お気に入りに登録したシナリオはありません")


class CodeSearchTest(BrowseTestBase):
    def test_found(self):
        scenario = self.make("コードのシナリオ")
        res = self.client.get(f"/scenarios/code/{scenario.share_code}/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["id"], scenario.pk)
        self.assertEqual(res.json()["author"], "さくしゃ")

    def test_invalid_code(self):
        for code in ("1234567", "ABCDEFG!", "123456789"):
            res = self.client.get(f"/scenarios/code/{code}/")
            self.assertEqual(res.status_code, 400)
            self.assertEqual(res.json()["error"]["message"], "8桁の英数字で入力してね。")

    def test_private_deleted_and_missing_are_not_found(self):
        private = self.make(public=False)
        deleted = self.make(deleted_at=timezone.now())
        for code in (private.share_code, deleted.share_code, "00000000"):
            res = self.client.get(f"/scenarios/code/{code}/")
            self.assertEqual(res.status_code, 404)
            self.assertEqual(res.json()["error"]["message"], "そのコードのシナリオは見つかりません")


class PlayUserScenarioTest(BrowseTestBase):
    def start(self, scenario):
        res = self.client.post("/api/plays/", data=json.dumps({"scenario_id": scenario.pk}),
                               content_type="application/json")
        self.assertEqual(res.status_code, 201)
        return res.json()["play_id"]

    def clear(self, play_id):
        for no in range(1, 6):
            with mock.patch("plays.api.gemini.generate_reply", return_value=REPLY):
                self.client.post(f"/api/plays/{play_id}/turns/", data=json.dumps({"text": "a", "turn_no": no}),
                                 content_type="application/json")

    def test_play_screen_uses_scenario_image(self):
        scenario = self.make(image="scenario_images/abc.png")
        play_id = self.start(scenario)
        self.assertEqual(self.client.get(f"/api/plays/{play_id}/").json()["image_url"], "/media/scenario_images/abc.png")
        no_image = self.make()
        play_id = self.start(no_image)
        self.assertEqual(self.client.get(f"/api/plays/{play_id}/").json()["image_url"], "/static/img/silhouette.svg")

    def test_result_shows_new_best_but_no_rank(self):
        scenario = self.make()
        play_id = self.start(scenario)
        self.clear(play_id)
        res = self.client.get(f"/plays/{play_id}/result/")
        self.assertContains(res, "自己ベスト更新！")
        self.assertNotContains(res, 'id="rank"')  # ユーザー作成シナリオはランキング対象外
        # 同じ点数では更新にならない
        play_id = self.start(scenario)
        self.clear(play_id)
        self.assertNotContains(self.client.get(f"/plays/{play_id}/result/"), "自己ベスト更新！")
