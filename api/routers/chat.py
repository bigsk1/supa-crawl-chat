from fastapi import APIRouter, Body, Query, HTTPException, status, Path, Depends
from typing import List, Dict, Any, Optional
from pydantic import BaseModel
import os
import time
import uuid

# Import from main project
from app_logging import get_logger
from chat import ChatBot
from brave_llm_context import (
    brave_ui_payload,
    fetch_llm_context,
    format_grounding_for_prompt,
    should_merge_brave,
)
from chat_intent import is_local_inventory_query

logger = get_logger(__name__)

# Create router
router = APIRouter()


# Define models
class Message(BaseModel):
    role: str
    content: str
    timestamp: Optional[str] = None

    class Config:
        arbitrary_types_allowed = True

    @classmethod
    def from_dict(cls, message_dict):
        """Create a Message from a dictionary, converting datetime to string if needed."""
        if 'timestamp' in message_dict and message_dict['timestamp'] is not None:
            if not isinstance(message_dict['timestamp'], str):
                message_dict['timestamp'] = str(message_dict['timestamp'])
        return cls(**message_dict)

class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None
    user_id: Optional[str] = None
    profile: Optional[str] = None

class ChatResponse(BaseModel):
    response: str
    session_id: str
    user_id: Optional[str] = None
    context_mode: str = "auto"
    context: Optional[List[Dict[str, Any]]] = None
    conversation_history: Optional[List[Message]] = None
    brave_used: bool = False
    brave_sources: Optional[List[Dict[str, Any]]] = None
    brave_preview: Optional[str] = None

class ProfileResponse(BaseModel):
    name: str
    description: str
    is_active: bool

class ProfileListResponse(BaseModel):
    profiles: List[ProfileResponse]
    count: int
    active_profile: str

class ChatDefaultsResponse(BaseModel):
    user_id: Optional[str] = None
    profile: str
    session_id: Optional[str] = None

class ConversationHistoryResponse(BaseModel):
    messages: List[Message]
    count: int
    session_id: str
    user_id: Optional[str] = None

class UserPreference(BaseModel):
    id: Optional[int] = None
    preference_type: str
    preference_value: str
    context: Optional[str] = None
    confidence: float
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    last_used: Optional[str] = None
    source_session: Optional[str] = None
    is_active: bool = True
    metadata: Optional[Dict[str, Any]] = None
    relevance_score: Optional[float] = None

    class Config:
        arbitrary_types_allowed = True

    @classmethod
    def from_dict(cls, pref_dict):
        """Create a UserPreference from a dictionary, converting datetime to string if needed."""
        for date_field in ['created_at', 'updated_at', 'last_used']:
            if date_field in pref_dict and pref_dict[date_field] is not None:
                if not isinstance(pref_dict[date_field], str):
                    pref_dict[date_field] = str(pref_dict[date_field])
        return cls(**pref_dict)

class UserPreferenceCreate(BaseModel):
    preference_type: str
    preference_value: str
    context: Optional[str] = None
    confidence: float = 0.9
    metadata: Optional[Dict[str, Any]] = None

class UserPreferenceResponse(BaseModel):
    preferences: List[UserPreference]
    count: int
    user_id: str

CHAT_CONTEXT_MODES = {"auto", "indexed", "web", "none"}
CHAT_CONTEXT_MODE_ALIASES = {
    "default": "auto",
    "crawl": "indexed",
    "crawled": "indexed",
    "indexed_only": "indexed",
    "local": "indexed",
    "off": "none",
    "disabled": "none",
}


def normalize_context_mode(mode: Optional[str]) -> str:
    normalized = (mode or "auto").strip().lower().replace("-", "_")
    normalized = CHAT_CONTEXT_MODE_ALIASES.get(normalized, normalized)
    if normalized not in CHAT_CONTEXT_MODES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Invalid context_mode. Use one of: auto, indexed, web, none."
            ),
        )
    return normalized


# Dependency to get a ChatBot instance
def get_chat_bot(
    model: Optional[str] = None,
    result_limit: Optional[int] = None,
    similarity_threshold: Optional[float] = None,
    session_id: Optional[str] = None,
    user_id: Optional[str] = None,
    profile: str = "default",
):
    try:
        return ChatBot(
            model=model,
            result_limit=result_limit,
            similarity_threshold=similarity_threshold,
            session_id=session_id,
            user_id=user_id,
            profile=profile,
            verbose=False  # Always use quiet mode for API
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error initializing ChatBot: {str(e)}"
        )

