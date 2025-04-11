from django.urls import path
from . import views

urlpatterns = [
    path("login/", views.login, name="spotify-login"),
    path("callback/", views.callback, name="spotify-callback"),
]
