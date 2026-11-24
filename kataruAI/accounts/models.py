
from django.db import models
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
import uuid


class UserManager(BaseUserManager):

    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("メールアドレスを入力してください")

        email = self.normalize_email(email)

        user = self.model(
            email=email,
            **extra_fields
        )

        user.set_password(password)
        user.save(using=self._db)

        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("スーパーユーザーにはis_staff=Trueが必要です")

        if extra_fields.get("is_superuser") is not True:
            raise ValueError("スーパーユーザーにはis_superuser=Trueが必要です")

        return self.create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
    )

    username = models.CharField(
        verbose_name="名前",
        max_length=20,
        unique=False,
        default="テストユーザー"
    )

    email = models.EmailField(
        verbose_name="メールアドレス",
        unique=True,
    )

    create_at = models.DateTimeField(
        verbose_name="アカウント作成日",
        auto_now_add=True,
    )

    update_at = models.DateTimeField(
        verbose_name="アカウント更新日",
        auto_now=True,
        null=True,
        blank=True
    )

    deleted_at = models.DateTimeField(
        verbose_name="アカウント削除日",
        null=True,
        blank=True,
    )

    is_active = models.BooleanField(
        verbose_name="アカウントが有効か",
        default=True
    )

    is_staff = models.BooleanField(
        verbose_name="管理画面へのアクセス権限",
        default=False
    )

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    def __str__(self):
        return self.email


class UserSetting(models.Model):
    class TextSpeed(models.TextChoices):
        SLOW = 'slow', 'ゆっくり'
        NORMAL = 'normal', 'ふつう'
        FAST = 'fast', 'はやい'

    user = models.OneToOneField(
        User,
        primary_key=True,
        on_delete=models.CASCADE
    )

    text_speed = models.CharField(
        verbose_name="テキスト速度",
        max_length=10,
        choices=TextSpeed.choices,
        default=TextSpeed.NORMAL,
    )

    auto_save_chat = models.BooleanField(
        verbose_name="チャット履歴の自動保存",
        default=True,
    )

    updated_at = models.DateTimeField(
        verbose_name="更新日時",
        auto_now=True,
    )
