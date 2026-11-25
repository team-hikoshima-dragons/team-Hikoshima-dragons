from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm

User = get_user_model()


class SignUpForm(UserCreationForm):
    class Meta:
        model = User
        fields = ["username", "email"]

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

