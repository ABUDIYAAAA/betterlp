from django.db import models


class UserToken(models.Model):
    discord_user_id = models.BigIntegerField(unique=True)
    access_token = models.TextField()
    refresh_token = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Discord User ID: {self.discord_user_id}"
