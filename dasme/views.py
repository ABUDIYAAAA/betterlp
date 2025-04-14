import requests
from django.http import HttpResponse, HttpResponseRedirect, JsonResponse
from django.conf import settings
from urllib.parse import urlencode
from django.views.decorators.csrf import csrf_exempt
from .models import UserToken, ListenParty, Friendship, Track
import json
from django.shortcuts import redirect
from django.contrib.auth.models import User

# Replace or add these in your settings.py
CLIENT_ID = "a1358e7bde1741bd9a7d0242d77dd9fb"
CLIENT_SECRET = "772fe3710f7d4491b8202bf52e1a0b2b"
REDIRECT_URI = r"https://abudiyaaaaa.pythonanywhere.com/callback"
SCOPE = "user-read-playback-state user-modify-playback-state user-read-private"


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
                "client_secret": CLIENT_SECRET,  # Spotify Client Secret
            },
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

    return JsonResponse({"error": "Method not allowed"}, status=405)


@csrf_exempt  # Add this decorator to exempt CSRF checks
def verify_tokens(request, discord_user_id):
    try:
        user_token = UserToken.objects.get(discord_user_id=discord_user_id)
        access_token = user_token.access_token
        refresh_token = user_token.refresh_token
        headers = {"Authorization": f"Bearer {access_token}"}
        response = requests.get("https://api.spotify.com/v1/me", headers=headers)

        if response.status_code == 200:
            return JsonResponse({"linked": True, "valid": True})
        elif response.status_code == 401:
            url = "https://accounts.spotify.com/api/token"

            # Prepare headers and body
            headers = {"Content-Type": "application/x-www-form-urlencoded"}

            data = {
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": CLIENT_ID,
            }

            response = requests.post(url, headers=headers, data=data)

            if response.status_code == 200:
                # Parse the response
                response_data = response.json()

                # Store the new access token
                access_token = response_data["access_token"]
                refresh_token = response_data["refresh_token"]

                if access_token and refresh_token:
                    user_token.access_token = access_token
                    user_token.refresh_token = refresh_token
                    user_token.save()
                    return JsonResponse({"linked": True, "valid": True})
                else:
                    return JsonResponse(
                        {
                            "linked": True,
                            "valid": False,
                            "error": "Invalid or expired token",
                        }
                    )
        else:
            return JsonResponse(
                {"linked": True, "valid": False, "error": response.text},
                status=response.status_code,
            )
    except UserToken.DoesNotExist:
        return JsonResponse(
            {"linked": False, "valid": False, "error": "No token found"}
        )
    except Exception as e:
        # Log unexpected errors for debugging
        print(f"Unexpected error: {str(e)}")
        return JsonResponse(
            {"linked": False, "valid": False, "error": f"Unexpected error: {str(e)}"},
            status=500,
        )


def get_currently_playing(request, discord_user_id):
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

                return JsonResponse(
                    {
                        "is_playing": True,
                        "track_name": track_name,
                        "artist_name": artist_name,
                        "duration_ms": duration_ms,
                        "progress_ms": progress_ms,
                    }
                )
            else:
                return JsonResponse(
                    {"is_playing": False, "message": "Not playing anything"}
                )
        elif response.status_code == 401:
            return JsonResponse({"error": "Invalid or expired token"}, status=401)
        else:
            return JsonResponse(
                {"error": "Failed to fetch currently playing track"},
                status=response.status_code,
            )
    except UserToken.DoesNotExist:
        return JsonResponse({"error": "User token not found"}, status=404)


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

        # Try to find a ListenParty the user owns
        obj = (
            ListenParty.objects.prefetch_related("que", "connected")
            .filter(owner=user)
            .first()
        )

        if not obj:
            # Try to find a ListenParty where the user is connected
            obj = (
                ListenParty.objects.prefetch_related("que", "connected")
                .filter(connected=user)
                .first()
            )

        if not obj:
            return JsonResponse({"error": "ListenParty not found."}, status=404)

        que = [t.song_name for t in obj.que.all()]
        connected_users = [u.username for u in obj.connected.all()]

        return JsonResponse(
            {"owner": obj.owner.username, "que": que, "connected": connected_users}
        )

    except User.DoesNotExist:
        return JsonResponse({"error": "User not found."}, status=404)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON."}, status=400)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


@csrf_exempt
def add_user(request):
    """Add a user to the profile of the given username."""
    if request.method == "POST":
        data = json.loads(request.body)
        user = data["user"]
        friend = data["friend"]
        friendship, created = Friendship.objects.get_or_create(
            user=User.objects.get(id=user), friend=User.objects.get(id=friend)
        )
        return JsonResponse({"created": created}, status=200)


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
            new_token = refresh_token_util(user_token.refresh_token)
            if "access_token" in new_token:
                user_token.access_token = new_token["access_token"]
                user_token.refresh_token = new_token.get("refresh_token", "")
                user_token.save()
                return get_currently_playing_util(discord_user_id)
        else:
            return {"error": "Failed to fetch currently playing track"}
    except UserToken.DoesNotExist:
        return {"error": "User token not found"}


@csrf_exempt
def join_lp(request):
    """Join a listening party."""
    if request.method == "POST":
        data = json.loads(request.body)
        user = User.objects.get(id=data["user"])
        friend = User.objects.get(id=data["friend"])
        obj = (
            ListenParty.objects.prefetch_related("que", "connected")
            .filter(owner=friend)
            .first()
        )
        if obj:
            return JsonResponse({"error": "You are already hosting a lp"}, status=403)

        if not obj:
            # Try to find a ListenParty where the user is connected
            obj = (
                ListenParty.objects.prefetch_related("que", "connected")
                .filter(connected=friend)
                .first()
            )
            if obj:
                return JsonResponse({"error": "You are already in a lp"}, status=403)

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
                                {"error": "Listening party not found"}, status=404
                            )
                    else:
                        return JsonResponse(
                            {"error": "You are not in an lp"}, status=403
                        )
                else:
                    return JsonResponse(
                        {"error": "That user is not hosting a listen party"}, status=403
                    )
            else:
                return JsonResponse({"error": "User not added"}, status=404)


