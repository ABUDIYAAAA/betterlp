import requests
from django.http import HttpResponse, HttpResponseRedirect, JsonResponse
from django.conf import settings
from urllib.parse import urlencode
from django.views.decorators.csrf import csrf_exempt
from .models import UserToken
import json
from django.shortcuts import redirect

# Replace or add these in your settings.py
CLIENT_ID = "a1358e7bde1741bd9a7d0242d77dd9fb"
CLIENT_SECRET = "772fe3710f7d4491b8202bf52e1a0b2b"
REDIRECT_URI = r"http://127.0.0.1:8000/callback"
SCOPE = "user-read-playback-state user-modify-playback-state"


def login(request):
    params = urlencode(
        {
            "response_type": "code",
            "client_id": CLIENT_ID,
            "scope": SCOPE,
            "redirect_uri": REDIRECT_URI,
        }
    )
    return HttpResponseRedirect(f"https://accounts.spotify.com/authorize?{params}")


def callback(request):
    code = request.GET.get("code")

    token_res = requests.post(
        "https://accounts.spotify.com/api/token",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": REDIRECT_URI,
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
        },
    )

    token_data = token_res.json()

    if "access_token" in token_data:
        access_token = token_data["access_token"]
        refresh_token = token_data.get("refresh_token", "❌ Not returned")
        return HttpResponse(
            f"<h2>✅ Auth successful!</h2>"
            f"<p><strong>Access Token:</strong> {access_token}</p>"
            f"<p><strong>Refresh Token:</strong> {refresh_token}</p>"
            f"<p>Copy these tokens and close the window.</p>"
        )
    else:
        return HttpResponse(f"❌ Error: {token_data}")


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
                "client_secret": "772fe3710f7d4491b8202bf52e1a0b2b",  # Spotify Client Secret
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
            return redirect("https://discord.com/app")  # Redirect back to Discord
        else:
            return JsonResponse(
                {"error": "Failed to exchange code for tokens"}, status=400
            )

    if request.method == "POST":
        code = request.POST.get("code")
        state = request.POST.get("state")  # Discord user ID passed as state

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
            return HttpResponseRedirect(
                "https://discord.com/app"
            )  # Redirect back to Discord
        else:
            return JsonResponse(
                {"error": "Failed to exchange code for tokens"}, status=400
            )

    return JsonResponse({"error": "Method not allowed"}, status=405)


def verify_tokens(request, discord_user_id):
    try:
        user_token = UserToken.objects.get(discord_user_id=discord_user_id)
        return JsonResponse({"linked": True})
    except UserToken.DoesNotExist:
        return JsonResponse({"linked": False})


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
                return JsonResponse({"is_playing": False})
        else:
            return JsonResponse(
                {"error": "Failed to fetch currently playing track"},
                status=response.status_code,
            )
    except UserToken.DoesNotExist:
        return JsonResponse({"error": "User token not found"}, status=404)
