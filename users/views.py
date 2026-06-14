from django.shortcuts import render, redirect, get_object_or_404
from .models import FriendRequest, Message, Post, PostLike, PostComment, SavedPost
from django.contrib.auth.decorators import login_required
from .forms import RegisterForm, UserUpdateForm, ProfileUpdateForm
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.http import JsonResponse
import os
import re
from django.db.models import Q
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

def chat_room_name(user1, user2):
    users = sorted([user1.username, user2.username])
    return f"chat_{users[0]}_{users[1]}"

def broadcast_chat_event(user1, user2, event):
    channel_layer = get_channel_layer()

    async_to_sync(channel_layer.group_send)(
        chat_room_name(user1, user2),
        event
    )

def home(request):
    posts = Post.objects.select_related(
        "author"
    ).order_by("-created_at")

    for post in posts:
        post.is_saved = False

        if request.user.is_authenticated:
            post.is_saved = SavedPost.objects.filter(
                user=request.user,
                post=post
            ).exists()

        post.likes_count = PostLike.objects.filter(
            post=post
        ).count()

        post.formatted_description = re.sub(
            r'#(\w+)',
            r'<a href="/hashtag/\1/" class="hashtag">#\1</a>',
            post.description
        )

        post.formatted_description = re.sub(
            r'@(\w+)',
            r'<a href="/profile/\1/" class="mention">@\1</a>',
            post.formatted_description
        )

        post.comments_count = post.comments.count()
        post.last_comments = post.comments.select_related("author").order_by("-created_at")[:3]

        post.is_liked = False

        if request.user.is_authenticated:
            post.is_liked = PostLike.objects.filter(
                post=post,
                user=request.user
            ).exists()
    return render(request, 'home.html', {
        'posts': posts
    })

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

@login_required
def chat(request, username=None):
    request.user.profile.last_seen = timezone.now()
    request.user.profile.save(update_fields=["last_seen"])

    friends = User.objects.filter(
        Q(sent_requests__to_user=request.user,
          sent_requests__status='accepted') |
        Q(received_requests__from_user=request.user,
          received_requests__status='accepted')
    ).distinct()

    selected_user = None
    messages = []

    if username:
        selected_user = get_object_or_404(User, username=username)

        messages = Message.objects.filter(
            sender__in=[request.user, selected_user],
            receiver__in=[request.user, selected_user]
        ).order_by('created_at')

    chat_friends = []

    for friend in friends:
        last_message = Message.objects.filter(
            sender__in=[request.user, friend],
            receiver__in=[request.user, friend]
        ).order_by('-created_at').first()

        unread_count = Message.objects.filter(
            sender=friend,
            receiver=request.user,
            is_read=False
        ).count()

        friend.last_message = last_message
        friend.unread_count = unread_count

        if last_message:
            friend.last_time = last_message.created_at
        else:
            friend.last_time = None

        chat_friends.append(friend)

    chat_friends.sort(
        key=lambda friend: friend.last_time or friend.date_joined,
        reverse=True
    )

    return render(request, 'chat.html', {
        'friends': chat_friends,
        'selected_user': selected_user,
        'messages': messages
    })

def register_view(request, post_id):
    post = get_object_or_404(Post, id=post_id)

    post.views += 1
    post.save(update_fields=["views"])

    return JsonResponse({
        "success": True,
        "views": post.views
    })

@login_required
def user_profile(request, username):
    profile_user = get_object_or_404(User, username=username)

    following = FriendRequest.objects.filter(
        from_user=request.user,
        to_user=profile_user
    ).exists()

    follower_back = FriendRequest.objects.filter(
        from_user=profile_user,
        to_user=request.user
    ).exists()

    is_friend = following and follower_back

    # 🔥 новые штуки
    followers = FriendRequest.objects.filter(to_user=profile_user)
    followings = FriendRequest.objects.filter(from_user=profile_user)

    return render(request, 'user_profile.html', {
        'profile_user': profile_user,
        'following': following,
        'follower_back': follower_back,
        'is_friend': is_friend,
        'followers': followers,
        'followings': followings
    })

@login_required
def followers_list(request, username):
    user = get_object_or_404(User, username=username)

    followers = FriendRequest.objects.filter(to_user=user)

    return render(request, 'followers.html', {
        'profile_user': user,
        'followers': followers
    })

def post_detail(request, post_id):
    post = get_object_or_404(Post, id=post_id)

    comments = post.comments.select_related("author").order_by("-created_at")

    return render(request, "post_detail.html", {
        "post": post,
        "comments": comments,
    })

@login_required
def toggle_save_post(request, post_id):
    post = get_object_or_404(Post, id=post_id)

    saved = SavedPost.objects.filter(
        user=request.user,
        post=post
    )

    if saved.exists():
        saved.delete()
    else:
        SavedPost.objects.create(
            user=request.user,
            post=post
        )

    return redirect("home")

@login_required
def add_comment(request, post_id):
    post = get_object_or_404(Post, id=post_id)

    if request.method == "POST":
        text = request.POST.get("text", "").strip()

        if text:
            comment = PostComment.objects.create(
                post=post,
                author=request.user,
                text=text
            )

            return JsonResponse({
                "success": True,
                "username": comment.author.username,
                "text": comment.text,
                "comments_count": post.comments.count()
            })

    return JsonResponse({
        "success": False
    })


