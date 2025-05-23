import requests
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from .models import UserToken, ListenParty, Friendship
import json
from django.shortcuts import get_object_or_404
from django.contrib.auth.models import User
import time
from django.views.decorators.http import require_GET

# Replace or add these in your settings.py
CLIENT_ID = "ffd54fb8f0ce49d4a7eb7ec31d0a2f6a"
CLIENT_SECRET = "178fa9b9c6bc4f4c8261cf632233f36f"
REDIRECT_URI = r"https://abudiyaaaaa.pythonanywhere.com/callback"


@csrf_exempt
def save_tokens(request):
    if request.method == "GET":
        code = request.GET.get("code")
        state = request.GET.get("state")  # Discord user ID passed as state

        if not code or not state:
            return JsonResponse({"error": "Missing code or state"}, status=400)

        # Exchange the authorization code for tokens
        token_res = requests.post(
            "https://accounts.spotify.com/api/token",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": REDIRECT_URI,
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

        token_data = token_res.json()

        if "access_token" in token_data:
            UserToken.objects.update_or_create(
                discord_user_id=state,
                defaults={
                    "access_token": token_data["access_token"],
                    "refresh_token": token_data.get("refresh_token", ""),
                },
            )
            return HttpResponse(
                f"<h2>✅ Auth successful!</h2>"
                f'<p><a href="discord://">Click here to open Discord</a></p>'
            )

        return JsonResponse(
            {"error": "Token exchange failed", "response": token_data}, status=400
        )

    return JsonResponse({"error": "Method not allowed"}, status=405)


def refresh_token_util(refresh_token):
    """Refresh the Spotify access token."""
    url = "https://accounts.spotify.com/api/token"
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    data = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,  # This is required for server-side apps
    }

    try:
        response = requests.post(url, headers=headers, data=data)
        response.raise_for_status()  # Raise an exception for HTTP errors
        return response.json(), None
    except requests.exceptions.RequestException as e:
        error_message = f"Failed to refresh token: {str(e)}"
        if response and hasattr(response, "text"):
            try:
                error_data = response.json()
                if "error_description" in error_data:
                    error_message = error_data["error_description"]
                elif "error" in error_data:
                    error_message = error_data["error"]
            except:
                error_message = f"Status code: {response.status_code}, Response: {response.text[:100]}"

        return None, error_message


@csrf_exempt
def check_lp_sync(request):
    if request.method != "POST":
        return JsonResponse({"error": "Only POST allowed"}, status=405)

    try:
        data = json.loads(request.body)
        owner_id = data.get("owner_id")
        joiner_id = data.get("joiner_id")
        lp_id = data.get("lp_id")

        if not all([owner_id, joiner_id, lp_id]):
            return JsonResponse({"error": "Missing fields"}, status=400)

        try:
            lp = ListenParty.objects.get(id=lp_id)

            # Check if joiner is still connected to this LP
            connected = [l.id for l in lp.connected.all()]
            if joiner_id not in connected and lp.owner.id != owner_id:
                return JsonResponse(
                    {"status": "remove", "reason": connected}, status=200
                )

            # Optional: ensure they are still friends

            # Refresh both tokens
            owner = None
            joiner = None
            try:
                owner = UserToken.objects.get(discord_user_id=owner_id)
            except UserToken.DoesNotExist:
                return JsonResponse(
                    {"status": "remove", "reason": "owner token not found"}, status=200
                )
            try:
                joiner = UserToken.objects.get(discord_user_id=joiner_id)

            except UserToken.DoesNotExist:
                return JsonResponse(
                    {"status": "remove", "reason": "joiner token not found"}, status=200
                )

            token1, error1 = refresh_token_util(owner.refresh_token)
            token2, error2 = refresh_token_util(joiner.refresh_token)
            if token1:
                owner.access_token = token1["access_token"]
                if "refresh_token" in token1:
                    owner.refresh_token = token1["refresh_token"]
                owner.save()
            if token2:
                joiner.access_token = token2["access_token"]
                if "refresh_token" in token2:
                    joiner.refresh_token = token2["refresh_token"]
                joiner.save()
            if not token1 or not token2:
                return JsonResponse(
                    {"status": "remove", "reason": [error1, error2]}, status=200
                )

            # Get current tracks
            owner_playing = get_currently_playing_util(owner_id)
            joiner_playing = get_currently_playing_util(joiner_id)

            # If host is not playing, skip syncing
            if not owner_playing["is_playing"]:
                return JsonResponse(
                    {"status": "ok", "reason": "host not playing"}, status=200
                )

            # If joiner is not playing or track differs, sync
            if (
                not joiner_playing["is_playing"]
                or joiner_playing["track_uri"] != owner_playing["track_uri"]
            ):
                play_track_util(
                    user_id=joiner_id,
                    track_uri=owner_playing["track_uri"],
                    progress_ms=owner_playing["progress_ms"],
                )
                return JsonResponse({"status": "synced"}, status=200)

            return JsonResponse(
                {"status": "ok", "reason": "already synced"}, status=200
            )

        except ListenParty.DoesNotExist:
            return JsonResponse(
                {"status": "remove", "reason": "lp not found"}, status=200
            )

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


