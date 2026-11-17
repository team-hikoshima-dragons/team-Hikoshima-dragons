from django.urls import path
from . import views

urlpatterns = [
    # http://localhost:8000/plays/ に対する設定を追加
    path('', views.Index.as_view(), name='index'),
    path('chat/', views.chat, name='chat'),
]