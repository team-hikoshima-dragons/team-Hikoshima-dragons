from django.db import models
from django.contrib.auth.models import AbstractBaseUser
from accounts.models import *
import secrets
# Create your models here.

class Scenario(models.Model):
    class Kind(models.TextChoices):
        RANDOM = 'random', 'ランダムなお題'
        USER = 'user', 'ユーザー作成'
    class Level(models.TextChoices):
        BEGINNER = 'beginner', '初級'
        INTERMEDIATE = 'intermediate', '中級'
        ADVANCED = 'advanced', '上級'
    def create_share_number():
        while True:
            # 8桁のランダムな数字文字列を生成（例: "04829104"）
            code = "".join(secrets.choice("0123456789") for _ in range(8))
            # DBに同じ値が既に存在しないか確認
            if not Scenario.objects.filter(share_code=code).exists():
                return code
    creator = models.ForeignKey(
        # ランダムなお題＝プレイしたユーザー、ユーザー作成＝作成したユーザー
        User,
        verbose_name="作成者",
        on_delete=models.PROTECT
    )
    kind = models.CharField(
        verbose_name="種別(ランダムなお題かユーザー作成か)",
        max_length=10,
        choices=Kind.choices,
    )
    difficulty = models.CharField(
        verbose_name="難易度",
        max_length=12,
        choices=Level.choices,
    )
    title = models.CharField(
        verbose_name="タイトル",
        max_length=40,
    )
    description = models.CharField(
        verbose_name="説明",
        max_length=10000,
        blank=True,
    )
    # AIで生成させる===============
    character_name = models.CharField(
        verbose_name="キャラクター名",
        max_length=50,
        null=True,
        blank=True
    )
    character_intro = models.TextField(
        verbose_name="キャラクター紹介文(性格)",
        null=True,
        blank=True    )
    goal = models.TextField(
        verbose_name="ゴール条件",
        null=True,
        blank=True    
        )
    condition = models.TextField(
        verbose_name="条件",
        null=True,
        blank=True    
        )
    # ============================
    image = models.TextField( # NULL＝標準シルエット
        verbose_name="キャラクター画像",
        null=True,
        blank=True
    )
    is_public = models.BooleanField(
        verbose_name="公開シナリオ",
        default=False
    )
    share_code = models.CharField(
        verbose_name="共有コード",
        default=create_share_number,
        max_length=8,
        unique=True,
        null=True,
        blank=True
    )
    created_at = models.DateTimeField(
        verbose_name="作成日時",
        auto_now_add=True
    )
    updated_at = models.DateTimeField(
        verbose_name="更新日時",
        auto_now=True
    )
    deleted_at = models.DateTimeField(
        # NULL＝有効。論理削除のときに日時を入れる
        verbose_name="削除日時",
        null=True,
        blank=True
    )


class ScenarioExpression(models.Model):
    # ランダムなお題の表情差分SVG（サニタイズ済み）
    class Expression(models.TextChoices):
        NORMAL = 'normal', '通常'
        HAPPY = 'happy', 'うれしい'
        ANGRY = 'angry', '怒り'
        DOUBT = 'doubt', '疑い'
    scenario = models.ForeignKey(
        Scenario,
        verbose_name="シナリオ",
        on_delete=models.CASCADE,
        related_name="expressions"
    )
    expression = models.CharField(
        verbose_name="表情",
        max_length=10,
        choices=Expression.choices,
    )
    svg = models.TextField(
        verbose_name="表情SVG(サニタイズ済み)",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["scenario", "expression"],
                name="unique_scenario_expression",
            ),
        ]

class Favorite(models.Model):
    user = models.ForeignKey(
        User,
        verbose_name="ユーザー",
        on_delete=models.CASCADE
    )
    scenario = models.ForeignKey(
        Scenario,
        verbose_name="シナリオ",
        on_delete=models.CASCADE
    )
    created_at = models.DateTimeField(
        auto_now_add=True
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "scenario"],
                name="unique_favorite_user_scenario",
            ),
        ]
