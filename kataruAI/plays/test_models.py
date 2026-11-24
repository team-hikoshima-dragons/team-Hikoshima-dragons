"""plays のモデルが テーブル設計図.drawio どおりかのテスト（DB を使う）"""
from django.db import IntegrityError, transaction
from django.test import TestCase

from accounts.models import User
from scenarios.models import Scenario

from .models import Play, PlayTurn


def make_scenario(user):
    return Scenario.objects.create(
        creator=user, kind=Scenario.Kind.RANDOM,
        difficulty=Scenario.Level.BEGINNER, title="閉店を延ばして",
    )


def make_play(user, scenario, status=Play.Status.PLAYING):
    return Play.objects.create(
        user=user, scenario=scenario, status=status, turn_limit=15, save_chat_log=True,
    )


class PlayModelTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("a@example.com", "pass1234")
        self.scenario = make_scenario(self.user)

    def test_initial_values(self):
        """初期値：状態は playing、機嫌50・疑い50・理解度0、終了日時は空"""
        play = make_play(self.user, self.scenario)
        self.assertEqual(play.status, "playing")
        self.assertEqual((play.mood, play.suspicion, play.understanding), (50, 50, 0))
        self.assertIsNone(play.finished_at)
        self.assertIsNone(play.score)

    def test_status_values_are_lowercase(self):
        """status の値は小文字（game.py と同じ）"""
        self.assertEqual(
            [value for value, _ in Play.Status.choices],
            ["playing", "cleared", "failed", "aborted"],
        )

    def test_only_one_playing_per_user(self):
        """プレイ中は1人1件"""
        make_play(self.user, self.scenario)
        with self.assertRaises(IntegrityError), transaction.atomic():
            make_play(self.user, self.scenario)

    def test_finished_plays_do_not_count(self):
        """終わったプレイ（cleared/failed/aborted）があっても、新しくプレイ中を作れる"""
        for status in (Play.Status.CLEARED, Play.Status.FAILED, Play.Status.ABORTED):
            make_play(self.user, self.scenario, status=status)
        make_play(self.user, self.scenario)
        self.assertEqual(Play.objects.filter(user=self.user, status="playing").count(), 1)

    def test_other_users_can_play_at_the_same_time(self):
        """別のユーザーなら、同時にプレイ中でもよい"""
        other = User.objects.create_user("b@example.com", "pass1234")
        make_play(self.user, self.scenario)
        make_play(other, make_scenario(other))
        self.assertEqual(Play.objects.filter(status="playing").count(), 2)


class PlayTurnModelTest(TestCase):
    def setUp(self):
        user = User.objects.create_user("a@example.com", "pass1234")
        self.play = make_play(user, make_scenario(user))

    def make_turn(self, turn_no, **extra):
        values = dict(
            play=self.play, turn_no=turn_no, user_message="こんにちは", ai_reply="……",
            delta_mood=5, delta_suspicion=-5, delta_understanding=10,
            mood_after=55, suspicion_after=45, understanding_after=10,
            state_text="少し警戒している", expression=PlayTurn.Expression.NORMAL,
        )
        values.update(extra)
        return PlayTurn.objects.create(**values)

    def test_turn_no_is_unique_in_a_play(self):
        """同じプレイに同じターン番号は2つ作れない（二重送信対策）"""
        self.make_turn(1)
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.make_turn(1)

    def test_chat_log_can_be_empty(self):
        """自動保存OFFのときは、発言と返答を NULL で保存できる"""
        turn = self.make_turn(1, user_message=None, ai_reply=None)
        turn.refresh_from_db()
        self.assertIsNone(turn.user_message)
        self.assertIsNone(turn.ai_reply)
        self.assertIsNotNone(turn.created_at)

    def test_expression_choices(self):
        """表情は normal / happy / angry / doubt"""
        self.assertEqual(
            [value for value, _ in PlayTurn.Expression.choices],
            ["normal", "happy", "angry", "doubt"],
        )
