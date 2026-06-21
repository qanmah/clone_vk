from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm
from .models import Profile
from django.forms.widgets import ClearableFileInput

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

