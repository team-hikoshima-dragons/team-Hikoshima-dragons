"""プレイ画面用APIのURL（config/urls.py から /api/plays/ にマウントする）"""
from django.urls import path

from . import api

urlpatterns = [
    path('', api.start, name='api_play_start'),                          # POST /api/plays/
    path('<str:play_id>/', api.detail, name='api_play_detail'),          # GET  /api/plays/{id}/
    path('<str:play_id>/turns/', api.turn, name='api_play_turn'),        # POST /api/plays/{id}/turns/
    path('<str:play_id>/give-up/', api.give_up, name='api_play_give_up'),  # POST .../give-up/
    path('<str:play_id>/abort/', api.abort, name='api_play_abort'),      # POST .../abort/
]