@csrf_exempt
def verify_tokens(request, discord_user_id):
    """Verify and refresh Spotify tokens for a Discord user."""
    try:
        # Get user token
        user_token = UserToken.objects.get(discord_user_id=discord_user_id)
        access_token = user_token.access_token
        refresh_token = user_token.refresh_token

        # First verify if current token is valid
        headers = {"Authorization": f"Bearer {access_token}"}
        try:
            response = requests.get("https://api.spotify.com/v1/me", headers=headers)

            # If token is valid, return success
            if response.status_code == 200:
                return JsonResponse(
                    {
                        "linked": True,
                        "valid": True,
                        "username": response.json().get("display_name", "Unknown"),
                        "profile_url": response.json()
                        .get("external_urls", {})
                        .get("spotify", ""),
                    }
                )

            # If unauthorized, try to refresh token
            elif response.status_code == 401:
                token_data, error = refresh_token_util(refresh_token)

                if token_data:
                    # Save the new tokens
                    user_token.access_token = token_data["access_token"]
                    new_access_token = token_data["access_token"]
                    # Not all token refreshes return a new refresh token
                    if "refresh_token" in token_data:
                        new_refresh_token = token_data["refresh_token"]
                        user_token.refresh_token = new_refresh_token
                    user_token.save()

                    # Verify the new token works
                    headers = {"Authorization": f"Bearer {new_access_token}"}
                    verify_response = requests.get(
                        "https://api.spotify.com/v1/me", headers=headers
                    )

                    if verify_response.status_code == 200:
                        user_data = verify_response.json()
                        return JsonResponse(
                            {
                                "linked": True,
                                "valid": True,
                                "refreshed": True,
                                "username": user_data.get("display_name", "Unknown"),
                                "profile_url": user_data.get("external_urls", {}).get(
                                    "spotify", ""
                                ),
                            }
                        )
                    else:
                        return JsonResponse(
                            {
                                "linked": True,
                                "valid": False,
                                "error": "Token refreshed but validation failed",
                                "details": verify_response.text,
                            }
                        )
                else:
                    # Return the specific error from Spotify
                    return JsonResponse(
                        {
                            "linked": True,
                            "valid": False,
                            "error": "Failed to refresh token",
                            "details": error,
                        }
                    )
            else:
                # Other error occurred with the Spotify API
                return JsonResponse(
                    {
                        "linked": True,
                        "valid": False,
                        "error": f"Spotify API error: {response.status_code} {response.text}",
                        "details": response.text,
                    }
                )

        except requests.exceptions.RequestException as e:
            return JsonResponse(
                {
                    "linked": True,
                    "valid": False,
                    "error": "Network error checking token",
                    "details": str(e),
                }
            )

    except UserToken.DoesNotExist:
        return JsonResponse(
            {
                "linked": False,
                "valid": False,
                "error": "No Spotify connection found",
                "action_required": "Please link your Spotify account",
            }
        )

    except Exception as e:
        # Log unexpected errors for debugging
        import traceback

        error_details = traceback.format_exc()
        print(f"Unexpected error in verify_tokens: {str(e)}")
        print(error_details)

        return JsonResponse(
            {
                "linked": False,
                "valid": False,
                "error": "An unexpected error occurred",
                "details": str(e),
            },
            status=500,
        )


@csrf_exempt
def create_profile(request):
    """Create or retrieve a profile for the given username."""
    if request.method == "POST":
        data = json.loads(request.body)
        user, c = User.objects.get_or_create(username=data["username"], id=data["id"])
        return JsonResponse({"user_id": user.id, "created": c})


