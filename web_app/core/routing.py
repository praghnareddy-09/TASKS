from django.urls import path

from core.consumers import WorkflowConsumer

websocket_urlpatterns = [
    path("ws/workflow/", WorkflowConsumer.as_asgi()),
]