@router.post("", response_model=ChatResponse)
async def chat(
    chat_request: ChatRequest = Body(...),
    model: Optional[str] = Query(None, description="The model to use for chat"),
    result_limit: Optional[int] = Query(None, description="Maximum number of search results"),
    similarity_threshold: Optional[float] = Query(None, description="Similarity threshold (0-1)"),
    include_context: bool = Query(True, description="When true, run vector search for RAG context (skipped for greetings)"),
    context_mode: str = Query(
        "auto",
        description=(
            "Context source routing: auto uses indexed crawls plus configured web fallback; "
            "indexed uses only crawled content; web forces Brave web context; none disables all context."
        ),
    ),
    include_history: bool = Query(False, description="Include conversation history in the response"),
):
    """
    Send a message to the chat bot and get a response.

    - **message**: The user's message
    - **session_id**: Session ID for persistent conversations
    - **user_id**: User ID for tracking conversations
    - **profile**: Profile to use
    """
    t0 = time.perf_counter()
    brave_used = False
    brave_chars = 0
    brave_sources: Optional[List[Dict[str, Any]]] = None
    brave_preview: Optional[str] = None
    try:
        context_mode = normalize_context_mode(context_mode)
        use_indexed_context = include_context and context_mode != "none"
        allow_brave_context = context_mode in {"auto", "web"}
        force_brave_context = context_mode == "web"

        # Generate a session ID if not provided
        session_id = chat_request.session_id or str(uuid.uuid4())

        # Initialize ChatBot
        chat_bot = get_chat_bot(
            model=model,
            result_limit=result_limit,
            similarity_threshold=similarity_threshold,
            session_id=session_id,
            user_id=chat_request.user_id,
            profile=chat_request.profile or "default"
        )

        # First message in a session should be about crawled sites, not random topics
        is_first_message = False
        try:
            chat_bot.load_conversation_history()
            is_first_message = len(chat_bot.conversation_history) <= 1  # Only the system message or empty
        except Exception as history_error:
            logger.warning("load_conversation_history: %s", history_error)
            is_first_message = True

        is_greeting = chat_bot.should_skip_crawl_rag_for_message(chat_request.message)
        is_inventory_query = is_local_inventory_query(chat_request.message)

        # For true greetings, skip retrieval. Otherwise pull RAG context so we can echo it
        # in the response payload (the main prompt path inside get_response() also retrieves).
        context = None
        if use_indexed_context and not is_greeting and not is_inventory_query:
            try:
                context = chat_bot.search_for_context(chat_request.message)
            except Exception as search_error:
                logger.exception("search_for_context failed: %s", search_error)
                context = None

        # Modify the system prompt for the first message to focus on crawled sites
        if use_indexed_context and is_first_message and not is_greeting and not is_inventory_query:
            # Get all available sites to mention in the greeting
            try:
                sites = chat_bot.crawler.db_client.get_all_sites()
                site_names = [site.get("name", "Unknown") for site in sites]

                if site_names:
                    sites_str = ", ".join(site_names)
                    chat_bot.add_system_message(
                        f"This is the first message in the conversation. You are a helpful assistant that specializes in providing information about the user's crawled sites: {sites_str}. "
                        f"Your primary purpose is to help the user find and understand information from their crawled content. "
                        f"In your greeting, focus on the user's crawled sites and how you can help them find information. "
                        f"Do not mention unrelated topics like gardening, cooking, or ancient civilizations unless the user asks about them. "
                        f"Suggest that the user can ask specific questions about their crawled sites.",
                        metadata={"llm_inject": True},
                    )
            except:
                # If we can't get sites, still avoid random topics
                chat_bot.add_system_message(
                    "This is the first message in the conversation. You are a helpful assistant that specializes in providing information about the user's crawled sites. "
                    "Your primary purpose is to help the user find and understand information from their crawled content. "
                    "In your greeting, focus on the user's crawled sites and how you can help them find information. "
                    "Do not mention unrelated topics unless the user asks about them.",
                    metadata={"llm_inject": True},
                )

        # The strong "prioritize crawled sites" instruction is now injected inside
        # ChatBot._prepare_messages_for_llm so the CLI and API grounded the same way.

        # Optional Brave Search LLM Context (web grounding) — BRAVE_API_KEY + BRAVE_WEB_CONTEXT
        if allow_brave_context and not is_greeting and not is_inventory_query:
            try:
                brave_mode = "always" if force_brave_context else (os.getenv("BRAVE_WEB_CONTEXT") or "when_empty").strip()
                weak_thr = float(os.getenv("BRAVE_WEAK_THRESHOLD", "0.35"))
                ctx_list = context if isinstance(context, list) else None
                if should_merge_brave(
                    brave_mode,
                    ctx_list,
                    weak_threshold=weak_thr,
                    user_message=chat_request.message,
                ):
                    brave_data = fetch_llm_context(chat_request.message)
                    if brave_data:
                        g = brave_data.get("grounding") or {}
                        gen = g.get("generic") if isinstance(g, dict) else None
                        has_grounding = isinstance(gen, list) and len(gen) > 0
                        has_sources = bool(
                            isinstance(brave_data.get("sources"), dict) and brave_data["sources"]
                        )
                        if has_grounding or has_sources:
                            block = format_grounding_for_prompt(brave_data)
                            if block:
                                brave_chars = len(block)
                                ui = brave_ui_payload(block, brave_data)
                                brave_preview = ui["preview"]
                                brave_sources = ui["sources"]
                                chat_bot.add_system_message(
                                    "Supplemental web context from Brave Search (verify facts; prefer the user's crawled "
                                    "sources when both apply). Use [link text](URL) when citing URLs.\n\n"
                                    + block,
                                    metadata={"llm_inject": True, "source": "brave_web"},
                                )
                                brave_used = True
            except Exception as brave_err:
                logger.warning("Brave LLM Context skipped: %s", brave_err)

        # Get response
        try:
            response = chat_bot.get_response(
                chat_request.message,
                use_crawl_context=use_indexed_context,
            )
        except Exception as response_error:
            logger.exception("get_response failed: %s", response_error)
            response = f"I'm sorry, but I encountered an error processing your request. Error details: {str(response_error)}"

        # Prepare the response
        chat_response = {
            "response": response,
            "session_id": session_id,
            "user_id": chat_request.user_id,
            "context_mode": context_mode,
            "brave_used": brave_used,
            "brave_sources": brave_sources,
            "brave_preview": brave_preview,
        }

        # Include context in the response only if it's not a greeting
        if context and not is_greeting:
            chat_response["context"] = context

        # Include conversation history if requested
        if include_history:
            # Load conversation history
            chat_bot.load_conversation_history()

            # Convert to Message model
            messages = []
            for msg in chat_bot.conversation_history:
                messages.append(Message(
                    role=msg["role"],
                    content=msg["content"],
                    timestamp=msg.get("timestamp")
                ))

            chat_response["conversation_history"] = messages

        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        ctx_n = len(context) if isinstance(context, list) else (0 if context is None else 1)
        logger.info(
            "chat_ok session=%s user=%s profile=%s greeting=%s include_ctx=%s context_mode=%s ctx_items=%s "
            "brave=%s brave_chars=%s msg_chars=%s reply_chars=%s ms=%s",
            session_id,
            chat_request.user_id or "-",
            chat_request.profile or "default",
            is_greeting,
            include_context,
            context_mode,
            ctx_n,
            brave_used,
            brave_chars,
            len(chat_request.message or ""),
            len(response or ""),
            elapsed_ms,
        )

        return chat_response
    except Exception as e:
        logger.exception("chat_failed session=%s: %s", chat_request.session_id, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error in chat: {str(e)}"
        )