@csrf_exempt
def create_lp(request):
    """Create a new Listen Party."""
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            user = User.objects.get(id=data["owner"])
            obj, created = ListenParty.objects.get_or_create(
                owner=user,
            )
            obj.connected.add(user)
            obj.save()
            return JsonResponse({"created": created}, status=200)
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=400)


@csrf_exempt
def lp_info(request):
    """Get information about the current Listen Party."""
    try:
        data = json.loads(request.body)
        user = User.objects.get(id=data["owner"])

        obj = get_listen_party(user)
        if not obj:
            return JsonResponse({"error": "ListenParty not found."}, status=404)

        is_owner = obj.owner == user
        try:
            token = UserToken.objects.get(
                discord_user_id=user.id if is_owner else obj.owner.id
            )
        except UserToken.DoesNotExist:
            return JsonResponse({"error": "Spotify token not found."}, status=404)

        queue_items = fetch_spotify_queue(token.access_token, token.refresh_token)

        if not queue_items:
            return JsonResponse({"error": "Failed to fetch Spotify queue."}, status=500)

        connected_users = [u.username for u in obj.connected.all()]
        mobile_users = [u.username for u in obj.mobile_lp_users.all()]

        return JsonResponse(
            {
                "owner": obj.owner.username,
                "owner_id": obj.owner.id,
                "queue": queue_items,
                "connected": connected_users,
                "mobile_users": mobile_users,
                "using_spotify_data": True,
            }
        )

    except User.DoesNotExist:
        return JsonResponse({"error": "User not found."}, status=404)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON."}, status=400)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


def fetch_spotify_queue(access_token, refresh_token):
    headers = {"Authorization": f"Bearer {access_token}"}

    try:
        current_response = requests.get(
            "https://api.spotify.com/v1/me/player/currently-playing", headers=headers
        )

        if current_response.status_code == 401:
            token_data, error = refresh_token_util(refresh_token)

            if not token_data:
                return None

            access_token = token_data["access_token"]
            headers = {"Authorization": f"Bearer {access_token}"}

            try:
                user_token = UserToken.objects.get(refresh_token=refresh_token)
                user_token.access_token = access_token
                if "refresh_token" in token_data:
                    user_token.refresh_token = token_data["refresh_token"]
                user_token.save()
            except UserToken.DoesNotExist:
                pass

            current_response = requests.get(
                "https://api.spotify.com/v1/me/player/currently-playing",
                headers=headers,
            )

        if current_response.status_code not in [200, 204]:
            return None

        queue_response = requests.get(
            "https://api.spotify.com/v1/me/player/queue", headers=headers
        )

        if queue_response.status_code != 200:
            return None

        queue_data = queue_response.json()
        result = []

        if current_response.status_code == 200 and current_response.content:
            current_data = current_response.json()
            if current_data.get("item"):
                track = current_data["item"]
                result.append(
                    {
                        "id": None,
                        "title": track.get("name", "Unknown"),
                        "artist": ", ".join(
                            [artist["name"] for artist in track.get("artists", [])]
                        ),
                        "album": track.get("album", {}).get("name", "Unknown"),
                        "duration": track.get("duration_ms", 0),
                        "spotify_id": track.get("id"),
                        "added_by": None,
                        "position": 0,
                        "is_playing": True,
                        "album_art": track.get("album", {})
                        .get("images", [{}])[0]
                        .get("url"),
                        "progress_ms": current_data.get("progress_ms", 0),
                        "timestamp": current_data.get(
                            "timestamp", int(time.time() * 1000)
                        ),  # ✅ ADD THIS
                    }
                )

        position = 1
        for track in queue_data.get("queue", []):
            result.append(
                {
                    "id": None,
                    "title": track.get("name", "Unknown"),
                    "artist": ", ".join(
                        [artist["name"] for artist in track.get("artists", [])]
                    ),
                    "album": track.get("album", {}).get("name", "Unknown"),
                    "duration": track.get("duration_ms", 0),
                    "spotify_id": track.get("id"),
                    "added_by": None,
                    "position": position,
                    "is_playing": False,
                    "album_art": track.get("album", {})
                    .get("images", [{}])[0]
                    .get("url"),
                }
            )
            position += 1

        return result

    except requests.exceptions.RequestException:
        return None


