from django.urls import path
from . import views

urlpatterns = [
    # http://localhost:8000/plays/ に対する設定を追加
    path('', views.Index.as_view(), name='index'),
    # プレイ画面（React）。IDはReact側がURLから読む
    path('<str:play_id>/', views.PlayPage.as_view(), name='play_page'),
    # リザルト画面（ゲスト用。設計書：/plays/{id}/result/）
    path('<str:play_id>/result/', views.result, name='play_result'),
]
