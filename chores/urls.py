from django.urls import path

from chores import views

app_name = "chores"

urlpatterns = [
    path("", views.chore_list, name="list"),
    path("login/", views.login, name="login"),
    path("logout/", views.logout, name="logout"),
]
