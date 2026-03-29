from django.shortcuts import render, redirect, get_object_or_404
from .forms import RegisterForm, UserUpdateForm, ProfileUpdateForm
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
import os


def home(request):
    return render(request, 'home.html')

def register(request):
    if request.method == 'POST':
        form = RegisterForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('login')
    else:
        form = RegisterForm()

    return render(request, 'register.html', {'form': form})

@login_required
def profile(request):
    return render(request, 'profile.html', {'user': request.user})

def user_profile(request, username):
    user = get_object_or_404(User, username=username)
    return render(request, 'user_profile.html', {'profile_user': user})

def custom_404(request, exception):
    return render(request, '404.html', status=404)

@login_required
def edit_profile(request):

    if request.method == 'POST':
        u_form = UserUpdateForm(request.POST, instance=request.user)
        p_form = ProfileUpdateForm(
            request.POST,
            request.FILES,
            instance=request.user.profile
        )

        if u_form.is_valid() and p_form.is_valid():

            profile = request.user.profile

            # 🧹 Удаление старого файла при Clear
            if 'avatar-clear' in request.POST:
                if profile.avatar:
                    if os.path.isfile(profile.avatar.path):
                        os.remove(profile.avatar.path)
                    profile.avatar = None

            u_form.save()
            p_form.save()

            return redirect('user_profile', username=request.user.username)

    else:
        u_form = UserUpdateForm(instance=request.user)
        p_form = ProfileUpdateForm(instance=request.user.profile)

    return render(request, 'edit_profile.html', {
        'u_form': u_form,
        'p_form': p_form
    })