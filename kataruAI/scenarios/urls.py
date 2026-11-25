from django.urls import path

from . import views

app_name = "scenarios"

urlpatterns = [
    path("create/", views.create, name="create"),
    path("mine/", views.mine, name="mine"),
    path("<int:scenario_id>/visibility/", views.toggle_public, name="toggle_public"),
    path("<int:scenario_id>/delete/", views.delete, name="delete"),
]
