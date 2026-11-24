from django.urls import path
from . import views

urlpatterns = [
    # http://localhost:8000/plays/ に対する設定を追加
    path('', views.Index.as_view(), name='index'),
    path('chat/', views.chat, name='chat'),
    # プレイ画面（React）。IDはReact側がURLから読む。'chat/' より後ろに置くこと
    path('<str:play_id>/', views.PlayPage.as_view(), name='play_page'),
    # リザルト画面（ゲスト用。設計書：/plays/{id}/result/）
    path('<str:play_id>/result/', views.result, name='play_result'),
]
