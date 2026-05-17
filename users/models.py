from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save, pre_save, post_delete
from django.dispatch import receiver
from django.conf import settings
from django.utils import timezone
import os


def user_avatar_path(instance, filename):
    ext = filename.split('.')[-1]
    username = instance.user.username

    file_path = f'avatars/{username}_avatar.{ext}'

    full_path = os.path.join(settings.MEDIA_ROOT, file_path)
    if os.path.exists(full_path):
        os.remove(full_path)

    return file_path


class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)

    last_seen = models.DateTimeField(default=timezone.now)

    avatar = models.ImageField(
        upload_to=user_avatar_path,
        blank=True,
        null=True
    )

    bio = models.TextField(blank=True)

    @property
    def is_online(self):
        return timezone.now() - self.last_seen < timezone.timedelta(minutes=3)

    def __str__(self):
        return self.user.username
    
class FriendRequest(models.Model):
    from_user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sent_requests')
    to_user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='received_requests')
    status = models.CharField(max_length=10, choices=[
        ('pending', 'Pending'),
        ('accepted', 'Accepted'),
        ('rejected', 'Rejected'),
    ], default='pending')

    created_at = models.DateTimeField(auto_now_add=True)

    is_read = models.BooleanField(default=False)  # 👈 ВОТ СЮДА ДОБАВЬ

    def __str__(self):
        return f"{self.from_user} -> {self.to_user} ({self.status})"

class Message(models.Model):
    sender = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sent_messages')
    receiver = models.ForeignKey(User, on_delete=models.CASCADE, related_name='received_messages')

    text = models.TextField(blank=True)

    image = models.ImageField(
        upload_to="chat_images/",
        blank=True,
        null=True
    )

    reply_to = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="replies"
    )

    is_pinned = models.BooleanField(default=False)
    is_read = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.sender} -> {self.receiver}"
    
@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        Profile.objects.create(user=instance)


@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    instance.profile.save()


@receiver(pre_save, sender=Profile)
def delete_old_avatar(sender, instance, **kwargs):
    if not instance.pk:
        return

    try:
        old_avatar = Profile.objects.get(pk=instance.pk).avatar
    except Profile.DoesNotExist:
        return

    new_avatar = instance.avatar

    if old_avatar and old_avatar != new_avatar:
        if old_avatar.name:
            old_path = old_avatar.path
            if os.path.isfile(old_path):
                os.remove(old_path)


@receiver(post_delete, sender=Profile)
def delete_avatar_on_delete(sender, instance, **kwargs):
    if instance.avatar:
        if instance.avatar.name:
            file_path = instance.avatar.path
            if os.path.isfile(file_path):
                os.remove(file_path)