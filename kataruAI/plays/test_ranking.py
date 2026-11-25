"""ランキングのテスト（Phase 5）"""
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from accounts.models import User
from scenarios.models import Scenario

from . import ranking
from .models import Play


def clear(user, score, difficulty="beginner", kind="random", days_ago=0, status="cleared"):
    scenario = Scenario.objects.create(creator=user, kind=kind, difficulty=difficulty, title="t")
    return Play.objects.create(
        user=user, scenario=scenario, status=status, score=score, turn_limit=15, save_chat_log=True,
        finished_at=timezone.now() - timedelta(days=days_ago),
    )


class AggregateTest(TestCase):
    def setUp(self):
        self.a = User.objects.create_user("a@example.com", "abcd1234", username="あ")
        self.b = User.objects.create_user("b@example.com", "abcd1234", username="い")
        self.c = User.objects.create_user("c@example.com", "abcd1234", username="う")

    def test_total_and_clears_and_ties(self):
        """同点ならクリア数の多いほうが上（テスト仕様書 08「同点の並び」）。順位は通し番号"""
        clear(self.a, 300)
        clear(self.a, 300)
        clear(self.b, 600)
        clear(self.c, 100)
        rows = ranking.aggregate()
        self.assertEqual([(r["username"], r["clears"], r["total"], r["rank"]) for r in rows],
                         [("あ", 2, 600, 1), ("い", 1, 600, 2), ("う", 1, 100, 3)])

    def test_same_total_and_clears_first_to_reach_is_higher(self):
        """合計もクリア数も同じなら、先にその合計に達したユーザーが上"""
        clear(self.b, 500, days_ago=1)  # い が先に到達
        clear(self.a, 500, days_ago=0)
        self.assertEqual([r["username"] for r in ranking.aggregate()], ["い", "あ"])

    def test_only_random_clears_of_active_users(self):
        clear(self.a, 500, kind="user")
        clear(self.a, 0, status="failed")
        clear(self.a, 999, status="aborted")
        inactive = User.objects.create_user("d@example.com", "abcd1234", is_active=False)
        clear(inactive, 900)
        clear(self.b, 100)
        self.assertEqual([r["user_id"] for r in ranking.aggregate()], [self.b.pk])

    def test_period_and_difficulty(self):
        clear(self.a, 100, days_ago=0)
        clear(self.b, 200, days_ago=10)
        clear(self.c, 300, days_ago=400, difficulty="advanced")
        week = ranking.aggregate(ranking.period_start("week"))
        self.assertEqual([r["user_id"] for r in week], [self.a.pk])
        self.assertEqual(len(ranking.aggregate(ranking.period_start("month"))), 2)
        self.assertEqual(len(ranking.aggregate(None)), 3)
        self.assertEqual([r["user_id"] for r in ranking.aggregate(None, "advanced")], [self.c.pk])


class RankingPageTest(TestCase):
    def setUp(self):
        self.me = User.objects.create_user("me@example.com", "abcd1234", username="わたし")
        self.client.force_login(self.me)

    def test_default_week_all_and_highlight(self):
        other = User.objects.create_user("o@example.com", "abcd1234", username="ほか")
        clear(other, 1500)
        clear(self.me, 1000)
        clear(other, 5000, days_ago=8)  # 1週間より前
        res = self.client.get("/rankings/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual((res.context["period"], res.context["difficulty"]), ("week", "all"))
        self.assertContains(res, "1,500")
        self.assertContains(res, '<tr class="rank-table__me">', html=False)
        self.assertContains(res, "あなた")

    def test_top_50_and_my_row_below(self):
        for i in range(55):
            clear(User.objects.create_user(f"u{i}@example.com", "abcd1234", username=f"u{i}"), 1000 + i)
        clear(self.me, 1)
        res = self.client.get("/rankings/?period=all")
        self.assertEqual(len(res.context["rows"]), 50)
        self.assertEqual(res.context["me_below"]["rank"], 56)
        self.assertContains(res, "わたし")

    def test_empty(self):
        self.assertContains(self.client.get("/rankings/?period=today&difficulty=advanced"),
                            "データがまだありません")

    def test_invalid_params_fall_back(self):
        res = self.client.get("/rankings/?period=xx&difficulty=yy")
        self.assertEqual((res.context["period"], res.context["difficulty"]), ("week", "all"))

    def test_login_required(self):
        self.client.logout()
        self.assertEqual(self.client.get("/rankings/").status_code, 302)
