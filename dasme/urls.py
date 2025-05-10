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
    # Profile management routes
    path("api/create_profile/", views.create_profile, name="create_profile"),
    path("api/lp_create/", views.create_lp, name="create_lp"),
    path("api/lp_info/", views.lp_info, name="lp_info"),
    path("api/add_user/", views.add_user, name="add_user"),
    path("api/remove_user/", views.remove_user, name="remove_user"),
    path("api/edit_perms/", views.edit_perms, name="edit_perms"),
    path("api/join_lp/", views.join_lp, name="join_lp"),
    path("api/leave_lp/", views.leave_lp, name="leave_lp"),
    path("api/que_query/", views.que_query, name="que_query"),
    path("api/add_to_que/", views.add_to_que, name="add_to_que"),
    path(
        "api/disconnect_spotify/", views.disconnect_spotify, name="disconnect_spotify"
    ),
    path("api/forward/", views.forward, name="forward"),
    path("api/friends/", views.friends, name="friends"),
    path("api/currently_playing/", views.check_current_playing, name="playing"),
    path("api/mobile-sync/", views.check_lp_sync, name="sync"),
    path("api/get-mobile-lps", views.get_mobile_lp_users),
]
