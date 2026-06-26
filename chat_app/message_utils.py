from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

from .models import Message


def build_message_payload(message):
    payload = {
        'id': message.id,
        'content': message.content,
        'sender_id': message.sender_id,
        'sender_username': message.sender.username,
        'created_at': message.created_at.isoformat(),
        'media_gcs_id': message.media_gcs_id,
        'media_file_name': message.media_file_name,
        'media_content_type': message.media_content_type,
        'reply_to': None,
    }
    if message.reply_to_id:
        payload['reply_to'] = {
            'id': message.reply_to_id,
            'sender_username': message.reply_to.sender.username,
            'content': message.reply_to.content,
            'media_file_name': message.reply_to.media_file_name,
        }
    return payload


def broadcast_message_deleted(room_id, message_id):
    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        f'chat_{room_id}',
        {
            'type': 'broadcast_message_deleted',
            'message_id': message_id,
        },
    )


def delete_message_for_user(message_id, user, room_id):
    msg = Message.objects.filter(id=message_id, room_id=room_id).first()
    if not msg:
        return None, 'not_found'
    if msg.sender_id != user.id:
        return None, 'forbidden'
    broadcast_message_deleted(room_id, message_id)
    msg.delete()
    return message_id, None
