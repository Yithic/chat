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
    
    class Meta:
        model = Message
        fields = ['id', 'room', 'sender', 'sender_username', 'content', 'media_gcs_id', 'created_at']


class RoomSerializer(serializers.ModelSerializer):
    class Meta:
        model = Room
        fields = ['id', 'name', 'is_group', 'created_at']


class RoomMemberSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)

    class Meta:
        model = RoomMember
        fields = ['id', 'room', 'user', 'joined_at']