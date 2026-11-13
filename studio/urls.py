from django.urls import path

from . import views

app_name = "studio"

urlpatterns = [
    path("", views.home, name="home"),
    path("add/", views.quick_add, name="quick_add"),
    path("pieces/", views.project_list, name="project_list"),
    path("pieces/<int:pk>/", views.project_detail, name="project_detail"),
    path("entries/<int:pk>/", views.entry_edit, name="entry_edit"),
    path("photos/<int:pk>/delete/", views.photo_delete, name="photo_delete"),
    path("glazes/", views.glaze_list, name="glaze_list"),
    path("glazes/<int:pk>/", views.glaze_detail, name="glaze_detail"),
    path("manifest.webmanifest", views.manifest, name="manifest"),
]
