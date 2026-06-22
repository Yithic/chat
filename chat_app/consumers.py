import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from .models import Message

class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.room_id = self.scope['url_route']['kwargs']['room_id']
        self.room_group_name = f'chat_{self.room_id}'
        self.user = self.scope['user']

        if self.user.is_anonymous:
            await self.close()
            return

        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )

    async def receive(self, text_data):
        data = json.loads(text_data)
        
        if data['type'] == 'chat_message':
            message_data = await self.save_message(data['content'])
            
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

    @database_sync_to_async
    def save_message(self, content):
        msg = Message.objects.create(
            room_id=self.room_id,
            sender=self.user,
            content=content
        )
        return {
            'id': msg.id,
            'content': msg.content,
            'sender_username': msg.sender.username,
            'created_at': msg.created_at.isoformat()
        }