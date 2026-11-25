from django.urls import path

from . import views

app_name = "scenarios"

urlpatterns = [
    path("", views.browse, name="list"),
    path("favorites/", views.favorites, name="favorites"),
    path("code/<str:code>/", views.find_by_code, name="find_by_code"),
    path("<int:scenario_id>/favorite/", views.toggle_favorite, name="toggle_favorite"),
    path("create/", views.create, name="create"),
    path("mine/", views.mine, name="mine"),
    path("<int:scenario_id>/visibility/", views.toggle_public, name="toggle_public"),
    path("<int:scenario_id>/delete/", views.delete, name="delete"),
]