@csrf_exempt
def add_user(request):
    """Add a user to the profile of the given username."""
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            user = data["user"]
            friend = data["friend"]
            friendship, created = Friendship.objects.get_or_create(
                user=User.objects.get(id=user), friend=User.objects.get(id=friend)
            )
            return JsonResponse({"created": created}, status=200)
        except Exception as e:
            return JsonResponse({"error": str(e)})


@csrf_exempt
def edit_perms(request):
    """Edit permissions for a user in a profile."""
    if request.method == "POST":
        data = json.loads(request.body)
        try:
            friendship = Friendship.objects.get(
                user=User.objects.get(id=data["user"]),
                friend=User.objects.get(id=data["friend"]),
            )
            friendship.can_forward = data.get("can_forward", friendship.can_forward)
            friendship.can_que = data.get("can_que", friendship.can_que)
            friendship.save()
            return JsonResponse({"success": True}, status=200)
        except Friendship.DoesNotExist:
            return JsonResponse({"error": "User not added"}, status=404)


@csrf_exempt
def remove_user(request):
    """Add a user to the profile of the given username."""
    if request.method == "POST":
        data = json.loads(request.body)
        user = data["user"]
        friend = data["friend"]
        try:
            friendship = Friendship.objects.get(
                user=User.objects.get(id=user), friend=User.objects.get(id=friend)
            )
            friendship.delete()
            return JsonResponse({"success": True}, status=200)
        except Friendship.DoesNotExist:
            return JsonResponse({"error": "User not added"}, status=404)


def try_skip_next(access_token):
    return requests.post(
        "https://api.spotify.com/v1/me/player/next",
        headers={"Authorization": f"Bearer {access_token}"},
    )


def refresh_and_retry(tokens):
    token_data, error = refresh_token_util(tokens.refresh_token)
    if not token_data:
        return None, JsonResponse({"error": error}, status=400)

    tokens.access_token = token_data["access_token"]
    if "refresh_token" in token_data:
        tokens.refresh_token = token_data["refresh_token"]
    tokens.save()

    return try_skip_next(tokens.access_token), None


@csrf_exempt
def forward(request):
    if request.method != "POST":
        return JsonResponse({"error": "Only POST allowed"}, status=405)

    data = json.loads(request.body)
    user = User.objects.get(id=data["user"])

    # Try as owner
    obj = ListenParty.objects.prefetch_related("connected").filter(owner=user).first()

    if not obj:
        # Try as connected user
        obj = (
            ListenParty.objects.prefetch_related("connected")
            .filter(connected=user)
            .first()
        )
        if not obj:
            return JsonResponse(
                {"error": "You are not in a listening party"}, status=404
            )

        if not Friendship.objects.filter(
            user=obj.owner, friend=user, can_forward=True
        ).exists():
            return JsonResponse({"error": "You are not allowed to forward"}, status=403)

        tokens = UserToken.objects.get(discord_user_id=obj.owner.id)
    else:
        tokens = UserToken.objects.get(discord_user_id=user.id)

    response = try_skip_next(tokens.access_token)
    if response.status_code == 204:
        return JsonResponse({"success": True}, status=200)
    elif response.status_code == 401:
        refreshed_response, error_response = refresh_and_retry(tokens)
        if error_response:
            return error_response
        if refreshed_response.status_code == 204:
            return JsonResponse({"success": True}, status=200)
        else:
            return JsonResponse(
                {"error": refreshed_response.text},
                status=refreshed_response.status_code,
            )

    return JsonResponse({"error": response.text}, status=response.status_code)


def play_track_util(discord_user_id, track_uri, progress_ms):
    """Plays the specified track for a user at the given progress position."""
    try:
        # Get user's token
        user_token = UserToken.objects.get(discord_user_id=discord_user_id)
        access_token = user_token.access_token

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }

        data = {
            "uris": [track_uri],
            "position_ms": progress_ms,
        }

        response = requests.put(
            "https://api.spotify.com/v1/me/player/play", headers=headers, json=data
        )

        if response.status_code == 204:
            return {"success": True}
        elif response.status_code == 401:
            # Refresh token if expired
            token_data, error = refresh_token_util(user_token.refresh_token)
            if token_data:
                user_token.access_token = token_data["access_token"]
                if "refresh_token" in token_data:
                    user_token.refresh_token = token_data["refresh_token"]
                user_token.save()
                return play_track_util(discord_user_id, track_uri, progress_ms)
            else:
                return {"error": f"Token refresh failed: {error}"}
        else:
            return {
                "error": f"Failed to play track. Status: {response.status_code}, Response: {response.text}"
            }

    except UserToken.DoesNotExist:
        return {"error": "User token not found"}


