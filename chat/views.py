
from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST
from django.conf import settings

from .models import ChatConversation, ChatMessage

import json
import urllib.request
import urllib.error


GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "openai/gpt-oss-20b"


# HOME PAGE
@ensure_csrf_cookie
def home(request):

    if not request.session.session_key:
        request.session.create()

    return render(request, "chat/index.html")


# GET ALL CONVERSATIONS
@require_GET
def conversations_api(request):

    if not request.session.session_key:
        return JsonResponse({"conversations": []})

    conversations = ChatConversation.objects.filter(
        session_key=request.session.session_key
    ).order_by("-updated_at")

    data = []

    for conversation in conversations:

        data.append({
            "id": conversation.id,
            "title": conversation.title,
            "updated_at": conversation.updated_at.isoformat()
        })

    return JsonResponse({
        "conversations": data
    })


# CREATE NEW CHAT
@require_POST
def new_chat(request):

    if not request.session.session_key:
        request.session.create()

    conversation = ChatConversation.objects.create(
        session_key=request.session.session_key,
        title="New Chat"
    )

    return JsonResponse({
        "conversation_id": conversation.id,
        "title": conversation.title
    })


# LOAD PREVIOUS CONVERSATION
@require_GET
def conversation_detail(request, conversation_id):

    conversation = ChatConversation.objects.filter(
        id=conversation_id,
        session_key=request.session.session_key
    ).first()

    if conversation is None:

        return JsonResponse({
            "error": "Conversation not found."
        }, status=404)

    messages = conversation.messages.order_by(
        "created_at", "id"
    )

    message_data = []

    for message in messages:

        message_data.append({
            "role": message.role,
            "content": message.content
        })

    return JsonResponse({
        "conversation_id": conversation.id,
        "title": conversation.title,
        "messages": message_data
    })


# CHAT API
@require_POST
def chat_api(request):

    try:

        data = json.loads(request.body)

        if not isinstance(data, dict):
            return JsonResponse(
                {"error": "Invalid request data."},
                status=400
            )

        message = data.get("message", "")

        if not isinstance(message, str):
            return JsonResponse(
                {"error": "Invalid message."},
                status=400
            )

        message = message.strip()

        if not message:
            return JsonResponse(
                {"error": "Please enter a message."},
                status=400
            )

        api_key = settings.GROQ_API_KEY

        if not api_key:
            return JsonResponse(
                {"error": "Groq API key is not configured."},
                status=500
            )

        # GET OR CREATE SESSION
        if not request.session.session_key:
            request.session.create()

        session_key = request.session.session_key

        # GET SELECTED CONVERSATION
        conversation_id = data.get("conversation_id")

        if conversation_id is not None:

            try:
                conversation_id = int(conversation_id)

            except (ValueError, TypeError):

                return JsonResponse(
                    {"error": "Invalid conversation ID."},
                    status=400
                )

            conversation = ChatConversation.objects.filter(
                id=conversation_id,
                session_key=session_key
            ).first()

            if conversation is None:

                return JsonResponse(
                    {"error": "Conversation not found."},
                    status=404
                )

        else:

            conversation = ChatConversation.objects.create(
                session_key=session_key,
                title="New Chat"
            )

        # GET PREVIOUS MESSAGES
        previous_messages = list(
            conversation.messages
            .order_by("-created_at", "-id")
            .values("role", "content")[:20]
        )

        previous_messages.reverse()

        # SAVE USER MESSAGE
        ChatMessage.objects.create(
            conversation=conversation,
            role="user",
            content=message
        )

        # SET CONVERSATION TITLE
        if conversation.title == "New Chat":
            conversation.title = message[:50]

        conversation.save(
            update_fields=["title", "updated_at"]
        )

        # PREPARE GROQ MESSAGES
        messages = [
            {
                "role": "system",
                "content": (
                    "You are SuperChat, a helpful AI assistant. "
                    "Remember and use previous messages in this conversation "
                    "to answer follow-up questions. "
                    "Use simple English and give clear, accurate answers. "
                    "Use headings and bullet points when helpful. "
                    "Avoid unnecessary decorative symbols."
                )
            }
        ]

        for item in previous_messages:

            messages.append({
                "role": item["role"],
                "content": item["content"][:10000]
            })

        messages.append({
            "role": "user",
            "content": message
        })

        # SEND REQUEST TO GROQ
        payload = {
            "model": GROQ_MODEL,
            "messages": messages,
            "max_completion_tokens": 1024,
            "temperature": 0.7
        }

        request_data = json.dumps(payload).encode("utf-8")

        req = urllib.request.Request(
            GROQ_API_URL,
            data=request_data,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "User-Agent": "SuperChat/1.0"
            },
            method="POST"
        )

        with urllib.request.urlopen(req, timeout=60) as response:

            result = json.loads(
                response.read().decode("utf-8")
            )

        ai_reply = result["choices"][0]["message"]["content"]

        if not isinstance(ai_reply, str) or not ai_reply.strip():
            raise ValueError("Empty AI response received")

        # SAVE AI RESPONSE
        ChatMessage.objects.create(
            conversation=conversation,
            role="assistant",
            content=ai_reply
        )

        conversation.save(
            update_fields=["updated_at"]
        )

        return JsonResponse({
            "reply": ai_reply,
            "conversation_id": conversation.id,
            "title": conversation.title
        })

    except urllib.error.HTTPError as e:

        error_details = e.read().decode(
            "utf-8", errors="replace"
        )

        print("Groq API Error:", e.code, error_details)

        return JsonResponse(
            {"error": "Groq AI request failed. Please check API access."},
            status=502
        )

    except urllib.error.URLError as e:

        print("Groq Connection Error:", str(e))

        return JsonResponse(
            {"error": "Unable to connect to Groq AI. Please try again."},
            status=503
        )

    except json.JSONDecodeError:

        return JsonResponse(
            {"error": "Invalid JSON request."},
            status=400
        )

    except Exception as e:

        print("SuperChat Error:", str(e))

        return JsonResponse(
            {"error": "Sorry, AI service is currently unavailable. Please try again."},
            status=500
        )
