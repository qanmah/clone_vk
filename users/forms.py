from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm
from .models import Profile
from django.forms.widgets import ClearableFileInput
from django.core.exceptions import ValidationError
from pathlib import Path

from .models import AUDIO_EXTENSIONS, IMAGE_EXTENSIONS, Post, VIDEO_EXTENSIONS

MAX_VIDEO_SIZE = 100 * 1024 * 1024
MAX_IMAGE_SIZE = 15 * 1024 * 1024
MAX_IMAGES = 10
MAX_AUDIO_SIZE = 30 * 1024 * 1024

class AvatarFileInput(ClearableFileInput):
    template_name = "widgets/avatar_file_input.html"

class RegisterForm(UserCreationForm):
    email = forms.EmailField()

    class Meta:
        model = User
        fields = ['username', 'email', 'password1', 'password2']

class UserUpdateForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ['username']

class CustomClearableFileInput(ClearableFileInput):
    initial_text = "Текущий файл"
    input_text = "Изменить"
    clear_checkbox_label = "Удалить аватар"


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleFileField(forms.FileField):
    def clean(self, data, initial=None):
        files = data if isinstance(data, (list, tuple)) else [data] if data else []
        clean_single = super().clean
        return [clean_single(file, initial) for file in files]

class ProfileUpdateForm(forms.ModelForm):
    class Meta:
        model = Profile
        fields = ["avatar", "bio"]

        widgets = {
            "avatar": AvatarFileInput(),
            "bio": forms.Textarea(attrs={
                "placeholder": "Расскажи немного о себе..."
            }),
        }


class PostForm(forms.ModelForm):
    photos = MultipleFileField(
        required=False,
        widget=MultipleFileInput(attrs={"accept": "image/*"}),
    )

    class Meta:
        model = Post
        fields = ["video", "audio", "description", "visibility"]
        widgets = {
            "video": forms.FileInput(attrs={"accept": "video/*"}),
            "audio": forms.FileInput(attrs={"accept": "audio/*"}),
            "description": forms.Textarea(attrs={
                "maxlength": 2000,
                "placeholder": "Текст, #хэштеги, @друзья",
                "rows": 5,
            }),
        }

    def clean_video(self):
        video = self.cleaned_data.get("video")
        if not video:
            return video
        extension = Path(video.name).suffix.lower()

        if extension not in VIDEO_EXTENSIONS:
            raise ValidationError("Поддерживаются MP4, WebM, MOV, M4V и OGG.")

        content_type = getattr(video, "content_type", "")
        if content_type and not content_type.startswith("video/"):
            raise ValidationError("Выбранный файл не является видео.")

        if video.size > MAX_VIDEO_SIZE:
            raise ValidationError("Размер видео не должен превышать 100 МБ.")

        return video

    def clean_audio(self):
        audio = self.cleaned_data.get("audio")
        if not audio:
            return audio
        extension = Path(audio.name).suffix.lower()
        content_type = getattr(audio, "content_type", "")
        if extension not in AUDIO_EXTENSIONS or (content_type and not content_type.startswith("audio/")):
            raise ValidationError("Поддерживаются MP3, WAV, OGG, M4A, AAC и FLAC.")
        if audio.size > MAX_AUDIO_SIZE:
            raise ValidationError("Размер аудио не должен превышать 30 МБ.")
        return audio

    def clean_photos(self):
        photos = self.cleaned_data.get("photos", [])
        if len(photos) > MAX_IMAGES:
            raise ValidationError(f"Можно загрузить не больше {MAX_IMAGES} фотографий.")
        for photo in photos:
            extension = Path(photo.name).suffix.lower()
            content_type = getattr(photo, "content_type", "")
            if extension not in IMAGE_EXTENSIONS or (content_type and not content_type.startswith("image/")):
                raise ValidationError("Поддерживаются JPG, PNG, WebP и GIF.")
            if photo.size > MAX_IMAGE_SIZE:
                raise ValidationError("Размер одной фотографии не должен превышать 15 МБ.")
        return photos

    def clean(self):
        cleaned_data = super().clean()
        video = cleaned_data.get("video")
        audio = cleaned_data.get("audio")
        photos = cleaned_data.get("photos", [])
        if not video and not photos:
            raise ValidationError("Выберите видео или хотя бы одну фотографию.")
        if video and photos:
            raise ValidationError("В одной публикации можно загрузить либо видео, либо фотографии.")
        if audio and not photos:
            raise ValidationError("Свой звук можно добавить только к фотографиям.")
        return cleaned_data

    def clean_description(self):
        description = self.cleaned_data["description"].strip()
        if len(description) > 2000:
            raise ValidationError("Описание не должно превышать 2000 символов.")
        return description


class PostManageForm(forms.ModelForm):
    class Meta:
        model = Post
        fields = ["description", "visibility"]

    def clean_description(self):
        description = self.cleaned_data["description"].strip()
        if len(description) > 2000:
            raise ValidationError("Описание не должно превышать 2000 символов.")
        return description

