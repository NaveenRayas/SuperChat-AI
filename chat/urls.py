from django.urls import path
from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("chat/", views.chat_api, name="chat_api"),

    # Conversation history
    path("conversations/", views.conversations_api, name="conversations"),
    path("new-chat/", views.new_chat, name="new_chat"),
    path(
        "conversations/<int:conversation_id>/",
        views.conversation_detail,
        name="conversation_detail"
    ),
]