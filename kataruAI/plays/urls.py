from django.urls import path
from . import history, views

urlpatterns = [
    # http://localhost:8000/plays/ に対する設定を追加
    path('', views.Index.as_view(), name='index'),
    # プレイ履歴（会員）。'<str:play_id>/' より前に置くこと（history がプレイIDとして読まれないように）
    path('history/', history.history_list, name='history_list'),
    path('history/<int:play_id>/', history.history_detail, name='history_detail'),
    # プレイ画面（React）。IDはReact側がURLから読む
    path('<str:play_id>/', views.PlayPage.as_view(), name='play_page'),
    # リザルト画面（ゲスト用。設計書：/plays/{id}/result/）
    path('<str:play_id>/result/', views.result, name='play_result'),
]
