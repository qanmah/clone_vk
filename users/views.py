from django.shortcuts import render, redirect, get_object_or_404
from .models import FriendRequest, Message, Post, PostImage, PostLike, PostComment, SavedPost
from django.contrib.auth.decorators import login_required
from .forms import RegisterForm, UserUpdateForm, ProfileUpdateForm, PostForm, PostManageForm
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
from django.utils import timezone


def build_comment_threads(post, root_limit=None):
    comments = list(post.comments.select_related(
        "author",
        "author__profile",
        "parent",
        "parent__author",
    ).order_by("created_at"))
    comments_by_id = {comment.id: comment for comment in comments}
    roots = []

    for comment in comments:
        comment.thread_replies = []
        if comment.parent_id is None:
            roots.append(comment)

    for comment in comments:
        if comment.parent_id is None:
            continue
        root = comment
        visited = set()
        while root.parent_id and root.parent_id in comments_by_id and root.parent_id not in visited:
            visited.add(root.parent_id)
            root = comments_by_id[root.parent_id]
        if root.parent_id is None:
            root.thread_replies.append(comment)

    roots.sort(key=lambda comment: comment.created_at, reverse=True)
    if root_limit is not None:
        roots = roots[:root_limit]
    return roots
from django.http import JsonResponse
import os
import re
from collections import Counter
from difflib import SequenceMatcher
from django.db.models import BooleanField, Count, Exists, F, OuterRef, Q, Value
from django.views.decorators.http import require_POST
from django.utils.html import escape
from django.urls import reverse
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

def can_view_post(user, post):
    if post.visibility == "public" or post.author == user:
        return True
    if post.visibility == "followers" and user.is_authenticated:
        return FriendRequest.objects.filter(
            from_user=user,
            to_user=post.author,
            status="accepted",
        ).exists()
    return False


def visible_post_or_404(request, post_id):
    post = get_object_or_404(Post, id=post_id)
    if not can_view_post(request.user, post):
        return None
    return post


def accepted_friends(user):
    return User.objects.filter(
        Q(sent_requests__to_user=user, sent_requests__status="accepted") |
        Q(received_requests__from_user=user, received_requests__status="accepted")
    ).distinct()


def russian_relative_time(created_at):
    seconds = max(0, int((timezone.now() - created_at).total_seconds()))

    if seconds < 60:
        return "только что"

    def plural(value, forms):
        if 11 <= value % 100 <= 14:
            return forms[2]
        if value % 10 == 1:
            return forms[0]
        if 2 <= value % 10 <= 4:
            return forms[1]
        return forms[2]

    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes} {plural(minutes, ('минуту', 'минуты', 'минут'))} назад"

    hours = seconds // 3600
    if hours < 24:
        return f"{hours} {plural(hours, ('час', 'часа', 'часов'))} назад"

    days = seconds // 86400
    if days < 7:
        return f"{days} {plural(days, ('день', 'дня', 'дней'))} назад"

    return created_at.strftime("%d.%m.%Y")


def fuzzy_score(query, text):
    query = query.casefold().strip()
    text = text.casefold().strip()
    if not query or not text:
        return 0
    if query in text:
        return 1

    words = re.findall(r"\w+", text)
    phrase_score = SequenceMatcher(None, query, text[:max(len(query) * 3, 80)]).ratio()
    word_score = max((SequenceMatcher(None, query, word).ratio() for word in words), default=0)
    window_score = max(
        (
            SequenceMatcher(None, query, " ".join(words[index:index + 4])).ratio()
            for index in range(len(words))
        ),
        default=0,
    )
    return max(phrase_score, word_score, window_score)


def format_post_description(description):
    formatted = re.sub(
        r'#([\w-]+)',
        r'<a href="/?q=%23\1" class="hashtag">#\1</a>',
        escape(description),
    )
    return re.sub(
        r'@(\w+)',
        r'<a href="/profile/\1/" class="mention">@\1</a>',
        formatted,
    )