@csrf_exempt
def leave_lp(request):
    """Leave a listening party."""
    if request.method == "POST":
        data = json.loads(request.body)
        user = User.objects.get(id=data["user"])

        # Try to find a ListenParty the user owns
        obj = (
            ListenParty.objects.prefetch_related("que", "connected")
            .filter(owner=user)
            .first()
        )
        if obj:
            obj.delete()
            return JsonResponse({"success": True}, status=200)

        if not obj:
            # Try to find a ListenParty where the user is connected
            obj = (
                ListenParty.objects.prefetch_related("que", "connected")
                .filter(connected=user)
                .first()
            )
            obj.connected.remove(user)
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
                ListenParty.objects.prefetch_related("que", "connected")
                .filter(owner=user)
                .first()
            )

            if obj:
                owner = True
            else:
                # Try to find a ListenParty where the user is connected
                obj = (
                    ListenParty.objects.prefetch_related("que", "connected")
                    .filter(connected=user)
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
                # Token expired, refresh it
                token_data = refresh_token_util(refresh_token)
                access_token = token_data["access_token"]
                refresh_token = token_data["refresh_token"]
                user_token.access_token = access_token
                user_token.refresh_token = refresh_token
                user_token.save()

                # Retry the search with the new token
                headers = {"Authorization": f"Bearer {access_token}"}
                res = requests.get(url, headers=headers, params=params)
                if res.status_code != 200:
                    return JsonResponse(
                        {"error": "Failed to search for track"}, status=400
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


def refresh_token_util(refresh_token):
    """Refresh the Spotify access token."""
    url = "https://accounts.spotify.com/api/token"
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    data = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
    }

    response = requests.post(url, headers=headers, data=data)
    return response.json()


@csrf_exempt
def add_to_que(request):
    """Add a track to the queue."""
    if request.method == "POST":
        data = json.loads(request.body)
        user = User.objects.get(id=data["user"])
        uri = data["uri"]
        name = data["name"]
        try:
            owner = False
            obj = (
                ListenParty.objects.prefetch_related("que", "connected")
                .filter(owner=user)
                .first()
            )

            if obj:
                owner = True

            if not obj:
                # Try to find a ListenParty where the user is connected
                obj = (
                    ListenParty.objects.prefetch_related("que", "connected")
                    .filter(connected=user)
                    .first()
                )

            if not obj:
                return JsonResponse(
                    {"error": "You are not in a listen party"}, status=404
                )
            else:
                track, created = Track.objects.get_or_create(
                    song_id=uri, requester=user, song_name=name
                )
                obj.que.add(track)
                endpoint = "https://api.spotify.com/v1/me/player/queue"
                if owner:
                    user_token = UserToken.objects.get(discord_user_id=user.id)
                    access_token = user_token.access_token
                    headers = {"Authorization": f"Bearer {access_token}"}
                    params = {"uri": uri}

                    response = requests.post(endpoint, headers=headers, params=params)

                    if response.status_code == 204:
                        return JsonResponse({"success": True}, status=200)
                    elif response.status_code == 401:
                        # Token expired, refresh it
                        token_data = refresh_token_util(
                            UserToken.objects.get(discord_user_id=user.id).refresh_token
                        )
                        access_token = token_data["access_token"]
                        refresh_token = token_data["refresh_token"]
                        user_token.access_token = access_token
                        user_token.refresh_token = refresh_token
                        user_token.save()

                        # Retry the request with the new token
                        headers = {"Authorization": f"Bearer {access_token}"}
                        response = requests.post(
                            endpoint, headers=headers, params=params
                        )

                        if response.status_code == 204:
                            return JsonResponse({"success": True}, status=200)
                        else:
                            return JsonResponse(
                                {"error": response.text},
                                status=response.status_code,
                            )
                    else:
                        return JsonResponse(
                            {"error": response.text},
                            status=response.status_code,
                        )
                else:
                    user_token = UserToken.objects.get(discord_user_id=obj.owner.id)
                    access_token = user_token.access_token
                    headers = {"Authorization": f"Bearer {access_token}"}
                    params = {"uri": uri}

                    response = requests.post(endpoint, headers=headers, params=params)

                    if response.status_code == 204:
                        return JsonResponse({"success": True}, status=200)
                    elif response.status_code == 401:
                        # Token expired, refresh it
                        token_data = refresh_token_util(
                            UserToken.objects.get(discord_user_id=user.id).refresh_token
                        )
                        access_token = token_data["access_token"]
                        refresh_token = token_data["refresh_token"]
                        user_token.access_token = access_token
                        user_token.refresh_token = refresh_token
                        user_token.save()

                        # Retry the request with the new token
                        headers = {"Authorization": f"Bearer {access_token}"}
                        response = requests.post(
                            endpoint, headers=headers, params=params
                        )

                        if response.status_code == 204:
                            return JsonResponse({"success": True}, status=200)
                        else:
                            return JsonResponse(
                                {"error": response.text},
                                status=response.status_code,
                            )
                    else:
                        return JsonResponse(
                            {"error": response.text},
                            status=response.status_code,
                        )

        except Exception as e:
            return JsonResponse({"error": str(e)}, status=400)
