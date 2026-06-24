def build_message_payload(message):
    payload = {
        'id': message.id,
        'content': message.content,
        'sender_username': message.sender.username,
        'created_at': message.created_at.isoformat(),
        'reply_to': None,
    }
    if message.reply_to_id:
        payload['reply_to'] = {
            'id': message.reply_to_id,
            'sender_username': message.reply_to.sender.username,
            'content': message.reply_to.content,
        }
    return payload
