"""accounts のテスト：新規登録の検証・マイページ（成績・アカウント変更）・アカウント削除・ゲーム設定"""
import json

from django.test import TestCase
from django.utils import timezone

from plays.models import Play
from scenarios.models import Favorite, Scenario

from .forms import SignUpForm
from .models import User, UserSetting


def signup_data(**extra):
    data = {"username": "たろう", "email": "taro@example.com", "password": "abcd1234", "password_confirm": "abcd1234"}
    data.update(extra)
    return data


class SignUpTest(TestCase):
    def post(self, **extra):
        return self.client.post("/accounts/signup/", signup_data(**extra))

    def test_signup_creates_user_and_setting(self):
        res = self.post()
        self.assertEqual(res.status_code, 201)
        user = User.objects.get(email="taro@example.com")
        self.assertEqual(user.username, "たろう")
        self.assertTrue(user.check_password("abcd1234"))
        self.assertTrue(UserSetting.objects.filter(user=user).exists())

    def test_blank_username_gets_random_name(self):
        self.post(username="  ")
        self.assertRegex(User.objects.get().username, r"^プレイヤー\d{4}$")

    def test_username_over_20_is_rejected(self):
        res = self.post(username="あ" * 21)
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["field"], "username")

    def test_password_rules(self):
        for password, message in (
            ("abc123", "パスワードは8文字以上にしてね。"),
            ("abcdefgh", "英字と数字を両方入れてね。"),
            ("12345678", "英字と数字を両方入れてね。"),
        ):
            res = self.post(password=password, password_confirm=password)
            self.assertEqual(res.status_code, 400)
            self.assertEqual(res.json()["error"], message)
        self.assertFalse(User.objects.exists())

    def test_confirm_mismatch(self):
        res = self.post(password_confirm="abcd12345")
        self.assertEqual(res.json()["field"], "password_confirm")

    def test_taken_email_returns_email_step(self):
        User.objects.create_user("taro@example.com", "abcd1234")
        res = self.post(email="TARO@example.com")
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["field"], "email")
        self.assertEqual(res.json()["error"], "そのメールアドレスはもう登録されてるよ。")

    def test_invalid_email(self):
        form = SignUpForm(signup_data(email="taro"))
        self.assertFalse(form.is_valid())
        self.assertEqual(form.errors["email"][0], "メールアドレスの形がちがうみたい。")


class MypageTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("a@example.com", "abcd1234", username="たろう")
        self.client.force_login(self.user)

    def make_play(self, status, score):
        scenario = Scenario.objects.create(creator=self.user, kind="random", difficulty="beginner", title="t")
        return Play.objects.create(
            user=self.user, scenario=scenario, status=status, score=score, turn_limit=15, save_chat_log=True,
        )

    def post(self, **extra):
        data = {"username": "たろう", "email": "a@example.com", "current_password": "",
                "new_password": "", "new_password_confirm": ""}
        data.update(extra)
        return self.client.post("/accounts/mypage/", data)

    def test_login_required(self):
        self.client.logout()
        self.assertEqual(self.client.get("/accounts/mypage/").status_code, 302)

    def test_stats(self):
        self.make_play("cleared", 500)
        self.make_play("cleared", 800)
        self.make_play("failed", 0)
        self.make_play("aborted", None)  # 中断・プレイ中は数えない
        self.make_play("playing", None)
        res = self.client.get("/accounts/mypage/")
        self.assertEqual(res.context["stats"], {"clear_count": 2, "play_count": 3, "best_score": 800})
        self.assertContains(res, "たろうさん")

    def test_change_username(self):
        res = self.post(username="じろう")
        self.assertRedirects(res, "/accounts/mypage/", fetch_redirect_response=False)
        self.user.refresh_from_db()
        self.assertEqual(self.user.username, "じろう")
        self.assertContains(self.client.get("/accounts/mypage/"), "更新が完了しました")

    def test_username_required_and_max_20(self):
        for name in ("", "  ", "あ" * 21):
            self.assertEqual(self.post(username=name).status_code, 400)
        self.user.refresh_from_db()
        self.assertEqual(self.user.username, "たろう")

    def test_change_email_requires_current_password(self):
        res = self.post(email="new@example.com")
        self.assertEqual(res.status_code, 400)
        self.assertContains(res, "今のパスワードを入力してね。", status_code=400)
        res = self.post(email="new@example.com", current_password="wrong123")
        self.assertContains(res, "今のパスワードがちがうみたい。", status_code=400)
        self.post(email="new@example.com", current_password="abcd1234")
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "new@example.com")

    def test_email_used_by_other_user(self):
        User.objects.create_user("b@example.com", "abcd1234")
        res = self.post(email="b@example.com", current_password="abcd1234")
        self.assertContains(res, "そのメールアドレスは他のユーザーが使っています。", status_code=400)

    def test_change_password_keeps_login(self):
        res = self.post(current_password="abcd1234", new_password="newpass99", new_password_confirm="newpass99")
        self.assertRedirects(res, "/accounts/mypage/")
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("newpass99"))
        self.assertEqual(self.client.get("/accounts/mypage/").status_code, 200)  # ログインしたまま

    def test_new_password_rules(self):
        for new, confirm in (("short1", "short1"), ("abcdefgh", "abcdefgh"), ("newpass99", "newpass98")):
            res = self.post(current_password="abcd1234", new_password=new, new_password_confirm=confirm)
            self.assertEqual(res.status_code, 400)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("abcd1234"))


