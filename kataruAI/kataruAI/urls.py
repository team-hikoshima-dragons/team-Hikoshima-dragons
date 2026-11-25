from django.urls import path
from . import views

app_name = 'kataruAI'

urlpatterns = [
    path('', views.IndexContent.as_view(), name='index'),
]
