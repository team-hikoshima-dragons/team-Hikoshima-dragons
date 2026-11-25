import random
import re

from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm

User = get_user_model()

USERNAME_MAX = 20
PASSWORD_MIN = 8


def check_password_rule(password):
    """パスワードのルール（設計書：8文字以上・英字と数字を両方含む）。違反ならメッセージを返す。"""
    if len(password) < PASSWORD_MIN:
        return f"パスワードは{PASSWORD_MIN}文字以上にしてね。"
    if not re.search(r"[A-Za-z]", password) or not re.search(r"[0-9]", password):
        return "英字と数字を両方入れてね。"
    return ""


def random_username():
    """ニックネームが空欄のときの名前（例：プレイヤー1234）。重複は許す（設計書 イベント17）"""
    return f"プレイヤー{random.randint(1000, 9999)}"


def email_in_use(email, exclude_user=None):
    users = User.objects.filter(email__iexact=email)
    if exclude_user is not None:
        users = users.exclude(pk=exclude_user.pk)
    return users.exists()


class SignUpForm(forms.Form):
    """新規登録（画面設計書 サインアップ・イベント17）。項目名は設計書の name 属性に合わせる。

    エラーは項目の順（ニックネーム → メール → パスワード → 確認）に1つずつ JS に返す。
    """
    username = forms.CharField(
        required=False, max_length=USERNAME_MAX,
        error_messages={"max_length": f"ニックネームは{USERNAME_MAX}文字以内にしてね。"},
    )
    email = forms.EmailField(error_messages={
        "required": "メールアドレスを入力してね。",
        "invalid": "メールアドレスの形がちがうみたい。",
    })
    password = forms.CharField(strip=False, error_messages={"required": "パスワードを入力してね。"})
    password_confirm = forms.CharField(
        strip=False, error_messages={"required": "確認のため、もう一度パスワードを入れてね。"},
    )

    def clean_username(self):
        return self.cleaned_data["username"].strip() or random_username()

    def clean_email(self):
        email = User.objects.normalize_email(self.cleaned_data["email"])
        if email_in_use(email):
            raise forms.ValidationError("そのメールアドレスはもう登録されてるよ。")
        return email

    def clean_password(self):
        password = self.cleaned_data["password"]
        error = check_password_rule(password)
        if error:
            raise forms.ValidationError(error)
        return password

    def clean(self):
        cleaned = super().clean()
        password = cleaned.get("password")
        confirm = cleaned.get("password_confirm")
        if password and confirm is not None and password != confirm:
            self.add_error("password_confirm", "さっきのパスワードと一致しないみたい。")
        return cleaned

    def save(self):
        data = self.cleaned_data
        return User.objects.create_user(data["email"], data["password"], username=data["username"])


class AccountForm(forms.Form):
    """マイページのアカウント情報の変更（画面設計書 マイページ・イベント37）"""
    username = forms.CharField(
        max_length=USERNAME_MAX,
        error_messages={
            "required": "ユーザー名を入力してね。",
            "max_length": f"ユーザー名は{USERNAME_MAX}文字以内にしてね。",
        },
    )
    email = forms.EmailField(error_messages={
        "required": "メールアドレスを入力してね。",
        "invalid": "メールアドレスの形がちがうみたい。",
    })
    current_password = forms.CharField(required=False, strip=False)
    new_password = forms.CharField(required=False, strip=False)
    new_password_confirm = forms.CharField(required=False, strip=False)

    def __init__(self, user, *args, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

    def clean_username(self):
        username = self.cleaned_data["username"].strip()
        if not username:
            raise forms.ValidationError("ユーザー名を入力してね。")
        return username

    def clean_email(self):
        email = User.objects.normalize_email(self.cleaned_data["email"])
        if email_in_use(email, exclude_user=self.user):
            raise forms.ValidationError("そのメールアドレスは他のユーザーが使っています。")
        return email

    def clean(self):
        cleaned = super().clean()
        email = cleaned.get("email")
        current = cleaned.get("current_password") or ""
        new = cleaned.get("new_password") or ""
        confirm = cleaned.get("new_password_confirm") or ""
        changing_email = email is not None and email.lower() != self.user.email.lower()

        # メールアドレスまたはパスワードを変えるときは、今のパスワードが必要（⑤-b）
        if changing_email or new:
            if not current:
                self.add_error("current_password", "今のパスワードを入力してね。")
            elif not self.user.check_password(current):
                self.add_error("current_password", "今のパスワードがちがうみたい。")
        if new:
            error = check_password_rule(new)
            if error:
                self.add_error("new_password", error)
            elif new != confirm:
                self.add_error("new_password_confirm", "確認用のパスワードが一致しないよ。")
        return cleaned

    def save(self):
        data = self.cleaned_data
        self.user.username = data["username"]
        self.user.email = data["email"]
        if data.get("new_password"):
            self.user.set_password(data["new_password"])
        self.user.save()
        return self.user


class LoginForm(AuthenticationForm):
    # HTMLの <input name="email"> と一致させるため、username を上書きする
    username = forms.EmailField(label="メールアドレス")

    def __init__(self, request=None, *args, **kwargs):
        super().__init__(request, *args, **kwargs)
        # フォームのフィールド名を 'email' に変更してHTMLの name="email" と紐付ける
        self.fields["email"] = self.fields.pop("username")
        self.order_fields(["email", "password"])

    def clean(self):
        # AuthenticationForm本来の clean() が self.cleaned_data['username'] を参照するため値を移す
        self.cleaned_data["username"] = self.cleaned_data.get("email")
        return super().clean()