class AccountDeleteTest(TestCase):
    def test_delete_account(self):
        user = User.objects.create_user("a@example.com", "abcd1234")
        other = User.objects.create_user("b@example.com", "abcd1234")
        mine = Scenario.objects.create(creator=user, kind="user", difficulty="beginner", title="t")
        others = Scenario.objects.create(creator=other, kind="user", difficulty="beginner", title="t", is_public=True)
        Favorite.objects.create(user=user, scenario=others)
        Favorite.objects.create(user=other, scenario=mine)
        self.client.force_login(user)

        res = self.client.post("/accounts/delete/")
        self.assertRedirects(res, "/", fetch_redirect_response=False)
        user.refresh_from_db()
        self.assertFalse(user.is_active)
        self.assertIsNotNone(user.deleted_at)
        self.assertEqual(user.email, f"deleted-{user.pk}@invalid")
        mine.refresh_from_db()
        self.assertIsNotNone(mine.deleted_at)
        self.assertFalse(Favorite.objects.filter(user=user).exists())  # 物理削除
        self.assertTrue(Favorite.objects.filter(user=other).exists())  # 他人のお気に入りは残る
        # ログアウトしている。同じメールアドレスで登録し直せる
        self.assertEqual(self.client.get("/accounts/mypage/").status_code, 302)
        self.assertEqual(self.client.post("/accounts/signup/", signup_data(email="a@example.com")).status_code, 201)
        # 削除したアカウントではログインできない
        self.assertFalse(self.client.login(email=f"deleted-{user.pk}@invalid", password="abcd1234"))

    def test_get_is_not_allowed(self):
        user = User.objects.create_user("a@example.com", "abcd1234")
        self.client.force_login(user)
        self.assertEqual(self.client.get("/accounts/delete/").status_code, 405)
        user.refresh_from_db()
        self.assertTrue(user.is_active)


class SettingsTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("a@example.com", "abcd1234")
        self.client.force_login(self.user)

    def post(self, body):
        return self.client.post("/accounts/settings/", data=json.dumps(body), content_type="application/json")

    def test_page_shows_defaults_when_not_set(self):
        res = self.client.get("/accounts/settings/")
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, 'value="normal" checked', html=False)
        self.assertContains(res, 'value="1" checked', html=False)

    def test_save_text_speed(self):
        res = self.post({"text_speed": "fast"})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(UserSetting.objects.get(user=self.user).text_speed, "fast")

    def test_save_auto_save_chat(self):
        self.post({"auto_save_chat": False})
        self.assertFalse(UserSetting.objects.get(user=self.user).auto_save_chat)

    def test_invalid_values_are_rejected(self):
        for body in ({"text_speed": "turbo"}, {"auto_save_chat": "no"}, {}):
            self.assertEqual(self.post(body).status_code, 400)
        setting = UserSetting.objects.get(user=self.user)
        self.assertEqual((setting.text_speed, setting.auto_save_chat), ("normal", True))

    def test_login_required(self):
        self.client.logout()
        self.assertEqual(self.post({"text_speed": "fast"}).status_code, 302)


class LoginTest(TestCase):
    """ユースケース記述テスト仕様書 02「認証失敗」"""

    def setUp(self):
        User.objects.create_user("a@example.com", "abcd1234")

    def test_failure_keeps_email_and_shows_message(self):
        res = self.client.post("/accounts/login/", {"email": "a@example.com", "password": "wrong999"})
        self.assertContains(res, "メールアドレスまたはパスワードが正しくありません")
        self.assertContains(res, 'value="a@example.com"', html=False)
        self.assertNotContains(res, "wrong999")

    def test_deleted_account_cannot_login(self):
        User.objects.filter(email="a@example.com").update(is_active=False)
        res = self.client.post("/accounts/login/", {"email": "a@example.com", "password": "abcd1234"})
        self.assertContains(res, "メールアドレスまたはパスワードが正しくありません")

    def test_password_reset_link_is_hidden(self):
        self.assertNotContains(self.client.get("/accounts/login/"), "パスワードを忘れた")