def home(request):
    posts = Post.objects.select_related("author", "author__profile").prefetch_related("images").annotate(
        likes_count=Count("likes", distinct=True),
        comments_count=Count("comments", distinct=True),
        saves_count=Count("saves", distinct=True),
    )

    feed = request.GET.get("feed", "all")
    query = request.GET.get("q", "").strip()
    if feed not in {"all", "following", "saved"}:
        feed = "all"

    if request.user.is_authenticated:
        follower_ids = FriendRequest.objects.filter(
            from_user=request.user,
            status="accepted",
        ).values("to_user_id")
        posts = posts.filter(
            Q(visibility="public") |
            Q(author=request.user) |
            Q(visibility="followers", author_id__in=follower_ids)
        )
        posts = posts.annotate(
            is_liked=Exists(PostLike.objects.filter(user=request.user, post=OuterRef("pk"))),
            is_saved=Exists(SavedPost.objects.filter(user=request.user, post=OuterRef("pk"))),
        )

        if feed == "following":
            posts = posts.filter(author_id__in=follower_ids)
        elif feed == "saved":
            posts = posts.filter(saves__user=request.user)
    else:
        posts = posts.filter(visibility="public")
        posts = posts.annotate(
            is_liked=Value(False, output_field=BooleanField()),
            is_saved=Value(False, output_field=BooleanField()),
        )

    if query:
        posts = posts.filter(Q(description__icontains=query) | Q(author__username__icontains=query))

    posts = posts.distinct().order_by("-created_at")[:30]

    for post in posts:
        post.relative_created_at = russian_relative_time(post.created_at)
        post.formatted_description = format_post_description(post.description)
        post.images_list = list(post.images.all())
        post.images_count = len(post.images_list)
        post.comment_threads = build_comment_threads(post, root_limit=20)

    return render(request, 'home.html', {
        'posts': posts,
        'active_feed': feed,
        'feed_query': query,
    })


def search_suggestions(request):
    query = request.GET.get("q", "").strip()
    if len(query) < (2 if query.startswith("#") else 3):
        return JsonResponse({"results": []})

    user_candidates = User.objects.select_related("profile").order_by("username")[:100]

    posts = Post.objects.select_related("author", "author__profile").prefetch_related("images")
    if request.user.is_authenticated:
        following_ids = FriendRequest.objects.filter(
            from_user=request.user,
            status="accepted",
        ).values("to_user_id")
        posts = posts.filter(
            Q(visibility="public") |
            Q(author=request.user) |
            Q(visibility="followers", author_id__in=following_ids)
        )
    else:
        posts = posts.filter(visibility="public")

    users = sorted(
        (
            (fuzzy_score(query, found_user.username), found_user)
            for found_user in user_candidates
        ),
        key=lambda item: item[0],
        reverse=True,
    )
    ranked_posts = sorted(
        (
            (
                max(fuzzy_score(query, post.description), fuzzy_score(query, post.author.username)),
                post,
            )
            for post in posts.order_by("-created_at").distinct()[:150]
        ),
        key=lambda item: item[0],
        reverse=True,
    )

    results = []
    if query.startswith("#"):
        hashtag_query = query[1:].casefold()
        hashtag_counts = Counter(
            hashtag.casefold()
            for description in posts.exclude(description="").values_list("description", flat=True)[:500]
            for hashtag in re.findall(r"(?<!\w)#([\w-]+)", description)
        )
        ranked_hashtags = sorted(
            ((fuzzy_score(hashtag_query, hashtag), hashtag, count) for hashtag, count in hashtag_counts.items()),
            key=lambda item: (-item[0], -item[2], item[1]),
        )
        for score, hashtag, count in ranked_hashtags[:5]:
            if score < 0.42:
                continue
            results.append({
                "type": "hashtag",
                "badge": "Хештег",
                "title": f"#{hashtag}",
                "subtitle": f"Публикаций: {count}",
                "url": f"/?q=%23{hashtag}",
                "avatar": "",
                "video": "",
                "image": "",
                "match": "Похожий хештег" if score < 1 else "",
            })

    for score, found_user in users[:5]:
        if score < 0.48:
            continue
        results.append({
            "type": "user",
            "badge": "Аккаунт",
            "title": f"@{found_user.username}",
            "subtitle": "Аккаунт пользователя",
            "url": reverse("user_profile", args=[found_user.username]),
            "avatar": found_user.profile.avatar.url if found_user.profile.avatar else "/media/avatars/default.jpg",
            "video": "",
            "match": "Похожий аккаунт" if score < 1 else "",
        })

    for score, post in ranked_posts[:5]:
        if score < 0.48:
            continue
        description = post.description.strip()
        first_image = post.images.first()
        results.append({
            "type": "post",
            "badge": "Видео" if post.video else "Фотографии",
            "title": description[:80] or f"Публикация от @{post.author.username}",
            "subtitle": f"@{post.author.username} · {russian_relative_time(post.created_at)}",
            "url": reverse("post_detail", args=[post.id]),
            "avatar": post.author.profile.avatar.url if post.author.profile.avatar else "/media/avatars/default.jpg",
            "video": post.video.url if post.video else "",
            "image": first_image.image.url if first_image else "",
            "match": "Похожая фраза" if score < 1 else "",
        })

    return JsonResponse({"results": results[:8]})


