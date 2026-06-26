from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import Room, RoomMember, Message

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'is_online']


class MessageSerializer(serializers.ModelSerializer):
    sender_username = serializers.CharField(source='sender.username', read_only=True)
    reply_to = serializers.SerializerMethodField()

    class Meta:
        model = Message
        fields = [
            'id', 'room', 'sender', 'sender_username', 'content',
            'media_gcs_id', 'media_file_name', 'media_content_type',
            'reply_to', 'created_at',
        ]

    def get_reply_to(self, obj):
        if not obj.reply_to_id:
            return None
        return {
            'id': obj.reply_to_id,
            'sender_username': obj.reply_to.sender.username,
            'content': obj.reply_to.content,
            'media_file_name': obj.reply_to.media_file_name,
        }


class RoomSerializer(serializers.ModelSerializer):
    name = serializers.SerializerMethodField()
    other_user_id = serializers.SerializerMethodField()
    other_user_online = serializers.SerializerMethodField()

    class Meta:
        model = Room
        fields = ['id', 'name', 'is_group', 'other_user_id', 'other_user_online', 'created_at']

    def get_name(self, obj):
        request = self.context.get('request')

        if not obj.is_group and request and request.user.is_authenticated:
            other_member = obj.members.exclude(user=request.user).select_related('user').first()
            if other_member:
                return other_member.user.username

        return obj.name

    def _get_other_member(self, obj):
        request = self.context.get('request')
        if obj.is_group or not request or not request.user.is_authenticated:
            return None
        return obj.members.exclude(user=request.user).select_related('user').first()

    def get_other_user_id(self, obj):
        other_member = self._get_other_member(obj)
        return other_member.user.id if other_member else None

    def get_other_user_online(self, obj):
        other_member = self._get_other_member(obj)
        return other_member.user.is_online if other_member else False


class RoomMemberSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)

    class Meta:
        model = RoomMember
        fields = ['id', 'room', 'user', 'joined_at']
