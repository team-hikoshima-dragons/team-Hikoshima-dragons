"""scenarios のモデルが テーブル設計図.drawio どおりかのテスト"""
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.test import TestCase

from accounts.models import User, UserSetting

from .models import Favorite, Scenario, ScenarioExpression


def make_scenario(user, **extra):
    values = dict(
        creator=user, kind=Scenario.Kind.USER,
        difficulty=Scenario.Level.INTERMEDIATE, title="閉店を延ばして",
    )
    values.update(extra)
    return Scenario.objects.create(**values)


class ScenarioModelTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("a@example.com", "pass1234")

    def test_choice_values(self):
        """種別は random / user、難易度は beginner / intermediate / advanced"""
        self.assertEqual([v for v, _ in Scenario.Kind.choices], ["random", "user"])
        self.assertEqual(
            [v for v, _ in Scenario.Level.choices],
            ["beginner", "intermediate", "advanced"],
        )

    def test_new_scenario_is_not_deleted_and_private(self):
        """作成直後は削除日時が空（＝有効）、非公開、共有コードは8桁"""
        scenario = make_scenario(self.user)
        self.assertIsNone(scenario.deleted_at)
        self.assertFalse(scenario.is_public)
        self.assertRegex(scenario.share_code, r"^\d{8}$")
        self.assertIsNone(scenario.image)

    def test_updated_at_changes_on_save(self):
        """更新日時は保存のたびに更新される"""
        scenario = make_scenario(self.user)
        before = scenario.updated_at
        scenario.title = "別のタイトル"
        scenario.save()
        scenario.refresh_from_db()
        self.assertGreater(scenario.updated_at, before)

    def test_creator_is_protected(self):
        """シナリオが残っている作成者は物理削除できない（アカウント削除は論理削除で行う）"""
        make_scenario(self.user)
        with self.assertRaises(ProtectedError):
            self.user.delete()


class ScenarioExpressionModelTest(TestCase):
    def test_one_svg_per_expression(self):
        """同じシナリオの同じ表情は1つだけ"""
        user = User.objects.create_user("a@example.com", "pass1234")
        scenario = make_scenario(user, kind=Scenario.Kind.RANDOM)
        ScenarioExpression.objects.create(scenario=scenario, expression="normal", svg="<svg></svg>")
        ScenarioExpression.objects.create(scenario=scenario, expression="happy", svg="<svg></svg>")
        with self.assertRaises(IntegrityError), transaction.atomic():
            ScenarioExpression.objects.create(scenario=scenario, expression="normal", svg="<svg></svg>")
        self.assertEqual(scenario.expressions.count(), 2)


class FavoriteModelTest(TestCase):
    def test_same_scenario_cannot_be_favorited_twice(self):
        """同じシナリオを2回お気に入りにできない"""
        user = User.objects.create_user("a@example.com", "pass1234")
        scenario = make_scenario(user)
        Favorite.objects.create(user=user, scenario=scenario)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Favorite.objects.create(user=user, scenario=scenario)


class UserSettingModelTest(TestCase):
    def test_default_values(self):
        """設定の初期値：テキスト速度はふつう、チャット履歴の自動保存はON"""
        user = User.objects.create_user("a@example.com", "pass1234")
        setting = UserSetting.objects.create(user=user)
        self.assertEqual(setting.text_speed, "normal")
        self.assertTrue(setting.auto_save_chat)
        self.assertEqual(
            [v for v, _ in UserSetting.TextSpeed.choices], ["slow", "normal", "fast"],
        )
