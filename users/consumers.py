from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth.models import User
from .models import Message
import json


class ChatConsumer(AsyncWebsocketConsumer):

    async def connect(self):
        self.user = self.scope["user"]

        if not self.user.is_authenticated:
            await self.close()
            return

        other_username = self.scope['url_route']['kwargs']['username']
        self.other_user = await database_sync_to_async(User.objects.get)(username=other_username)

        # одинаковая комната для двух пользователей
        users = sorted([self.user.username, self.other_user.username])
        self.room_name = f"chat_{users[0]}_{users[1]}"

        await self.channel_layer.group_add(
            self.room_name,
            self.channel_name
        )

        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(
            self.room_name,
            self.channel_name
        )

    async def receive(self, text_data):
        data = json.loads(text_data)

        event_type = data.get("type")

        if event_type == "typing":
            await self.channel_layer.group_send(
                self.room_name,
                {
                    "type": "typing_status",
                    "user": self.user.username,
                    "sender_id": self.user.id,
                    "is_typing": data.get("is_typing", False)
                }
            )
            return

        message = data.get("message", "").strip()
        reply_to_id = data.get("reply_to")

        if not message:
            return

        saved_message = await self.save_message(message, reply_to_id)

        await self.channel_layer.group_send(
            self.room_name,
            {
                "type": "chat_message",
                "message": saved_message.text,
                "user": self.user.username,
                "sender_id": self.user.id,
                "created_at": saved_message.created_at.strftime("%H:%M"),
                "reply_to": saved_message.reply_to.text if saved_message.reply_to else None,
                "reply_to_id": saved_message.reply_to.id if saved_message.reply_to else None,
            }
        )

    async def chat_message(self, event):
        await self.send(text_data=json.dumps({
            "type": "message",
            "message": event["message"],
            "user": event["user"],
            "sender_id": event["sender_id"],
            "created_at": event["created_at"],
            "reply_to": event["reply_to"],
            "reply_to_id": event["reply_to_id"],
        }))

    async def typing_status(self, event):
        await self.send(text_data=json.dumps({
            "type": "typing",
            "user": event["user"],
            "sender_id": event["sender_id"],
            "is_typing": event["is_typing"]
        }))

    @database_sync_to_async
    def save_message(self, text, reply_to_id=None):
        reply_to = None

        if reply_to_id:
            try:
                reply_to = Message.objects.get(
                    id=reply_to_id,
                    sender__in=[self.user, self.other_user],
                    receiver__in=[self.user, self.other_user]
                )
            except Message.DoesNotExist:
                reply_to = None

        return Message.objects.create(
            sender=self.user,
            receiver=self.other_user,
            text=text,
            reply_to=reply_to
        )