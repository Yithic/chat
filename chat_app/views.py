import datetime
from django.conf import settings
from django.contrib.auth import get_user_model
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated, AllowAny
from google.cloud import storage

from .models import Room, Message, RoomMember
from .serializers import RoomSerializer, MessageSerializer

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
        user_data = [{"id": u.id, "username": u.username} for u in users]
        return Response(user_data, status=status.HTTP_200_OK)


class CreateRoomView(APIView):
    
    permission_classes = [IsAuthenticated]

    def post(self, request):
        target_user_id = request.data.get('user_id')
        if not target_user_id:
            return Response({"detail": "User ID is required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            target_user = User.objects.get(id=target_user_id)
        except User.DoesNotExist:
            return Response({"detail": "User not found."}, status=status.HTTP_404_NOT_FOUND)

        room = Room.objects.create(name=f"Chat with {target_user.username}", is_group=False)
        
        RoomMember.objects.create(room=room, user=request.user)
        RoomMember.objects.create(room=room, user=target_user)

        serializer = RoomSerializer(room)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class RoomListView(APIView):
    
    permission_classes = [IsAuthenticated]

    def get(self, request):
        rooms = Room.objects.filter(members__user=request.user).order_by('-created_at')
        serializer = RoomSerializer(rooms, many=True)
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

        messages = Message.objects.filter(room_id=room_id).order_by('id')[:50]
        serializer = MessageSerializer(messages, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


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
            storage_client = storage.Client()
            bucket_name = getattr(settings, 'GCS_BUCKET_NAME', 'your-default-bucket-name')
            bucket = storage_client.bucket(bucket_name)

            timestamp = datetime.datetime.utcnow().strftime('%Y%m%d%H%M%S')
            gcs_file_id = f"uploads/user_{request.user.id}/{timestamp}_{file_name}"
            blob = bucket.blob(gcs_file_id)

            signed_url = blob.generate_signed_url(
                version="v4",
                expiration=datetime.timedelta(minutes=15),
                method="PUT",
                content_type=content_type,
            )

            return Response({
                "upload_url": signed_url,
                "media_gcs_id": gcs_file_id
            }, status=status.HTTP_200_OK)

        except Exception as e:
            return Response(
                {"detail": f"Failed to generate signed URL: {str(e)}"}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        
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

        serializer = RoomSerializer(room)
        return Response(serializer.data, status=status.HTTP_201_CREATED)