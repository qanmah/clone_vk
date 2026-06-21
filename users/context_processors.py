from .models import FriendRequest, Message, PostComment, PostLike
from django.contrib.auth.models import User
from django.db.models import Count, Max


def _avatar(user):
    return user.profile.avatar.url if user.profile.avatar else "/media/avatars/default.jpg"


def _post_kind(post):
    return "видео" if post.video else "публикацию"


def notifications(request):
    if not request.user.is_authenticated:
        return {}

    requests = FriendRequest.objects.filter(
        to_user=request.user,
        is_read=False
    ).select_related("from_user", "from_user__profile").order_by("-created_at")

    unread_rows = Message.objects.filter(
        receiver=request.user,
        is_read=False
    ).values("sender").annotate(
        count=Count("id"),
        latest_at=Max("created_at")
    ).order_by("-latest_at")

    sender_ids = [row["sender"] for row in unread_rows]
    senders = User.objects.filter(id__in=sender_ids).select_related("profile")
    senders_by_id = {sender.id: sender for sender in senders}

    unread_chats = []
    activity_items = []

    for row in unread_rows:
        sender = senders_by_id.get(row["sender"])
        if not sender:
            continue

        unread_chats.append({
            "sender": sender,
            "count": row["count"]
        })
        activity_items.append({
            "type": "message",
            "icon": "chat_bubble",
            "actor": sender,
            "avatar": _avatar(sender),
            "title": f"{sender.username} написал вам личное сообщение",
            "text": f"Новых сообщений: {row['count']}",
            "url": f"/chat/{sender.username}/",
            "created_at": row["latest_at"],
            "is_new": True,
        })

    for req in requests[:12]:
        activity_items.append({
            "type": "follow",
            "icon": "person_add",
            "actor": req.from_user,
            "avatar": _avatar(req.from_user),
            "title": f"{req.from_user.username} подписался(-ась) на вас",
            "text": "Можно подписаться в ответ или отметить как прочитанное",
            "url": f"/profile/{req.from_user.username}",
            "created_at": req.created_at,
            "request": req,
            "is_new": True,
        })

    likes = PostLike.objects.filter(
        post__author=request.user
    ).exclude(user=request.user).select_related(
        "user", "user__profile", "post"
    ).order_by("-created_at")[:20]

    for like in likes:
        activity_items.append({
            "type": "like",
            "icon": "favorite",
            "actor": like.user,
            "avatar": _avatar(like.user),
            "title": f"{like.user.username} поставил(-а) лайк вашей публикации",
            "text": f"К публикации #{like.post_id}",
            "url": f"/post/{like.post_id}/",
            "created_at": like.created_at,
            "is_new": True,
        })

    comments = PostComment.objects.filter(
        post__author=request.user
    ).exclude(author=request.user).select_related(
        "author", "author__profile", "post"
    ).order_by("-created_at")[:20]

    for comment in comments:
        activity_items.append({
            "type": "comment",
            "icon": "mode_comment",
            "actor": comment.author,
            "avatar": _avatar(comment.author),
            "title": f"{comment.author.username} прокомментировал(-а) ваше {_post_kind(comment.post)}",
            "text": comment.text,
            "url": f"/post/{comment.post_id}/",
            "created_at": comment.created_at,
            "is_new": True,
        })

    activity_items.sort(key=lambda item: item["created_at"], reverse=True)
    activity_items = activity_items[:30]

    following_ids = set(
        FriendRequest.objects.filter(
            from_user=request.user,
            status="accepted"
        ).values_list("to_user_id", flat=True)
    )

    follower_ids = set(
        FriendRequest.objects.filter(
            to_user=request.user,
            status="accepted"
        ).values_list("from_user_id", flat=True)
    )

    activity_count = sum(1 for item in activity_items if item.get("is_new"))

    return {
        "requests": requests,
        "unread_chats": unread_chats,
        "activity_items": activity_items,
        "activity_count": activity_count,
        "following_ids": following_ids,
        "follower_ids": follower_ids
    }
