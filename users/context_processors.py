from .models import FriendRequest, Message
from django.contrib.auth.models import User
from django.db.models import Count


def notifications(request):
    if request.user.is_authenticated:

        requests = FriendRequest.objects.filter(
            to_user=request.user,
            is_read=False
        ).order_by('-id')

        unread_rows = Message.objects.filter(
            receiver=request.user,
            is_read=False
        ).values('sender').annotate(
            count=Count('id')
        ).order_by('-count')

        unread_chats = []

        for row in unread_rows:
            sender = User.objects.get(id=row['sender'])

            unread_chats.append({
                'sender': sender,
                'count': row['count']
            })

        following_ids = set(
            FriendRequest.objects.filter(
                from_user=request.user,
                status='accepted'
            ).values_list('to_user_id', flat=True)
        )

        follower_ids = set(
            FriendRequest.objects.filter(
                to_user=request.user,
                status='accepted'
            ).values_list('from_user_id', flat=True)
        )

        activity_count = requests.count() + len(unread_chats)

        return {
            'requests': requests,
            'unread_chats': unread_chats,
            'activity_count': activity_count,
            'following_ids': following_ids,
            'follower_ids': follower_ids
        }

    return {}