from django.contrib.auth import get_user_model
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated, AllowAny

from .models import Room, Message, RoomMember, PendingUpload
from .serializers import RoomSerializer, MessageSerializer
from .gcs_utils import generate_upload_url, generate_download_url
from .message_utils import delete_message_for_user

User = get_user_model()

class SignUpView(APIView):
    
    permission_classes = [AllowAny]

    def post(self, request):
        username = request.data.get('username')
        password = request.data.get('password')

        if not username or not password:
            return Response({"detail": "Username and password are required."}, status=status.HTTP_400_BAD_REQUEST)

        if User.objects.filter(username=username).exists():
            return Response({"detail": "Username already exists."}, status=status.HTTP_400_BAD_REQUEST)

        User.objects.create_user(username=username, password=password)
        return Response({"detail": "User created successfully!"}, status=status.HTTP_201_CREATED)


class UserSearchView(APIView):
    
    permission_classes = [IsAuthenticated]

    def get(self, request):
        query = request.query_params.get('search', '')
        if not query:
            return Response([], status=status.HTTP_200_OK)
        
        users = User.objects.filter(username__icontains=query).exclude(id=request.user.id)[:10]
        user_data = [
            {"id": u.id, "username": u.username, "is_online": u.is_online}
            for u in users
        ]
        return Response(user_data, status=status.HTTP_200_OK)


class CreateRoomView(APIView):
    # Add permission class to match your other views
    permission_classes = [IsAuthenticated]

    def post(self, request):
        target_user_id = request.data.get('user_id')
        if not target_user_id:
            return Response({"detail": "User ID is required."}, status=status.HTTP_400_BAD_REQUEST)
        
        # Safely get the target user using your imported User model
        try:
            target_user = User.objects.get(id=target_user_id)
        except User.DoesNotExist:
            return Response({"detail": "User not found."}, status=status.HTTP_404_NOT_FOUND)
            
        current_user = request.user

        # Prevents DMing yourself
        if current_user == target_user:
            return Response({"detail": "You cannot start a DM with yourself."}, status=status.HTTP_400_BAD_REQUEST)

        # 🔍 THE FIX: Check if a DM room already exists using the RoomMember reverse relation
        existing_rooms = Room.objects.filter(is_group=False).filter(
            members__user=current_user
        ).filter(
            members__user=target_user
        ).distinct()

        existing_dm = existing_rooms.first()

        if existing_dm:
            # 🎉 Found it! Return the existing room instead of making a duplicate
            serializer = RoomSerializer(existing_dm, context={'request': request})
            return Response(serializer.data, status=status.HTTP_200_OK)

        # 🆕 If it doesn't exist, build a brand new one
        new_room = Room.objects.create(
            name=f"DM: {current_user.username} & {target_user.username}", 
            is_group=False
        )
        
        # 🔗 Use your RoomMember model to link the users instead of .add()
        RoomMember.objects.create(room=new_room, user=current_user)
        RoomMember.objects.create(room=new_room, user=target_user)
        
        serializer = RoomSerializer(new_room, context={'request': request})
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class RoomListView(APIView):
    
    permission_classes = [IsAuthenticated]

    def get(self, request):
        rooms = Room.objects.filter(members__user=request.user).order_by('-created_at')
        serializer = RoomSerializer(rooms, many=True , context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)


