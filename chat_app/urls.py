from django.urls import path
from .views import RoomListView, MessageHistoryView, GenerateGCSSignedURLView, SignUpView, UserSearchView, CreateRoomView, CreateGroupView

urlpatterns = [
    path('signup/', SignUpView.as_view(), name='signup'),
    path('users/search/', UserSearchView.as_view(), name='user-search'),
    path('rooms/create/', CreateRoomView.as_view(), name='room-create'),
    
    path('rooms/create-group/', CreateGroupView.as_view(), name='room-create-group'),
    
    path('rooms/', RoomListView.as_view(), name='room-list'),
    path('rooms/<int:room_id>/history/', MessageHistoryView.as_view(), name='message-history'),
    path('media/upload-url/', GenerateGCSSignedURLView.as_view(), name='gcs-upload-url'),
]