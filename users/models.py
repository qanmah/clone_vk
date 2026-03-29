from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save, pre_save, post_delete
from django.dispatch import receiver
from django.conf import settings
import os


# 📁 Путь и имя файла
def user_avatar_path(instance, filename):
    ext = filename.split('.')[-1]  # расширение (png, jpg)
    username = instance.user.username

    file_path = f'avatars/{username}_avatar.{ext}'

    # 🧹 Удаляем старый файл, если он уже существует
    full_path = os.path.join(settings.MEDIA_ROOT, file_path)
    if os.path.exists(full_path):
        os.remove(full_path)

    return file_path


class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    avatar = models.ImageField(
        upload_to=user_avatar_path,
        blank=True,
        null=True
    )
    bio = models.TextField(blank=True)  

    def __str__(self):
        return self.user.username


# 🆕 Создание профиля при регистрации
@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        Profile.objects.create(user=instance)


# 💾 Сохранение профиля
@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    instance.profile.save()


# 🔄 Удаление старого файла при обновлении
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


# 🗑️ Удаление файла при удалении профиля
@receiver(post_delete, sender=Profile)
def delete_avatar_on_delete(sender, instance, **kwargs):
    if instance.avatar:
        if instance.avatar.name:
            file_path = instance.avatar.path
            if os.path.isfile(file_path):
                os.remove(file_path)