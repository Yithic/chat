# chat/asgi.py
import os
from django.core.asgi import get_asgi_application

# 1. Set settings module environmental variable
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'chat.settings')

# 2. Initialize the core Django ASGI application first! 
# This safely boots the app registry and loads your models.
django_asgi_app = get_asgi_application()

# 3. NOW it is completely safe to import Channels, routing, and middleware
from channels.routing import ProtocolTypeRouter, URLRouter
from chat_app.middleware import JWTAuthMiddleware
from chat_app import routing

application = ProtocolTypeRouter({
    # Use the pre-initialized django ASGI application here
    "http": django_asgi_app,
    
    "websocket": JWTAuthMiddleware(
        URLRouter(
            routing.websocket_urlpatterns
        )
    ),
})