@require_GET
@csrf_exempt
def get_mobile_lp_users(request):
    results = []

    for lp in ListenParty.objects.prefetch_related("mobile_lp_users").all():
        owner_id = lp.owner.id
        lp_id = lp.id
        for mobile_user in lp.mobile_lp_users.all():
            results.append(
                {
                    "owner_id": owner_id,
                    "joiner_id": mobile_user.id,
                    "lp_id": lp_id,
                }
            )

    return JsonResponse({"data": results})


@csrf_exempt
def join_lp(request):
    """Join a listening party."""
    try:
        if request.method == "POST":
            data = json.loads(request.body)
            user = User.objects.get(id=data["user"])
            friend = User.objects.get(id=data["friend"])
            mobile = data.get("mobile", False)
            if not mobile:
                obj = (
                    ListenParty.objects.prefetch_related("connected")
                    .filter(owner=friend)
                    .first()
                )
                if obj:
                    return JsonResponse(
                        {"error": "You are already hosting a lp"}, status=403
                    )

                if not obj:
                    # Try to find a ListenParty where the user is connected
                    obj = (
                        ListenParty.objects.prefetch_related("connected")
                        .filter(connected=friend)
                        .first()
                    )
                    if obj:
                        return JsonResponse(
                            {"error": "You are already in a lp"}, status=403
                        )

                if not obj:
                    if Friendship.objects.filter(user=user, friend=friend).exists():
                        if ListenParty.objects.filter(owner=user).exists():
                            in_lp = False
                            user_s = get_currently_playing_util(user.id)
                            friend_s = get_currently_playing_util(friend.id)
                            if user_s["is_playing"] and friend_s["is_playing"]:
                                if user_s["track_name"] == friend_s["track_name"]:
                                    in_lp = True
                            if in_lp:
                                try:
                                    lp = ListenParty.objects.get(owner=user)
                                    lp.connected.add(friend)
                                    lp.save()
                                    return JsonResponse({"success": True}, status=200)
                                except ListenParty.DoesNotExist:
                                    return JsonResponse(
                                        {"error": "Listening party not found"},
                                        status=404,
                                    )
                            else:
                                return JsonResponse(
                                    {"error": "You are not in an lp"}, status=403
                                )
                        else:
                            return JsonResponse(
                                {"error": "That user is not hosting a listen party"},
                                status=403,
                            )
                    else:
                        return JsonResponse({"error": "User not added"}, status=404)
            else:
                if ListenParty.objects.filter(owner=friend).exists():
                    return JsonResponse(
                        {"error": "You are already hosting a lp"}, status=403
                    )
                obj = ListenParty.objects.filter(owner=user).first()
                if obj:
                    if Friendship.objects.filter(user=user, friend=friend).exists():
                        try:
                            lp = ListenParty.objects.get(owner=user)
                            lp.connected.add(friend)
                            lp.mobile_lp_users.add(friend)
                            lp.save()
                            return JsonResponse({"success": True}, status=200)
                        except ListenParty.DoesNotExist:
                            return JsonResponse(
                                {"error": "Listening party not found"}, status=404
                            )
                    else:
                        return JsonResponse({"error": "User not added"}, status=404)

                else:
                    return JsonResponse(
                        {"error": "That user is not hosting a listen party"}, status=403
                    )
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


@csrf_exempt
def leave_lp(request):
    """Leave a listening party."""
    if request.method == "POST":
        data = json.loads(request.body)
        user = User.objects.get(id=data["user"])

        # Try to find a ListenParty the user owns
        obj = (
            ListenParty.objects.prefetch_related("connected").filter(owner=user).first()
        )
        if obj:
            obj.delete()
            return JsonResponse({"success": True}, status=200)

        if not obj:
            # Try to find a ListenParty where the user is connected
            obj = (
                ListenParty.objects.prefetch_related("connected")
                .filter(connected=user)
                .first()
            )
            obj.connected.remove(user)
            obj.save()
            return JsonResponse({"success": True}, status=200)

        if not obj:
            # Try to find a ListenParty where the user is a mobile user
            obj = (
                ListenParty.objects.prefetch_related("connected")
                .filter(mobile_lp_users=user)
                .first()
            )
            obj.mobile_lp_users.remove(user)
            obj.save()
            return JsonResponse({"success": True}, status=200)

        if not obj:
            return JsonResponse({"error": "ListenParty not found."}, status=404)