@login_required
def description_suggestions(request):
    kind = request.GET.get("kind", "")
    query = request.GET.get("q", "").strip().lstrip("@#").casefold()

    if kind == "mention":
        candidates = User.objects.select_related("profile").order_by("username")[:250]
        ranked = sorted(
            ((fuzzy_score(query, user.username) if query else 1, user) for user in candidates),
            key=lambda item: (-item[0], item[1].username.casefold()),
        )
        results = [{
            "value": f"@{user.username}",
            "title": f"@{user.username}",
            "subtitle": "Пользователь",
            "avatar": user.profile.avatar.url if user.profile.avatar else "/media/avatars/default.jpg",
        } for score, user in ranked[:8] if not query or score >= 0.42]
        return JsonResponse({"results": results})

    if kind == "hashtag":
        posts = Post.objects.filter(
            Q(visibility="public") |
            Q(author=request.user) |
            Q(visibility="followers", author__received_requests__from_user=request.user, author__received_requests__status="accepted")
        ).distinct()
        descriptions = posts.exclude(description="").order_by("-created_at").values_list("description", flat=True)[:500]
        counts = Counter(
            hashtag.casefold()
            for description in descriptions
            for hashtag in re.findall(r"(?<!\w)#([\w-]+)", description)
        )
        ranked = sorted(
            (
                (fuzzy_score(query, hashtag) if query else count, hashtag, count)
                for hashtag, count in counts.items()
            ),
            key=lambda item: (-item[0], -item[2], item[1]),
        )
        results = [{
            "value": f"#{hashtag}",
            "title": f"#{hashtag}",
            "subtitle": f"Публикаций: {count}",
            "avatar": "",
        } for score, hashtag, count in ranked[:8] if not query or score >= 0.42]
        return JsonResponse({"results": results})

    return JsonResponse({"results": []})


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

    friends = accepted_friends(request.user)

    selected_user = None
    messages = []

    if username:
        selected_user = get_object_or_404(User, username=username)

        messages = Message.objects.select_related(
            "shared_post",
            "shared_post__author",
            "shared_post__author__profile",
        ).prefetch_related("shared_post__likes", "shared_post__images").filter(
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

@require_POST
def register_view(request, post_id):
    post = visible_post_or_404(request, post_id)
    if post is None:
        return JsonResponse({"success": False}, status=404)
    viewed_posts = set(request.session.get("viewed_posts", []))
    if post_id not in viewed_posts:
        Post.objects.filter(id=post_id).update(views=F("views") + 1)
        viewed_posts.add(post_id)
        request.session["viewed_posts"] = list(viewed_posts)[-500:]

    post.refresh_from_db(fields=["views"])
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
    posts = Post.objects.filter(author=profile_user).prefetch_related("images").annotate(
        likes_count=Count("likes", distinct=True),
        comments_count=Count("comments", distinct=True),
    )
    if request.user != profile_user:
        posts = posts.filter(
            Q(visibility="public") |
            Q(visibility="followers", author__received_requests__from_user=request.user, author__received_requests__status="accepted")
        )
    posts = posts.distinct().order_by("-created_at")
    for post in posts:
        post.first_image = post.images.first()
        post.relative_created_at = russian_relative_time(post.created_at)

    return render(request, 'user_profile.html', {
        'profile_user': profile_user,
        'following': following,
        'follower_back': follower_back,
        'is_friend': is_friend,
        'followers': followers,
        'followings': followings,
        'profile_posts': posts,
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
    post = get_object_or_404(Post.objects.select_related("author", "author__profile").prefetch_related("images"), id=post_id)
    if not can_view_post(request.user, post):
        return redirect("home")

    comments = build_comment_threads(post)
    post.relative_created_at = russian_relative_time(post.created_at)
    post.formatted_description = format_post_description(post.description)
    post.likes_count = post.likes.count()
    post.comments_count = post.comments.count()
    post.is_liked = request.user.is_authenticated and PostLike.objects.filter(user=request.user, post=post).exists()
    post.is_saved = request.user.is_authenticated and SavedPost.objects.filter(user=request.user, post=post).exists()

    return render(request, "post_detail.html", {
        "post": post,
        "comments": comments,
    })

@login_required
@require_POST
def toggle_save_post(request, post_id):
    post = visible_post_or_404(request, post_id)
    if post is None:
        return JsonResponse({"success": False}, status=404)

    saved = SavedPost.objects.filter(
        user=request.user,
        post=post
    )

    is_saved = not saved.exists()
    if not is_saved:
        saved.delete()
    else:
        SavedPost.objects.create(
            user=request.user,
            post=post
        )

    saves_count = post.saves.count()
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return JsonResponse({"success": True, "is_saved": is_saved, "saves_count": saves_count})
    return redirect(request.META.get("HTTP_REFERER", "home"))


@login_required
def share_post_friends(request, post_id):
    post = visible_post_or_404(request, post_id)
    if post is None:
        return JsonResponse({"success": False}, status=404)

    friends = accepted_friends(request.user).select_related("profile").order_by("username")
    results = []
    for friend in friends:
        if can_view_post(friend, post):
            results.append({
                "id": friend.id,
                "username": friend.username,
                "avatar": friend.profile.avatar.url if friend.profile.avatar else "/media/avatars/default.jpg",
            })

    return JsonResponse({"friends": results})


@login_required
@require_POST
def share_post(request, post_id):
    post = visible_post_or_404(request, post_id)
    if post is None:
        return JsonResponse({"success": False}, status=404)

    recipient_ids = request.POST.getlist("recipients")[:20]
    friends = accepted_friends(request.user).filter(id__in=recipient_ids)
    sent = 0

    for friend in friends:
        if not can_view_post(friend, post):
            continue

        first_image = post.images.first()
        media_url = post.video.url if post.video else first_image.image.url if first_image else ""
        if not media_url:
            continue

        message = Message.objects.create(sender=request.user, receiver=friend, shared_post=post)
        broadcast_chat_event(request.user, friend, {
            "type": "shared_post_message",
            "message_id": message.id,
            "user": request.user.username,
            "sender_id": request.user.id,
            "created_at": message.created_at.strftime("%H:%M"),
            "created_date": message.created_at.strftime("%Y-%m-%d"),
            "is_read": False,
            "post_id": post.id,
            "post_url": reverse("post_detail", args=[post.id]),
            "media_type": "video" if post.video else "image",
            "media_url": media_url,
            "post_author": post.author.username,
            "views": post.views,
            "likes": post.likes.count(),
        })
        sent += 1

    if not sent:
        return JsonResponse({"success": False, "error": "Выберите хотя бы одного друга."}, status=400)
    return JsonResponse({"success": True, "sent": sent})


@login_required
@require_POST
def add_comment(request, post_id):
    post = visible_post_or_404(request, post_id)
    if post is None:
        return JsonResponse({"success": False}, status=404)

    if request.method == "POST":
        text = request.POST.get("text", "").strip()
        parent = None
        parent_id = request.POST.get("parent_id", "").strip()
        if parent_id:
            parent = PostComment.objects.filter(id=parent_id, post=post).select_related("author").first()
            if parent is None:
                return JsonResponse({"success": False, "error": "Комментарий для ответа не найден."}, status=400)

        if text and len(text) <= 1000:
            comment = PostComment.objects.create(
                post=post,
                author=request.user,
                parent=parent,
                text=text
            )

            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return JsonResponse({
                    "success": True,
                    "comment_id": comment.id,
                    "username": comment.author.username,
                    "text": comment.text,
                    "avatar": comment.author.profile.avatar.url if comment.author.profile.avatar else "",
                    "parent_id": parent.id if parent else None,
                    "parent_username": parent.author.username if parent else "",
                    "can_delete": True,
                    "delete_url": reverse("delete_comment", args=[comment.id]),
                    "comments_count": post.comments.count()
                })
            return redirect("post_detail", post_id=post.id)

    return JsonResponse({"success": False, "error": "Комментарий должен содержать от 1 до 1000 символов."}, status=400)


@login_required
@require_POST
def delete_comment(request, comment_id):
    comment = get_object_or_404(
        PostComment.objects.select_related("post", "author", "post__author"),
        id=comment_id,
    )
    if request.user != comment.author and request.user != comment.post.author:
        return JsonResponse({"success": False, "error": "Недостаточно прав."}, status=403)

    post = comment.post
    comment.delete()
    return JsonResponse({"success": True, "comments_count": post.comments.count()})


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
@require_POST
def toggle_like(request, post_id):
    post = visible_post_or_404(request, post_id)
    if post is None:
        return JsonResponse({"success": False}, status=404)

    like = PostLike.objects.filter(
        user=request.user,
        post=post
    )

    is_liked = not like.exists()
    if not is_liked:
        like.delete()
    else:
        PostLike.objects.create(
            user=request.user,
            post=post
        )

    likes_count = PostLike.objects.filter(post=post).count()
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return JsonResponse({"success": True, "is_liked": is_liked, "likes_count": likes_count})
    return redirect(request.META.get("HTTP_REFERER", "home"))

@login_required
def mark_read(request, request_id):
    req = FriendRequest.objects.get(id=request_id, to_user=request.user)
    req.is_read = True
    req.save()

    return redirect(request.META.get('HTTP_REFERER', '/'))

@login_required
def create_post(request):
    form = PostForm(request.POST or None, request.FILES or None)
    if request.method == "POST":
        if form.is_valid():
            post = form.save(commit=False)
            post.author = request.user
            post.save()
            for index, photo in enumerate(form.cleaned_data.get("photos", [])):
                PostImage.objects.create(post=post, image=photo, order=index)
            return redirect("home")

    return render(request, "create_post.html", {"form": form})


@login_required
@require_POST
def delete_post(request, post_id):
    post = get_object_or_404(Post, id=post_id, author=request.user)
    post.delete()
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return JsonResponse({"success": True})
    return redirect("home")


@login_required
@require_POST
def manage_post(request, post_id):
    post = get_object_or_404(Post, id=post_id, author=request.user)
    form = PostManageForm(request.POST, instance=post)
    if not form.is_valid():
        return JsonResponse({"success": False, "errors": form.errors}, status=400)
    form.save()
    return JsonResponse({
        "success": True,
        "description": post.description,
        "visibility": post.visibility,
        "visibility_label": post.get_visibility_display(),
    })

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