@router.get("/defaults", response_model=ChatDefaultsResponse)
async def chat_defaults():
    """
    Return server-side chat defaults from env so the web UI can initialize a
    single-user local profile without duplicating CHAT_* settings into Vite env.
    """
    return ChatDefaultsResponse(
        user_id=(os.getenv("CHAT_USER_ID") or "").strip() or None,
        profile=(os.getenv("CHAT_PROFILE") or "default").strip() or "default",
        session_id=(os.getenv("CHAT_SESSION_ID") or "").strip() or None,
    )

@router.get("/profiles", response_model=ProfileListResponse)
async def list_profiles(
    session_id: Optional[str] = Query(None, description="Session ID to get active profile"),
    user_id: Optional[str] = Query(None, description="User ID")
):
    """
    List all available profiles.

    - **session_id**: Optional session ID to get active profile
    - **user_id**: Optional user ID
    """
    try:
        # Initialize ChatBot
        chat_bot = get_chat_bot(
            session_id=session_id,
            user_id=user_id
        )

        # Get profiles
        profiles = chat_bot.profiles
        active_profile = chat_bot.current_profile

        # Convert to ProfileResponse model
        profile_list = []
        for name, profile in profiles.items():
            profile_list.append(ProfileResponse(
                name=name,
                description=profile.get("description", ""),
                is_active=(name == active_profile)
            ))

        return ProfileListResponse(
            profiles=profile_list,
            count=len(profile_list),
            active_profile=active_profile
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error listing profiles: {str(e)}"
        )