@csrf_exempt
def que_query(request):
    """Add a track to the queue."""
    if request.method == "POST":
        data = json.loads(request.body)
        user = User.objects.get(id=data["user"])
        query = data["query"]

        try:
            owner = False
            obj = (
                ListenParty.objects.prefetch_related("connected")
                .filter(owner=user)
                .first()
            )

            if obj:
                owner = True
            else:
                # Try to find a ListenParty where the user is connected
                obj = (
                    ListenParty.objects.prefetch_related("connected")
                    .filter(connected=user)
                    .first()
                )

            if not obj:
                # Try to find a ListenParty where the user is a mobile user
                obj = (
                    ListenParty.objects.prefetch_related("connected")
                    .filter(mobile_lp_users=user)
                    .first()
                )

            if not obj:
                return JsonResponse(
                    {"error": "You are not in a listen party"}, status=404
                )

            # Check if user has permission to queue tracks
            can_queue = owner or (
                obj
                and Friendship.objects.filter(user=obj.owner, friend=user).exists()
                and Friendship.objects.filter(user=obj.owner, friend=user)
                .first()
                .can_que
            )

            if not can_queue:
                return JsonResponse(
                    {"error": "You don't have permission to queue tracks"}, status=403
                )

            # User has permission, proceed with the API request
            user_token = UserToken.objects.get(discord_user_id=user.id)
            access_token = user_token.access_token
            refresh_token = user_token.refresh_token
            url = "https://api.spotify.com/v1/search"
            headers = {"Authorization": f"Bearer {access_token}"}
            params = {"q": query, "type": "track", "limit": 5}

            res = requests.get(url, headers=headers, params=params)
            if res.status_code == 401:
                token_data, error = refresh_token_util(refresh_token)

                if token_data:
                    # Save the new tokens
                    user_token.access_token = token_data["access_token"]
                    # Not all token refreshes return a new refresh token
                    if "refresh_token" in token_data:
                        user_token.refresh_token = token_data["refresh_token"]
                    user_token.save()

                    # Verify the new token works
                    headers = {"Authorization": f"Bearer {user_token.access_token}"}
                    verify_response = requests.get(
                        "https://api.spotify.com/v1/me", headers=headers
                    )

                    if verify_response.status_code == 200:
                        # Retry the search with the new token
                        headers = {"Authorization": f"Bearer {access_token}"}
                        res = requests.get(url, headers=headers, params=params)
                        if res.status_code != 200:
                            return JsonResponse(
                                {"error": "Failed to search for track"}, status=400
                            )
                else:
                    return JsonResponse(
                        {"error": error},
                        status=400,
                    )

            if res.status_code == 200:
                return JsonResponse(
                    {"data": res.json().get("tracks", {}).get("items", [])}
                )
            else:
                return JsonResponse(
                    {"error": f"API request failed with status {res.status_code}"},
                    status=400,
                )

        except Exception as e:
            return JsonResponse({"error": str(e)}, status=400)

    return JsonResponse({"error": "Only POST method is allowed"}, status=405)


def get_listen_party(user):
    """Get ListenParty where user is owner or connected."""
    return (
        ListenParty.objects.prefetch_related("connected").filter(owner=user).first()
        or ListenParty.objects.prefetch_related("connected")
        .filter(connected=user)
        .first()
    )


def refresh_and_retry_token(user_token, uri):
    token_data, error = refresh_token_util(user_token.refresh_token)
    if not token_data:
        return None, error
    user_token.access_token = token_data["access_token"]
    if "refresh_token" in token_data:
        user_token.refresh_token = token_data["refresh_token"]
    user_token.save()
    headers = {"Authorization": f"Bearer {user_token.access_token}"}
    try:
        verify_response = requests.get("https://api.spotify.com/v1/me", headers=headers)
        if verify_response.status_code == 200:
            return make_spotify_request(user_token.access_token, uri)
        else:
            return (
                None,
                f"Token refresh failed with status code {verify_response.status_code}",
            )
    except requests.exceptions.RequestException as e:
        return None, str(e)


