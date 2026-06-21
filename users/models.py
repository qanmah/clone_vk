from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save, pre_save, post_delete
from django.dispatch import receiver
from django.conf import settings
from django.utils import timezone
import os

VIDEO_EXTENSIONS = {".mp4", ".webm", ".mov", ".m4v", ".ogg"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
AUDIO_EXTENSIONS = {".mp3", ".wav", ".ogg", ".m4a", ".aac", ".flac"}


def post_video_path(instance, filename):
    extension = os.path.splitext(filename)[1].lower()
    return f"post_videos/{instance.author_id}/{timezone.now():%Y/%m}/{timezone.now().timestamp():.0f}{extension}"


def post_image_path(instance, filename):
    extension = os.path.splitext(filename)[1].lower()
    return f"post_images/{instance.post.author_id}/{timezone.now():%Y/%m}/{timezone.now().timestamp():.0f}_{instance.order}{extension}"


def post_audio_path(instance, filename):
    extension = os.path.splitext(filename)[1].lower()
    return f"post_audio/{instance.author_id}/{timezone.now():%Y/%m}/{timezone.now().timestamp():.0f}{extension}"


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

class Post(models.Model):
    VISIBILITY_CHOICES = (
        ("public", "Всем"),
        ("followers", "Подписчикам"),
        ("private", "Только мне"),
    )

    author = models.ForeignKey(User, on_delete=models.CASCADE, related_name="posts")
    video = models.FileField(upload_to=post_video_path, blank=True, null=True)
    audio = models.FileField(upload_to=post_audio_path, blank=True, null=True)
    views = models.PositiveIntegerField(default=0)
    description = models.TextField(blank=True)
    visibility = models.CharField(max_length=12, choices=VISIBILITY_CHOICES, default="public")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self):
        return f"Post by {self.author.username}"

    @property
    def is_video(self):
        return bool(self.video)


class PostImage(models.Model):
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name="images")
    image = models.ImageField(upload_to=post_image_path)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ("order", "id")

class PostLike(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="post_likes")
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name="likes")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("user", "post")

class PostComment(models.Model):
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name="comments")
    author = models.ForeignKey(User, on_delete=models.CASCADE)
    parent = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        related_name="replies",
        null=True,
        blank=True,
    )
    text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Comment by {self.author.username}"
    
class SavedPost(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="saved_posts")
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name="saves")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("user", "post")

    def __str__(self):
        return f"{self.user.username} saved post {self.post.id}"

class Message(models.Model):
    sender = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sent_messages')
    receiver = models.ForeignKey(User, on_delete=models.CASCADE, related_name='received_messages')

    text = models.TextField(blank=True)
    shared_post = models.ForeignKey(
        Post,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="shared_messages"
    )

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
    edited_at = models.DateTimeField(null=True, blank=True)

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


@receiver(post_delete, sender=Post)
def delete_video_on_post_delete(sender, instance, **kwargs):
    if instance.video and instance.video.name:
        instance.video.delete(save=False)
    if instance.audio and instance.audio.name:
        instance.audio.delete(save=False)


@receiver(post_delete, sender=PostImage)
def delete_image_on_post_image_delete(sender, instance, **kwargs):
    if instance.image and instance.image.name:
        instance.image.delete(save=False)
