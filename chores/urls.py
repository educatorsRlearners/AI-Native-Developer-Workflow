from django.urls import path

from chores import views

app_name = "chores"

urlpatterns = [
    path("", views.chore_list, name="list"),
]