@router.post("/profiles/{profile_name}", response_model=Dict[str, Any])
async def set_profile(
    profile_name: str = Path(..., description="The name of the profile to set"),
    session_id: str = Query(..., description="Session ID"),
    user_id: Optional[str] = Query(None, description="User ID")
):
    """
    Set the active profile for a session.

    - **profile_name**: The name of the profile to set
    - **session_id**: Session ID
    - **user_id**: Optional user ID
    """
    try:
        # Initialize ChatBot with the specified profile
        chat_bot = get_chat_bot(
            session_id=session_id,
            user_id=user_id,
            profile=profile_name
        )

        # Return success response
        return {
            "success": True,
            "message": f"Profile set to {profile_name}",
            "profile": profile_name,
            "session_id": session_id
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error setting profile: {str(e)}"
        )

@router.get("/history", response_model=ConversationHistoryResponse)
async def get_conversation_history(
    session_id: str = Query(..., description="Session ID"),
    user_id: Optional[str] = Query(None, description="User ID"),
):
    """
    Get conversation history for a session.

    - **session_id**: The session ID
    - **user_id**: Optional user ID
    """
    try:
        # Initialize ChatBot
        chat_bot = get_chat_bot(session_id=session_id, user_id=user_id)

        # Load conversation history
        chat_bot.load_conversation_history()

        # Convert to Message objects
        messages = []
        for msg in chat_bot.conversation_history:
            messages.append(Message.from_dict(msg))

        return ConversationHistoryResponse(
            messages=messages,
            count=len(messages),
            session_id=session_id,
            user_id=user_id
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting conversation history: {str(e)}"
        )

@router.delete("/history", response_model=Dict[str, Any])
async def clear_conversation_history(
    session_id: str = Query(..., description="Session ID"),
    user_id: Optional[str] = Query(None, description="User ID"),
):
    """
    Clear conversation history for a session.

    - **session_id**: The session ID
    - **user_id**: Optional user ID
    """
    try:
        # Initialize ChatBot
        chat_bot = get_chat_bot(session_id=session_id, user_id=user_id)

        # Clear conversation history
        chat_bot.clear_conversation_history()

        return {
            "message": "Conversation history cleared",
            "session_id": session_id,
            "user_id": user_id
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error clearing conversation history: {str(e)}"
        )

# User Preferences Endpoints

@router.get("/preferences", response_model=UserPreferenceResponse)
async def get_user_preferences(
    user_id: str = Query(..., description="User ID"),
    min_confidence: float = Query(0.0, description="Minimum confidence score (0-1)"),
    active_only: bool = Query(True, description="Whether to return only active preferences"),
    query: Optional[str] = Query(None, description="Optional current question to rank relevant preferences"),
    limit: int = Query(50, ge=1, le=200, description="Maximum preferences to return when query ranking is used"),
):
    """
    Get preferences for a user.

    - **user_id**: The user ID
    - **min_confidence**: Minimum confidence score (0-1) for preferences to return
    - **active_only**: Whether to return only active preferences
    """
    try:
        # Initialize ChatBot
        chat_bot = get_chat_bot(user_id=user_id)

        # Get preferences
        if query:
            preferences = chat_bot.crawler.db_client.get_relevant_user_preferences(
                user_id=user_id,
                query=query,
                min_confidence=min_confidence,
                active_only=active_only,
                limit=limit,
            )
        else:
            preferences = chat_bot.crawler.db_client.get_user_preferences(
                user_id, min_confidence, active_only
            )

        # Convert to Pydantic models
        preference_models = []
        for pref in preferences:
            # Ensure is_active is a boolean
            if 'is_active' in pref:
                pref['is_active'] = bool(pref['is_active'])
            else:
                # Default to True if not present (for backward compatibility)
                pref['is_active'] = True if active_only else False

            preference_models.append(UserPreference.from_dict(pref))

        return UserPreferenceResponse(
            preferences=preference_models,
            count=len(preference_models),
            user_id=user_id
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting user preferences: {str(e)}"
        )