def make_spotify_request(access_token, uri):
    endpoint = "https://api.spotify.com/v1/me/player/queue"
    headers = {"Authorization": f"Bearer {access_token}"}
    params = {"uri": uri}
    try:
        response = requests.post(endpoint, headers=headers, params=params)
        return response, None
    except requests.exceptions.RequestException as e:
        return None, str(e)


@csrf_exempt
def add_to_que(request):
    if request.method != "POST":
        return JsonResponse({"error": "Invalid method"}, status=405)
    try:
        data = json.loads(request.body)
        user = get_object_or_404(User, id=data["user"])
        uri = data["uri"]
        party = get_listen_party(user)
        if not party:
            return JsonResponse({"error": "You are not in a listen party"}, status=404)
        is_owner = party.owner == user
        user_token = UserToken.objects.get(
            discord_user_id=user.id if is_owner else party.owner.id
        )
        response, error = make_spotify_request(user_token.access_token, uri)
        if response:
            if response.status_code == 204:
                return JsonResponse({"success": True}, status=200)
            elif response.status_code == 401:
                response, error = refresh_and_retry_token(user_token, uri)
                if response and response.status_code == 204:
                    return JsonResponse({"success": True}, status=200)
                else:
                    return JsonResponse({"error": error or "Unauthorized"}, status=401)
            else:
                return JsonResponse(
                    {"error": f"Spotify API error: {response.status_code}"},
                    status=response.status_code,
                )
        else:
            return JsonResponse(
                {"error": error or "No response from Spotify API"}, status=400
            )
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=400)


@csrf_exempt
def disconnect_spotify(request):
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            discord_user_id = data.get("user_id")
            if not discord_user_id:
                return JsonResponse({"error": "Missing user_id"}, status=400)

            # Delete the user's tokens and remove them from any listening party
            UserToken.objects.filter(discord_user_id=discord_user_id).delete()

            user = User.objects.get(id=discord_user_id)

            # Remove from listening party
            ListenParty.objects.filter(owner=user).delete()
            for party in ListenParty.objects.filter(connected=user):
                party.connected.remove(user)

            return JsonResponse({"success": True})

        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)
    return JsonResponse({"error": "Invalid method"}, status=405)


@csrf_exempt
def friends(request):
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            user = User.objects.get(id=data["user"])
            friends = Friendship.objects.filter(user=user).select_related("friend")
            friend_list = [
                {
                    "id": f.friend.id,
                    "name": f.friend.username,
                    "can_forward": f.can_forward,
                    "can_que": f.can_que,  # Added this field to track queue permissions
                }
                for f in friends
            ]
            return JsonResponse({"friends": friend_list}, status=200)
        except User.DoesNotExist:
            return JsonResponse({"error": "User not found"}, status=404)
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)
    return JsonResponse({"error": "Only POST method is allowed"}, status=405)