@login_required
def following_list(request, username):
    user = get_object_or_404(User, username=username)

    following = FriendRequest.objects.filter(from_user=user)

    return render(request, 'following.html', {
        'profile_user': user,
        'following': following
    })

def custom_404(request, exception):
    return render(request, '404.html', status=404)

@login_required
def send_friend_request(request, username):
    to_user = get_object_or_404(User, username=username)

    if to_user != request.user:

        existing = FriendRequest.objects.filter(
            from_user=to_user,
            to_user=request.user
        ).first()

        fr, created = FriendRequest.objects.get_or_create(
            from_user=request.user,
            to_user=to_user,
            defaults={'status': 'accepted'}
        )

        if not created:
            fr.status = 'accepted'
            fr.save()

        if existing:
            existing.status = 'accepted'
            existing.is_read = False 
            existing.save()

            fr.status = 'accepted'
            fr.is_read = False 
            fr.save()

    return redirect('user_profile', username=username)

@login_required
def unfollow(request, username):
    other_user = get_object_or_404(User, username=username)

    FriendRequest.objects.filter(
        from_user=request.user,
        to_user=other_user
    ).delete()

    return redirect('user_profile', username=username)

@login_required
def toggle_like(request, post_id):
    post = get_object_or_404(Post, id=post_id)

    like = PostLike.objects.filter(
        user=request.user,
        post=post
    )

    if like.exists():
        like.delete()
    else:
        PostLike.objects.create(
            user=request.user,
            post=post
        )

    return redirect("home")

@login_required
def mark_read(request, request_id):
    req = FriendRequest.objects.get(id=request_id, to_user=request.user)
    req.is_read = True
    req.save()

    return redirect(request.META.get('HTTP_REFERER', '/'))

@login_required
def create_post(request):
    if request.method == "POST":
        video = request.FILES.get("video")
        description = request.POST.get("description", "")

        if video:
            Post.objects.create(
                author=request.user,
                video=video,
                description=description
            )

            return redirect("home")

    return render(request, "create_post.html")

@login_required
def mark_all_read(request):
    FriendRequest.objects.filter(
        to_user=request.user
    ).update(is_read=True)

    return redirect(request.META.get('HTTP_REFERER', '/'))

@login_required
def friend_requests(request):
    requests = FriendRequest.objects.filter(
        to_user=request.user,
        status='pending'
    )

    return render(request, 'friend_requests.html', {
        'requests': requests
    })

@login_required
def accept_friend_request(request, request_id):
    friend_request = get_object_or_404(FriendRequest, id=request_id)

    if friend_request.to_user == request.user:
        friend_request.status = 'accepted'
        friend_request.save()

    return redirect('friend_requests')

@login_required
def reject_friend_request(request, request_id):
    friend_request = get_object_or_404(FriendRequest, id=request_id)

    if friend_request.to_user == request.user:
        friend_request.status = 'rejected'
        friend_request.save()

    return redirect('friend_requests')

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

@login_required
def delete_message(request, message_id):
    message = get_object_or_404(Message, id=message_id, sender=request.user)

    chat_username = message.receiver.username

    broadcast_chat_event(
        message.sender,
        message.receiver,
        {
            "type": "message_deleted",
            "message_id": message.id,
        }
    )

    message.delete()

    return redirect("chat_with_user", username=chat_username)

@login_required
def edit_message(request, message_id):
    message = get_object_or_404(Message, id=message_id, sender=request.user)

    if request.method == "POST":
        new_text = request.POST.get("text", "").strip()

        if new_text:
            broadcast_chat_event(
                message.sender,
                message.receiver,
                {
                    "type": "message_edited",
                    "message_id": message.id,
                    "text": new_text,
                    "edited": True,
                }
            )
            message.text = new_text
            message.edited_at = timezone.now()
            message.save(update_fields=["text", "edited_at"])

        return redirect("chat_with_user", username=message.receiver.username)

    return redirect("chat_with_user", username=message.receiver.username)

@login_required
def pin_message(request, message_id):
    message = get_object_or_404(Message, id=message_id)

    if message.sender != request.user and message.receiver != request.user:
        return redirect("chat")

    other_user = (
        message.receiver
        if message.sender == request.user
        else message.sender
    )

    Message.objects.filter(
        sender__in=[request.user, other_user],
        receiver__in=[request.user, other_user],
        is_pinned=True
    ).update(is_pinned=False)

    broadcast_chat_event(
        request.user,
        other_user,
        {
            "type": "message_pinned",
            "message_id": message.id,
            "text": message.text,
            "user": message.sender.username,
        }
    )

    message.is_pinned = True
    message.save(update_fields=["is_pinned"])

    return redirect("chat_with_user", username=other_user.username)

@login_required
def unpin_message(request, message_id):
    message = get_object_or_404(Message, id=message_id)

    if message.sender != request.user and message.receiver != request.user:
        return redirect("chat")

    other_user = message.receiver if message.sender == request.user else message.sender

    broadcast_chat_event(
        request.user,
        other_user,
        {
            "type": "message_unpinned",
            "message_id": message.id,
        }
    )

    message.is_pinned = False
    message.save(update_fields=["is_pinned"])

    return redirect("chat_with_user", username=other_user.username)


@login_required
def send_chat_photo(request, username):
    other_user = get_object_or_404(User, username=username)

    if request.method == "POST":
        image = request.FILES.get("image")

        if image:
            Message.objects.create(
                sender=request.user,
                receiver=other_user,
                image=image
            )

    return redirect("chat_with_user", username=username)