"""URL configuration for config project."""
from django.contrib import admin
from django.urls import include, path

from chores import views as chores_views

urlpatterns = [
    path("admin/", admin.site.urls),
    # Served from the site root so both get service-worker/manifest root scope.
    path("manifest.webmanifest", chores_views.manifest, name="manifest"),
    path("sw.js", chores_views.service_worker, name="service_worker"),
    path("", include("chores.urls")),
]