class MessageHistoryView(APIView):
    
    permission_classes = [IsAuthenticated]

    def get(self, request, room_id):
        is_member = RoomMember.objects.filter(room_id=room_id, user=request.user).exists()
        if not is_member:
            return Response(
                {"detail": "You do not have permission to view this room's history."}, 
                status=status.HTTP_403_FORBIDDEN
            )

        try:
            limit = min(int(request.query_params.get('limit', 50)), 100)
        except (TypeError, ValueError):
            return Response({"detail": "Invalid limit parameter."}, status=status.HTTP_400_BAD_REQUEST)

        before_id = request.query_params.get('before')
        messages_qs = Message.objects.filter(room_id=room_id).select_related(
            'sender', 'reply_to', 'reply_to__sender'
        )

        if before_id is not None:
            try:
                before_id = int(before_id)
            except (TypeError, ValueError):
                return Response({"detail": "Invalid before parameter."}, status=status.HTTP_400_BAD_REQUEST)
            messages_qs = messages_qs.filter(id__lt=before_id)

        messages = list(messages_qs.order_by('-id')[: limit + 1])
        has_more = len(messages) > limit
        if has_more:
            messages = messages[:limit]
        messages.reverse()

        serializer = MessageSerializer(messages, many=True)
        return Response({"messages": serializer.data, "has_more": has_more}, status=status.HTTP_200_OK)


class GenerateGCSSignedURLView(APIView):

    permission_classes = [IsAuthenticated]

    def post(self, request):
        file_name = request.data.get('file_name')
        content_type = request.data.get('content_type')

        if not file_name or not content_type:
            return Response(
                {"detail": "Both file_name and content_type are required fields."},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            upload_url, gcs_file_id = generate_upload_url(
                request.user.id, file_name, content_type
            )
            PendingUpload.objects.create(
                user=request.user,
                gcs_id=gcs_file_id
            )
            return Response({
                "upload_url": upload_url,
                "media_gcs_id": gcs_file_id,
            }, status=status.HTTP_200_OK)

        except Exception as e:
            return Response(
                {"detail": f"Failed to generate signed URL: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class GenerateGCSDownloadURLView(APIView):

    permission_classes = [IsAuthenticated]

    def get(self, request):
        media_gcs_id = request.query_params.get('media_gcs_id')
        if not media_gcs_id:
            return Response(
                {"detail": "media_gcs_id is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        is_pending_owner = PendingUpload.objects.filter(
            gcs_id=media_gcs_id,
            user=request.user,
            is_attached=False
        ).exists()

        is_member = Message.objects.filter(
            media_gcs_id=media_gcs_id,
            room__members__user=request.user,
        ).exists()
        if not (is_member or is_pending_owner):
            return Response(
                {"detail": "You do not have access to this file."},
                status=status.HTTP_403_FORBIDDEN,
            )

        try:
            download_url = generate_download_url(media_gcs_id)
            return Response({"download_url": download_url}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response(
                {"detail": f"Failed to generate download URL: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class DeleteMessageView(APIView):

    permission_classes = [IsAuthenticated]

    def delete(self, request, room_id, message_id):
        is_member = RoomMember.objects.filter(room_id=room_id, user=request.user).exists()
        if not is_member:
            return Response(
                {"detail": "You do not have permission to access this room."},
                status=status.HTTP_403_FORBIDDEN,
            )

        deleted_id, error = delete_message_for_user(message_id, request.user, room_id)
        if error == 'not_found':
            return Response({"detail": "Message not found."}, status=status.HTTP_404_NOT_FOUND)
        if error == 'forbidden':
            return Response(
                {"detail": "You can only delete your own messages."},
                status=status.HTTP_403_FORBIDDEN,
            )

        return Response({"id": deleted_id}, status=status.HTTP_200_OK)

class CreateGroupView(APIView):
   
    permission_classes = [IsAuthenticated]

    def post(self, request):
        name = request.data.get('name')
        user_ids = request.data.get('user_ids', [])

        if not name or not user_ids:
            return Response(
                {"detail": "A group name and at least one other user are required."}, 
                status=status.HTTP_400_BAD_REQUEST
            )

        room = Room.objects.create(name=name, is_group=True)
        
        RoomMember.objects.create(room=room, user=request.user)
        
        for user_id in user_ids:
            try:
                target_user = User.objects.get(id=user_id)
                if target_user != request.user:
                    RoomMember.objects.create(room=room, user=target_user)
            except User.DoesNotExist:
                continue 

        serializer = RoomSerializer(room, context={'request': request})
        return Response(serializer.data, status=status.HTTP_201_CREATED)