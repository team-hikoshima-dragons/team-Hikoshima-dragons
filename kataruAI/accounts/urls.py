from django.urls import path
from . import views

app_name = "accounts"

urlpatterns = [
    path("signup/", views.SignUpView.as_view(), name="signup"),
    path("login/", views.LoginView.as_view(), name="login"),
    path("logout/", views.LogoutView.as_view(), name="logout"),
    path("mypage/", views.MypageView.as_view(), name="mypage"),
    path("delete/", views.AccountDeleteView.as_view(), name="delete"),
    path("settings/", views.SettingsView.as_view(), name="settings"),
]