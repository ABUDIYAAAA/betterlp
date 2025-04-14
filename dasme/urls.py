from django.urls import path
from . import views

urlpatterns = [
    # Spotify-related routes
    path("callback/", views.save_tokens, name="spotify-callback"),
    path(
        "api/verify_tokens/<int:discord_user_id>/",
        views.verify_tokens,
        name="verify_tokens",
    ),
    path(
        "api/get_currently_playing/<int:discord_user_id>/",
        views.get_currently_playing,
        name="get_currently_playing",
    ),
    # Profile management routes
    path("api/create_profile/", views.create_profile, name="create_profile"),
    #     path(
    #         "api/add_user_to_profile/",
    #         views.add_user_to_profile,
    #         name="add_user_to_profile",
    #     ),
    #     path(
    #         "api/update_user_settings/",
    #         views.update_user_settings,
    #         name="update_user_settings",
    #     ),
]
