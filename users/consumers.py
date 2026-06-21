from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth.models import User
from django.utils import timezone
from .models import Message
import json


class ChatConsumer(AsyncWebsocketConsumer):

    async def connect(self):
        self.user = self.scope["user"]

        if not self.user.is_authenticated:
            await self.close()
            return

        other_username = self.scope["url_route"]["kwargs"]["username"]

        try:
            self.other_user = await database_sync_to_async(User.objects.get)(
                username=other_username
            )
        except User.DoesNotExist:
            await self.close()
            return

        users = sorted([self.user.username, self.other_user.username])
        self.room_name = f"chat_{users[0]}_{users[1]}"

        await self.channel_layer.group_add(self.room_name, self.channel_name)
        await self.accept()

        await self.update_last_seen()

        read_ids = await self.mark_messages_as_read()

        if read_ids:
            await self.channel_layer.group_send(self.room_name, {
                "type": "read_receipt",
                "reader": self.user.username,
                "message_ids": read_ids,
            })

        await self.channel_layer.group_send(self.room_name, {
            "type": "user_status",
            "user": self.user.username,
            "is_online": True,
        })

    async def disconnect(self, close_code):
        if hasattr(self, "room_name"):
            await self.update_last_seen()

            await self.channel_layer.group_send(self.room_name, {
                "type": "user_status",
                "user": self.user.username,
                "is_online": False,
            })

            await self.channel_layer.group_discard(
                self.room_name,
                self.channel_name
            )

    async def receive(self, text_data):
        data = json.loads(text_data)
        event_type = data.get("type")

        if event_type == "typing":
            await self.channel_layer.group_send(self.room_name, {
                "type": "typing_status",
                "user": self.user.username,
                "sender_id": self.user.id,
                "is_typing": data.get("is_typing", False),
            })
            return
        
        if event_type == "mark_read":
            read_ids = await self.mark_messages_as_read()

            if read_ids:
                await self.channel_layer.group_send(self.room_name, {
                    "type": "read_receipt",
                    "reader": self.user.username,
                    "message_ids": read_ids,
                })

            return

        message = data.get("message", "").strip()
        reply_to_id = data.get("reply_to")

        if not message:
            return

        saved = await self.save_message(message, reply_to_id)

        await self.channel_layer.group_send(self.room_name, {
            "type": "chat_message",
            "message": saved["text"],
            "user": self.user.username,
            "sender_id": self.user.id,
            "created_at": saved["created_at"],
            "message_id": saved["id"],
            "created_date": saved["created_date"],
            "is_read": saved["is_read"],
            "reply_to_id": saved["reply_to_id"],
            "reply_text": saved["reply_text"],
            "reply_user": saved["reply_user"],
        })

    async def chat_message(self, event):
        await self.send(text_data=json.dumps({
            "type": "message",
            "message": event["message"],
            "user": event["user"],
            "sender_id": event["sender_id"],
            "created_at": event["created_at"],
            "created_date": event.get("created_date"),
            "message_id": event.get("message_id"),
            "is_read": event.get("is_read", False),
            "reply_to_id": event.get("reply_to_id"),
            "reply_text": event.get("reply_text"),
            "reply_user": event.get("reply_user"),
        }))

    async def shared_post_message(self, event):
        await self.send(text_data=json.dumps({
            "type": "shared_post",
            "message_id": event["message_id"],
            "user": event["user"],
            "sender_id": event["sender_id"],
            "created_at": event["created_at"],
            "created_date": event.get("created_date"),
            "is_read": event.get("is_read", False),
            "post_id": event["post_id"],
            "post_url": event["post_url"],
            "media_type": event["media_type"],
            "media_url": event["media_url"],
            "post_author": event["post_author"],
            "views": event.get("views", 0),
            "likes": event.get("likes", 0),
        }))

    async def typing_status(self, event):
        await self.send(text_data=json.dumps({
            "type": "typing",
            "user": event["user"],
            "sender_id": event["sender_id"],
            "is_typing": event["is_typing"],
        }))

    async def user_status(self, event):
        await self.send(text_data=json.dumps({
            "type": "user_status",
            "user": event["user"],
            "is_online": event["is_online"],
        }))

    async def message_deleted(self, event):
        await self.send(text_data=json.dumps({
            "type": "message_deleted",
            "message_id": event["message_id"],
        }))

    async def message_edited(self, event):
        await self.send(text_data=json.dumps({
            "type": "message_edited",
            "message_id": event["message_id"],
            "text": event["text"],
        }))

    async def message_pinned(self, event):
        await self.send(text_data=json.dumps({
            "type": "message_pinned",
            "message_id": event["message_id"],
            "text": event.get("text") or "Фото",
            "user": event.get("user"),
        }))

    async def message_unpinned(self, event):
        await self.send(text_data=json.dumps({
            "type": "message_unpinned",
            "message_id": event["message_id"],
        }))

    async def read_receipt(self, event):
        await self.send(text_data=json.dumps({
            "type": "read_receipt",
            "reader": event["reader"],
            "message_ids": event["message_ids"],
        }))

    @database_sync_to_async
    def save_message(self, text, reply_to_id=None):
        reply_to = None

        if reply_to_id:
            try:
                reply_to = Message.objects.select_related("sender").get(
                    id=reply_to_id,
                    sender__in=[self.user, self.other_user],
                    receiver__in=[self.user, self.other_user],
                )
            except Message.DoesNotExist:
                reply_to = None

        msg = Message.objects.create(
            sender=self.user,
            receiver=self.other_user,
            text=text,
            reply_to=reply_to,
        )

        return {
            "id": msg.id,
            "text": msg.text,
            "created_at": msg.created_at.strftime("%H:%M"),
            "created_date": msg.created_at.strftime("%Y-%m-%d"),
            "is_read": msg.is_read,
            "reply_to_id": reply_to.id if reply_to else None,
            "reply_text": reply_to.text[:80] if reply_to and reply_to.text else None,
            "reply_user": reply_to.sender.username if reply_to else None,
        }

    @database_sync_to_async
    def update_last_seen(self):
        profile = self.user.profile
        profile.last_seen = timezone.now()
        profile.save(update_fields=["last_seen"])

    @database_sync_to_async
    def mark_messages_as_read(self):
        unread_ids = list(
            Message.objects.filter(
                sender=self.other_user,
                receiver=self.user,
                is_read=False
            ).values_list("id", flat=True)
        )

        if unread_ids:
            Message.objects.filter(id__in=unread_ids).update(is_read=True)

        return unread_ids
