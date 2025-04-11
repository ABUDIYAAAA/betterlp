"""
URL configuration for spotifymoo project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/4.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from django.contrib import admin
from django.urls import path, include
from dasme import views

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("dasme.urls")),
    path("api/save_tokens/", views.save_tokens, name="save_tokens"),
    path(
        "api/verify_tokens/<int:discord_user_id>/",
        views.verify_tokens,
        name="verify_tokens",
    ),
    path(
        "callback", views.save_tokens, name="callback"
    ),  # Handle GET requests for callback
    path(
        "api/get_currently_playing/<int:discord_user_id>/",
        views.get_currently_playing,
        name="get_currently_playing",
    ),
]
