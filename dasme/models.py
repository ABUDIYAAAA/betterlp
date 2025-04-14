from django.db import models


class UserToken(models.Model):
    discord_user_id = models.BigIntegerField(unique=True)
    access_token = models.TextField()
    refresh_token = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Discord User ID: {self.discord_user_id}"


class Profile(models.Model):
    owner = models.OneToOneField("auth.User", on_delete=models.CASCADE)
    name = models.CharField(max_length=100)

    def __str__(self):
        return self.name


class ProfileUser(models.Model):
    profile = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name="users")
    discord_user_id = models.BigIntegerField()
    forward_permission = models.BooleanField(default=False)
    add_to_queue_permission = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.discord_user_id} in {self.profile.name}"
