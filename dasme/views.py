import requests
from django.http import HttpResponse, HttpResponseRedirect, JsonResponse
from django.conf import settings
from urllib.parse import urlencode
from django.views.decorators.csrf import csrf_exempt
from .models import UserToken, ListenParty
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
                owner=User.objects.get(id=state),
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


# @csrf_exempt
# def add_user_to_profile(request):
#     """Add a user to the profile of the given username."""
#     if request.method == "POST":
#         data = json.loads(request.body)
#         user = User.objects.get(username=data["username"])
#         profile = Profile.objects.get(
#             owner=user
#         )  # Automatically retrieve the user's profile
#         profile_user, created = ProfileUser.objects.get_or_create(
#             profile=profile, discord_user_id=data["discord_user_id"]
#         )
#         return JsonResponse({"profile_user_id": profile_user.id, "created": created})


# @csrf_exempt
# def update_user_settings(request):
#     """Update settings for a user in a profile."""
#     if request.method == "POST":
#         data = json.loads(request.body)
#         profile_user = ProfileUser.objects.get(id=data["profile_user_id"])
#         profile_user.forward_permission = data.get(
#             "forward_permission", profile_user.forward_permission
#         )
#         profile_user.add_to_queue_permission = data.get(
#             "add_to_queue_permission", profile_user.add_to_queue_permission
#         )
#         profile_user.save()
#         return JsonResponse({"success": True})
