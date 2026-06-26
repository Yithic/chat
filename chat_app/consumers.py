import json

from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth import get_user_model

from .models import Message, RoomMember, PendingUpload
from .message_utils import build_message_payload, delete_message_for_user
from .gcs_utils import user_owns_media_path

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
        # 1. 🛡️ Catch malformed JSON safely
        try:
            data = json.loads(text_data)
        except json.JSONDecodeError:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'data': {'detail': 'Invalid JSON format.'},
            }))
            return

        # 2. 🛡️ Ensure the payload is a dictionary
        if not isinstance(data, dict):
            await self.send(text_data=json.dumps({
                'type': 'error',
                'data': {'detail': 'Expected a JSON object.'},
            }))
            return

        # 3. 🛡️ Safely extract the type without risking a KeyError
        action_type = data.get('type')
        if not action_type:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'data': {'detail': 'Missing "type" field in payload.'},
            }))
            return

        # 4. Process the validated actions safely
        if action_type == 'chat_message':
            reply_to_id = data.get('reply_to_id')
            message_data, error = await self.save_message(
                data.get('content'),
                data.get('media_gcs_id'),
                data.get('media_file_name'),
                data.get('media_content_type'),
                reply_to_id,
            )
            if error:
                await self.send(text_data=json.dumps({
                    'type': 'error',
                    'data': {'detail': error},
                }))
                return

            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'broadcast_message',
                    'message': message_data
                }
            )
        elif action_type == 'delete_message':
            message_id = data.get('message_id')
            deleted_id, gcs_id, error = await self.delete_message(message_id)
            if error:
                await self.send(text_data=json.dumps({
                    'type': 'error',
                    'data': {'detail': error},
                }))
                return 
            if deleted_id:
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        'type': 'broadcast_message_deleted',  # Triggers your built-in handler
                        'message_id': deleted_id
                    }
                )
            if gcs_id:
                import asyncio
                from asgiref.sync import sync_to_async
                from .gcs_utils import delete_gcs_blob
                
                asyncio.create_task(sync_to_async(delete_gcs_blob)(gcs_id))

    async def broadcast_message(self, event):
        message = event['message']

        await self.send(text_data=json.dumps({
            'type': 'message',
            'data': message
        }))

    async def broadcast_message_deleted(self, event):
        await self.send(text_data=json.dumps({
            'type': 'message_deleted',
            'data': {'id': event['message_id']},
        }))

    async def broadcast_presence(self, event):
        await self.send(text_data=json.dumps({
            'type': 'presence',
            'data': event['presence'],
        }))

    @database_sync_to_async
    def save_message(self, content, media_gcs_id, media_file_name, media_content_type, reply_to_id=None):
        content = (content or '').strip() or None
        media_gcs_id = media_gcs_id or None

        if not content and not media_gcs_id:
            return None, 'Message must have text or an attachment.'

        if media_gcs_id:
            updated_count = PendingUpload.objects.filter(
                gcs_id=media_gcs_id,
                user=self.user,
                is_attached=False
            ).update(is_attached=True)

            if updated_count == 0:
                return None, 'Invalid, unauthorized, or already-used attachment.'

        reply_to = None
        if reply_to_id:
            reply_to = Message.objects.filter(
                id=reply_to_id,
                room_id=self.room_id,
            ).select_related('sender').first()
        safe_file_name = None
        safe_content_type = None

        if media_gcs_id:
            if media_file_name:
                safe_file_name = str(media_file_name)[:255]
    
            if media_content_type:
                safe_content_type = str(media_content_type)[:100]
        msg = Message.objects.create(
            room_id=self.room_id,
            sender=self.user,
            content=content,
            media_gcs_id=str(media_gcs_id)[:500] if media_gcs_id else None,
            media_file_name=safe_file_name if media_gcs_id else None,
            media_content_type=safe_content_type if media_gcs_id else None,
            reply_to=reply_to,
        )
        msg = Message.objects.select_related(
            'sender', 'reply_to', 'reply_to__sender'
        ).get(id=msg.id)
        return build_message_payload(msg), None

    @database_sync_to_async
    def delete_message(self, message_id):
        if not message_id:
            return None, 'message_id is required.'
        msg = Message.objects.filter(id=message_id, room_id=self.room_id).first()
        gcs_id = msg.media_gcs_id if msg else None
        deleted_id, error = delete_message_for_user(message_id, self.user, self.room_id)
        return deleted_id, gcs_id, error

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
