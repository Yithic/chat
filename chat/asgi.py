import os
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from chat_app.middleware import JWTAuthMiddleware
from chat_app import routing

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'chat.settings')

application = ProtocolTypeRouter({
    "http": get_asgi_application(),
    "websocket": JWTAuthMiddleware(
        URLRouter(
            routing.websocket_urlpatterns
        )
    ),
})