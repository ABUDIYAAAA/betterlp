from django.db import models
from django.contrib.auth.models import User


class UserToken(models.Model):
    discord_user_id = models.BigIntegerField(unique=True)
    access_token = models.TextField()
    refresh_token = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Discord User ID: {self.discord_user_id}"


class Friendship(models.Model):
    user = models.ForeignKey(User, related_name="friendships", on_delete=models.CASCADE)
    friend = models.ForeignKey(
        User, related_name="related_to_friendships", on_delete=models.CASCADE
    )

    can_forward = models.BooleanField(default=False)
    can_que = models.BooleanField(default=True)

    class Meta:
        unique_together = ("user", "friend")

    def __str__(self):
        return f"{self.user.username} ↔ {self.friend.username}"


class ListenParty(models.Model):
    owner = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="owner_party"
    )
    connected = models.ManyToManyField(User, blank=True, related_name="connected_users")
    mobile_lp_users = models.ManyToManyField(
        User, blank=True, related_name="mobile_lp_users"
    )
