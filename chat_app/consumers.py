import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth import get_user_model
from .models import Message, RoomMember
from .message_utils import build_message_payload

User = get_user_model()


class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.room_id = self.scope['url_route']['kwargs']['room_id']
        self.room_group_name = f'chat_{self.room_id}'
        self.user = self.scope['user']

        if self.user.is_anonymous:
            await self.close()
            return

        is_member = await self.is_room_member(self.room_id, self.user)

        if not is_member:
            await self.close(code=4003)
            return

        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )
        await self.accept()

        presence = await self.set_user_online(True)
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'broadcast_presence',
                'presence': presence,
            }
        )

    async def disconnect(self, close_code):
        if hasattr(self, 'room_group_name'):
            presence = await self.set_user_online(False)
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'broadcast_presence',
                    'presence': presence,
                }
            )
            await self.channel_layer.group_discard(
                self.room_group_name,
                self.channel_name
            )

    async def receive(self, text_data):
        data = json.loads(text_data)

        if data['type'] == 'chat_message':
            reply_to_id = data.get('reply_to_id')
            message_data = await self.save_message(data['content'], reply_to_id)

            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'broadcast_message',
                    'message': message_data
                }
            )

    async def broadcast_message(self, event):
        message = event['message']

        await self.send(text_data=json.dumps({
            'type': 'message',
            'data': message
        }))

    async def broadcast_presence(self, event):
        await self.send(text_data=json.dumps({
            'type': 'presence',
            'data': event['presence'],
        }))

    @database_sync_to_async
    def save_message(self, content, reply_to_id=None):
        reply_to = None
        if reply_to_id:
            reply_to = Message.objects.filter(
                id=reply_to_id,
                room_id=self.room_id,
            ).select_related('sender').first()

        msg = Message.objects.create(
            room_id=self.room_id,
            sender=self.user,
            content=content,
            reply_to=reply_to,
        )
        msg = Message.objects.select_related(
            'sender', 'reply_to', 'reply_to__sender'
        ).get(id=msg.id)
        return build_message_payload(msg)

    @database_sync_to_async
    def is_room_member(self, room_id, user):
        return RoomMember.objects.filter(room_id=room_id, user=user).exists()

    @database_sync_to_async
    def set_user_online(self, is_online):
        User.objects.filter(id=self.user.id).update(is_online=is_online)
        return {
            'user_id': self.user.id,
            'username': self.user.username,
            'is_online': is_online,
        }
