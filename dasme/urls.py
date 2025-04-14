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
    path("api/lp_create/", views.create_lp, name="create_lp"),
    path("api/lp_info/", views.lp_info, name="lp_info"),
    path("api/add_user/", views.add_user, name="add_user"),
    path("api/remove_user/", views.remove_user, name="remove_user"),
    path("api/edit_perms/", views.edit_perms, name="edit_perms"),
    path("api/remove_user/", views.remove_user, name="remove_user"),
    path("api/join_lp/", views.join_lp, name="join_lp"),
    path("api/leave_lp/", views.leave_lp, name="leave_lp"),
    path("api/que_query/", views.que_query, name="que_query"),
    path("api/add_to_que/", views.add_to_que, name="add_to_que"),
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