@csrf_exempt
def check_current_playing(request):
    """Get the currently playing track for a user."""
    if request.method != "POST":
        return JsonResponse({"error": "Only POST method is allowed"}, status=405)

    try:
        data = json.loads(request.body)
        discord_user_id = data.get("user_id")

        if not discord_user_id:
            return JsonResponse({"error": "Missing user_id parameter"}, status=400)

        # Try to get the token for the user
        try:
            user_token = UserToken.objects.get(discord_user_id=discord_user_id)
        except UserToken.DoesNotExist:
            return JsonResponse({"error": "User not connected to Spotify"}, status=404)

        access_token = user_token.access_token
        refresh_token = user_token.refresh_token

        # Call Spotify API to get currently playing
        headers = {"Authorization": f"Bearer {access_token}"}
        response = requests.get(
            "https://api.spotify.com/v1/me/player/currently-playing", headers=headers
        )

        # Handle different response status codes
        if response.status_code == 204:
            return JsonResponse(
                {"is_playing": False, "message": "No track currently playing"}
            )

        elif response.status_code == 200:
            data = response.json()

            if not data or not data.get("item"):
                return JsonResponse(
                    {"is_playing": False, "message": "No track details available"}
                )

            track = data["item"]
            is_playing = data.get("is_playing", False)

            result = {
                "is_playing": is_playing,
                "track_name": track.get("name", "Unknown"),
                "artist_name": ", ".join(
                    [artist["name"] for artist in track.get("artists", [])]
                ),
                "album": track.get("album", {}).get("name", "Unknown"),
                "duration_ms": track.get("duration_ms", 0),
                "progress_ms": data.get("progress_ms", 0),
                "album_art": track.get("album", {})
                .get("images", [{}])[0]
                .get("url", ""),
                "spotify_url": track.get("external_urls", {}).get("spotify", ""),
                "timestamp": data.get("timestamp", 0),
            }

            return JsonResponse(result)

        elif response.status_code == 401:
            # Token expired, try to refresh
            token_data, error = refresh_token_util(refresh_token)

            if not token_data:
                return JsonResponse(
                    {"error": f"Failed to refresh token: {error}"}, status=401
                )

            # Update tokens in database
            user_token.access_token = token_data["access_token"]
            if "refresh_token" in token_data:
                user_token.refresh_token = token_data["refresh_token"]
            user_token.save()

            # Retry the request with new token
            headers = {"Authorization": f"Bearer {token_data['access_token']}"}
            response = requests.get(
                "https://api.spotify.com/v1/me/player/currently-playing",
                headers=headers,
            )

            if response.status_code == 200:
                data = response.json()

                if not data or not data.get("item"):
                    return JsonResponse(
                        {"is_playing": False, "message": "No track details available"}
                    )

                track = data["item"]
                is_playing = data.get("is_playing", False)

                result = {
                    "is_playing": is_playing,
                    "track_name": track.get("name", "Unknown"),
                    "artist_name": ", ".join(
                        [artist["name"] for artist in track.get("artists", [])]
                    ),
                    "album": track.get("album", {}).get("name", "Unknown"),
                    "duration_ms": track.get("duration_ms", 0),
                    "progress_ms": data.get("progress_ms", 0),
                    "album_art": track.get("album", {})
                    .get("images", [{}])[0]
                    .get("url", ""),
                    "spotify_url": track.get("external_urls", {}).get("spotify", ""),
                    "timestamp": data.get("timestamp", 0),
                }

                return JsonResponse(result)

            elif response.status_code == 204:
                return JsonResponse(
                    {"is_playing": False, "message": "No track currently playing"}
                )

            else:
                return JsonResponse(
                    {"error": f"API request failed with status {response.status_code}"},
                    status=response.status_code,
                )

        else:
            return JsonResponse(
                {"error": f"API request failed with status {response.status_code}"},
                status=response.status_code,
            )

    except UserToken.DoesNotExist:
        return JsonResponse({"error": "User not connected to Spotify"}, status=404)

    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON in request body"}, status=400)

    except Exception as e:
        # Log the exception for debugging
        print(f"Error in check_current_playing: {str(e)}")
        return JsonResponse({"error": str(e)}, status=500)


def get_currently_playing_util(discord_user_id):
    try:
        # Step 1: Retrieve the user's token
        user_token = UserToken.objects.get(discord_user_id=discord_user_id)
        access_token = user_token.access_token

        # Step 2: Use the Spotify API to fetch the currently playing track
        headers = {"Authorization": f"Bearer {access_token}"}
        response = requests.get(
            "https://api.spotify.com/v1/me/player/currently-playing", headers=headers
        )

        if response.status_code == 200:
            data = response.json()
            if data and data.get("is_playing"):
                track_name = data["item"]["name"]
                artist_name = ", ".join(
                    artist["name"] for artist in data["item"]["artists"]
                )
                duration_ms = data["item"]["duration_ms"]
                progress_ms = data["progress_ms"]

                return {
                    "is_playing": True,
                    "track_name": track_name,
                    "artist_name": artist_name,
                    "duration_ms": duration_ms,
                    "progress_ms": progress_ms,
                }

            else:
                return {"is_playing": False, "message": "Not playing anything"}

        elif response.status_code == 401:
            token_data, error = refresh_token_util(user_token.refresh_token)

            if token_data:
                # Save the new tokens
                user_token.access_token = token_data["access_token"]
                # Not all token refreshes return a new refresh token
                if "refresh_token" in token_data:
                    user_token.refresh_token = token_data["refresh_token"]
                user_token.save()

                # Verify the new token works
                headers = {"Authorization": f"Bearer {user_token.access_token}"}
                verify_response = requests.get(
                    "https://api.spotify.com/v1/me", headers=headers
                )

                if verify_response.status_code == 200:
                    return get_currently_playing_util(discord_user_id)
        else:
            return {"error": "Failed to fetch currently playing track"}
    except UserToken.DoesNotExist:
        return {"error": "User token not found"}