@router.post("/preferences", response_model=UserPreference)
async def create_user_preference(
    user_id: str = Query(..., description="User ID"),
    session_id: Optional[str] = Query(None, description="Session ID"),
    preference: UserPreferenceCreate = Body(...),
):
    """
    Create a new user preference.

    - **user_id**: The user ID
    - **session_id**: Optional session ID
    - **preference**: The preference to create
    """
    try:
        # Initialize ChatBot
        chat_bot = get_chat_bot(user_id=user_id, session_id=session_id)

        # Save the preference to the database
        preference_id = chat_bot.crawler.db_client.save_user_preference(
            user_id=user_id,
            preference_type=preference.preference_type,
            preference_value=preference.preference_value,
            context=preference.context,
            confidence=preference.confidence,
            source_session=session_id,
            metadata=preference.metadata
        )

        # Get the created preference
        created_preference = chat_bot.crawler.db_client.get_preference_by_id(preference_id)

        return UserPreference.from_dict(created_preference)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error creating user preference: {str(e)}"
        )

@router.delete("/preferences/{preference_id}", response_model=Dict[str, Any])
async def delete_user_preference(
    preference_id: int = Path(..., description="The ID of the preference to delete"),
    user_id: str = Query(..., description="User ID"),
):
    """
    Delete a user preference.

    - **preference_id**: The ID of the preference to delete
    - **user_id**: The user ID
    """
    try:
        # Initialize ChatBot
        chat_bot = get_chat_bot(user_id=user_id)

        # Get the preference to verify ownership
        preference = chat_bot.crawler.db_client.get_preference_by_id(preference_id)

        if not preference:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Preference with ID {preference_id} not found"
            )

        if preference.get("user_id") != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to delete this preference"
            )

        # Delete the preference
        success = chat_bot.crawler.db_client.delete_user_preference(preference_id)

        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to delete preference"
            )

        return {
            "message": f"Preference with ID {preference_id} deleted",
            "id": preference_id,
            "user_id": user_id
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error deleting user preference: {str(e)}"
        )

@router.put("/preferences/{preference_id}/deactivate", response_model=Dict[str, Any])
async def deactivate_user_preference(
    preference_id: int = Path(..., description="The ID of the preference to deactivate"),
    user_id: str = Query(..., description="User ID"),
):
    """
    Deactivate a user preference.

    - **preference_id**: The ID of the preference to deactivate
    - **user_id**: The user ID
    """
    try:
        # Initialize ChatBot
        chat_bot = get_chat_bot(user_id=user_id)

        # Get the preference to verify ownership
        preference = chat_bot.crawler.db_client.get_preference_by_id(preference_id)

        if not preference:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Preference with ID {preference_id} not found"
            )

        if preference.get("user_id") != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to deactivate this preference"
            )

        # Deactivate the preference
        success = chat_bot.crawler.db_client.deactivate_user_preference(preference_id)

        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to deactivate preference"
            )

        return {
            "message": f"Preference with ID {preference_id} deactivated",
            "id": preference_id,
            "user_id": user_id
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error deactivating user preference: {str(e)}"
        )

@router.put("/preferences/{preference_id}/activate", response_model=Dict[str, Any])
async def activate_user_preference(
    preference_id: int = Path(..., description="The ID of the preference to activate"),
    user_id: str = Query(..., description="User ID"),
):
    """
    Activate a user preference.

    - **preference_id**: The ID of the preference to activate
    - **user_id**: The user ID
    """
    try:
        # Initialize ChatBot
        chat_bot = get_chat_bot(user_id=user_id)

        # Get the preference to verify ownership
        preference = chat_bot.crawler.db_client.get_preference_by_id(preference_id)

        if not preference:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Preference with ID {preference_id} not found"
            )

        if preference.get("user_id") != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to activate this preference"
            )

        # Activate the preference
        success = chat_bot.crawler.db_client.activate_user_preference(preference_id)

        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to activate preference"
            )

        return {
            "message": f"Preference with ID {preference_id} activated",
            "id": preference_id,
            "user_id": user_id
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error activating user preference: {str(e)}"
        )

@router.delete("/preferences", response_model=Dict[str, Any])
async def clear_user_preferences(
    user_id: str = Query(..., description="User ID"),
):
    """
    Clear all preferences for a user.

    - **user_id**: The user ID
    """
    try:
        # Initialize ChatBot
        chat_bot = get_chat_bot(user_id=user_id)

        # Clear preferences
        success = chat_bot.crawler.db_client.clear_user_preferences(user_id)

        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to clear preferences"
            )

        return {
            "message": f"All preferences cleared for user {user_id}",
            "user_id": user_id
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error clearing user preferences: {str(e)}"
        )
