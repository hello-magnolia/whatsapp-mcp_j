"""
FastAPI REST server for WhatsApp MCP
Exposes all WhatsApp functionality as REST endpoints
"""

from fastapi import FastAPI, HTTPException, WebSocket, File, UploadFile, Query
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Dict, Any, Literal
from datetime import datetime, timedelta
from collections import Counter
import json
import os
import asyncio
import logging
from pathlib import Path

# Setup logger
logger = logging.getLogger(__name__)

from whatsapp import (
    search_contacts,
    list_messages,
    list_chats,
    get_chat,
    get_direct_chat_by_contact,
    get_contact_chats,
    get_last_interaction,
    get_message_context,
    send_message,
    send_file,
    send_audio_message,
    download_media,
    Message,
    Chat,
    Contact,
)

from claude import (
    analyze_messages as claude_analyze_messages,
    summarize_messages as claude_summarize_messages,
    extract_topics as claude_extract_topics,
    analyze_sentiment as claude_analyze_sentiment,
    extract_action_items as claude_extract_action_items,
    semantic_search as claude_semantic_search,
)

# Initialize FastAPI app
app = FastAPI(
    title="WhatsApp MCP REST API",
    description="REST API for WhatsApp messaging through MCP Server",
    version="0.1.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Change to specific origins in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================================
# Pydantic Models (Request/Response)
# ============================================================================

class ContactResponse(BaseModel):
    phone_number: str
    name: Optional[str]
    jid: str

    class Config:
        from_attributes = True


class ChatResponse(BaseModel):
    jid: str
    name: Optional[str]
    last_message_time: Optional[datetime]
    last_message: Optional[str]
    last_sender: Optional[str]
    last_is_from_me: Optional[bool]
    is_group: bool

    class Config:
        from_attributes = True


class MessageResponse(BaseModel):
    id: str
    timestamp: datetime
    sender: str
    content: str
    is_from_me: bool
    chat_jid: str
    chat_name: Optional[str]
    media_type: Optional[str]

    class Config:
        from_attributes = True


class MessageContextResponse(BaseModel):
    message: MessageResponse
    before: List[MessageResponse]
    after: List[MessageResponse]


class SendMessageRequest(BaseModel):
    recipient: str  # Phone number or JID
    text: str
    is_group: Optional[bool] = False


class SendFileRequest(BaseModel):
    recipient: str  # Phone number or JID
    file_path: str
    is_group: Optional[bool] = False


class SendAudioRequest(BaseModel):
    recipient: str  # Phone number or JID
    file_path: str
    is_group: Optional[bool] = False


class SearchContactsRequest(BaseModel):
    query: str


class ListMessagesRequest(BaseModel):
    after: Optional[str] = None
    before: Optional[str] = None
    sender_phone_number: Optional[str] = None
    chat_jid: Optional[str] = None
    query: Optional[str] = None
    limit: int = 20
    page: int = 0


class AnalyzeQueryRequest(BaseModel):
    """Request model for flexible message analysis."""
    # Time filters
    after: Optional[str] = None              # ISO-8601 datetime
    before: Optional[str] = None             # ISO-8601 datetime
    
    # Contact filters
    contact_name: Optional[str] = None       # Fuzzy match
    contact_phone: Optional[str] = None      # Exact phone number
    chat_jid: Optional[str] = None           # Exact JID
    
    # Content filters
    keywords: Optional[List[str]] = None     # Search terms
    media_only: Optional[bool] = False       # Only media messages
    
    # Analysis type
    query_type: str = "summarize"            # "summarize", "topics", "sentiment", "action_items", "custom"
    
    # Custom prompt (for query_type="custom")
    custom_query: Optional[str] = None
    
    # Context limit
    max_messages: int = 100


class AnalyzeResponse(BaseModel):
    """Response model for message analysis."""
    query_type: str
    period: str
    messages_analyzed: int
    analysis: str
    metadata: Optional[Dict[str, Any]] = None
    timestamp: datetime


class DailySummaryRequest(BaseModel):
    """Request for daily summary - shortcut for today's messages."""
    date: Optional[str] = None  # ISO-8601 date (defaults to today)
    include_media: bool = True


class ContactSummaryRequest(BaseModel):
    """Request for conversation summary with specific contact."""
    contact_jid: str
    days: int = 7  # Look back this many days
    include_media: bool = True


class SemanticSearchRequest(BaseModel):
    """Request for semantic search within messages."""
    search_query: str
    after: Optional[str] = None
    before: Optional[str] = None
    chat_jid: Optional[str] = None
    max_messages: int = 100


class ErrorResponse(BaseModel):
    error: str
    detail: Optional[str] = None


# ============================================================================
# Health & Info Endpoints
# ============================================================================

@app.get("/")
async def root():
    """API root - health check"""
    return {
        "status": "ok",
        "message": "WhatsApp MCP REST API with Claude AI Chatbot",
        "endpoints": {
            "contacts": "/contacts",
            "chats": "/chats",
            "messages": "/messages",
            "send": "/messages/send",
            "download": "/media/download/{message_id}",
            "analyze": {
                "query": "/analyze/query (POST) - Flexible message analysis",
                "daily_summary": "/analyze/daily-summary (POST) - Today's summary",
                "contact_summary": "/analyze/contact-summary/{jid} (POST) - Contact conversation",
                "semantic_search": "/analyze/search (POST) - AI-powered search"
            },
            "docs": "/docs"
        }
    }


@app.get("/health")
async def health():
    """Health check endpoint"""
    return {"status": "healthy"}


# ============================================================================
# QR Code & Authentication Endpoints
# ============================================================================

# Global store for current QR code
_current_qr_code = None
_qr_code_timestamp = None

class QRCodeRequest(BaseModel):
    """Request model for receiving QR code from bridge"""
    qr: str


class QRCodeResponse(BaseModel):
    """Response model for QR code endpoints"""
    qr: Optional[str] = None
    authenticated: bool
    timestamp: datetime
    message: str


@app.post("/api/qr", response_model=Dict[str, Any])
async def receive_qr_code(request: QRCodeRequest):
    """
    Receive QR code from WhatsApp bridge.
    Bridge posts QR codes here for frontend to display.
    """
    global _current_qr_code, _qr_code_timestamp
    _current_qr_code = request.qr
    _qr_code_timestamp = datetime.now()
    
    return {
        "success": True,
        "message": "QR code received",
        "timestamp": _qr_code_timestamp.isoformat()
    }


@app.get("/api/qr", response_model=QRCodeResponse)
async def get_qr_code():
    """
    Get current QR code for frontend to display.
    Returns the latest QR code posted by the bridge.
    """
    global _current_qr_code, _qr_code_timestamp
    
    # Check if WhatsApp is already authenticated (has existing session)
    # In a real scenario, this would check if client is connected
    authenticated = False  # TODO: Check actual WhatsApp connection status
    
    return {
        "qr": _current_qr_code,
        "authenticated": authenticated,
        "timestamp": _qr_code_timestamp or datetime.now(),
        "message": "No QR code available" if not _current_qr_code else "Scan with WhatsApp"
    }


@app.get("/api/status", response_model=Dict[str, Any])
async def get_connection_status():
    """
    Get current WhatsApp connection status.
    Used by frontend to poll for authentication completion.
    """
    # TODO: Implement actual connection status check
    # For now, this is a placeholder
    return {
        "connected": False,  # Check actual client connection
        "authenticated": False,
        "timestamp": datetime.now().isoformat(),
        "message": "Not connected - waiting for QR scan"
    }


# ============================================================================
# Contact Endpoints
# ============================================================================

@app.get("/contacts", response_model=List[ContactResponse])
async def get_contacts(q: Optional[str] = Query(None, description="Search query")):
    """
    Search for contacts.
    
    Args:
        q: Optional search query to filter contacts by name or phone number
    """
    try:
        if q:
            results = search_contacts(q)
        else:
            results = search_contacts("")
        
        return [
            ContactResponse(
                phone_number=c.phone_number,
                name=c.name,
                jid=c.jid
            )
            for c in results
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Chat Endpoints
# ============================================================================

@app.get("/chats", response_model=List[ChatResponse])
async def get_chats(
    limit: int = Query(20, description="Number of chats to return"),
    page: int = Query(0, description="Page number (0-indexed)"),
    sort: str = Query("last_active", description="Sort by 'last_active' or 'name'")
):
    """
    Get list of chats.
    
    Args:
        limit: Number of chats to return (default: 20)
        page: Page number for pagination (default: 0)
        sort: Sort by 'last_active' or 'name' (default: 'last_active')
    """
    try:
        chats = list_chats(sort_by=sort, limit=limit, page=page)
        return [
            ChatResponse(
                jid=c.jid,
                name=c.name,
                last_message_time=c.last_message_time,
                last_message=c.last_message,
                last_sender=c.last_sender,
                last_is_from_me=c.last_is_from_me,
                is_group=c.is_group
            )
            for c in chats
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/chats/{jid}", response_model=ChatResponse)
async def get_chat_detail(jid: str):
    """
    Get details of a specific chat by JID.
    
    Args:
        jid: Chat JID (e.g., '1234567890@s.whatsapp.net' or '1234567890@g.us')
    """
    try:
        chat = get_chat(jid)
        if not chat:
            raise HTTPException(status_code=404, detail="Chat not found")
        
        return ChatResponse(
            jid=chat.jid,
            name=chat.name,
            last_message_time=chat.last_message_time,
            last_message=chat.last_message,
            last_sender=chat.last_sender,
            last_is_from_me=chat.last_is_from_me,
            is_group=chat.is_group
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/chats/by-phone/{phone_number}", response_model=ChatResponse)
async def get_chat_by_phone(phone_number: str):
    """
    Get chat by phone number (direct messages only).
    
    Args:
        phone_number: Phone number (e.g., '1234567890')
    """
    try:
        chat = get_direct_chat_by_contact(phone_number)
        if not chat:
            raise HTTPException(status_code=404, detail="Chat not found for this phone number")
        
        return ChatResponse(
            jid=chat.jid,
            name=chat.name,
            last_message_time=chat.last_message_time,
            last_message=chat.last_message,
            last_sender=chat.last_sender,
            last_is_from_me=chat.last_is_from_me,
            is_group=chat.is_group
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/contacts/{phone_number}/chats", response_model=List[ChatResponse])
async def get_contact_chats_endpoint(phone_number: str):
    """
    Get all chats involving a specific contact.
    
    Args:
        phone_number: Contact's phone number
    """
    try:
        # Convert phone to JID format for database lookup
        jid = f"{phone_number}@s.whatsapp.net"
        chats = get_contact_chats(jid)
        return [
            ChatResponse(
                jid=c.jid,
                name=c.name,
                last_message_time=c.last_message_time,
                last_message=c.last_message,
                last_sender=c.last_sender,
                last_is_from_me=c.last_is_from_me,
                is_group=c.is_group
            )
            for c in chats
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get contact chats: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Message Endpoints
# ============================================================================

@app.post("/messages/search", response_model=List[MessageResponse])
async def search_messages(request: ListMessagesRequest):
    """
    Search and list messages with optional filters.
    
    Args:
        after: ISO-8601 date string for messages after this date
        before: ISO-8601 date string for messages before this date
        sender_phone_number: Filter by sender phone number
        chat_jid: Filter by chat JID
        query: Search in message content
        limit: Number of messages to return (default: 20)
        page: Page number (default: 0)
    """
    try:
        messages = list_messages(
            after=request.after,
            before=request.before,
            sender_phone_number=request.sender_phone_number,
            chat_jid=request.chat_jid,
            query=request.query,
            limit=request.limit,
            page=request.page
        )
        
        return [
            MessageResponse(
                id=m.id,
                timestamp=m.timestamp,
                sender=m.sender,
                content=m.content,
                is_from_me=m.is_from_me,
                chat_jid=m.chat_jid,
                chat_name=m.chat_name,
                media_type=m.media_type
            )
            for m in messages
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/chats/{jid}/messages", response_model=List[MessageResponse])
async def get_chat_messages(
    jid: str,
    limit: int = Query(20, description="Number of messages to return"),
    page: int = Query(0, description="Page number")
):
    """
    Get messages from a specific chat.
    
    Args:
        jid: Chat JID
        limit: Number of messages (default: 20)
        page: Page number (default: 0)
    """
    try:
        messages = list_messages(
            chat_jid=jid,
            limit=limit,
            page=page,
            include_context=False,  # Disable context to avoid performance issues
            return_raw=True  # Return raw Message objects
        )
        
        return [
            MessageResponse(
                id=m.id,
                timestamp=m.timestamp,
                sender=m.sender,
                content=m.content,
                is_from_me=m.is_from_me,
                chat_jid=m.chat_jid,
                chat_name=m.chat_name,
                media_type=m.media_type
            )
            for m in messages
        ]
    except Exception as e:
        import traceback
        print(f"Error fetching messages: {str(e)}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Failed to fetch messages: {str(e)}")


@app.get("/messages/{message_id}/context", response_model=MessageContextResponse)
async def get_message_context_endpoint(
    message_id: str,
    before: int = Query(5, description="Messages before"),
    after: int = Query(5, description="Messages after")
):
    """
    Get a message with context (messages before and after).
    
    Args:
        message_id: Message ID
        before: Number of messages before (default: 5)
        after: Number of messages after (default: 5)
    """
    try:
        context = get_message_context(message_id, context_before=before, context_after=after)
        if not context:
            raise HTTPException(status_code=404, detail="Message not found")
        
        return MessageContextResponse(
            message=MessageResponse(
                id=context.message.id,
                timestamp=context.message.timestamp,
                sender=context.message.sender,
                content=context.message.content,
                is_from_me=context.message.is_from_me,
                chat_jid=context.message.chat_jid,
                chat_name=context.message.chat_name,
                media_type=context.message.media_type
            ),
            before=[
                MessageResponse(
                    id=m.id,
                    timestamp=m.timestamp,
                    sender=m.sender,
                    content=m.content,
                    is_from_me=m.is_from_me,
                    chat_jid=m.chat_jid,
                    chat_name=m.chat_name,
                    media_type=m.media_type
                )
                for m in context.before
            ],
            after=[
                MessageResponse(
                    id=m.id,
                    timestamp=m.timestamp,
                    sender=m.sender,
                    content=m.content,
                    is_from_me=m.is_from_me,
                    chat_jid=m.chat_jid,
                    chat_name=m.chat_name,
                    media_type=m.media_type
                )
                for m in context.after
            ]
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Send Message Endpoints
# ============================================================================

@app.post("/messages/send", response_model=Dict[str, Any])
async def send_text_message(request: SendMessageRequest):
    """
    Send a text message.
    
    Args:
        recipient: Phone number or JID of recipient
        text: Message text
        is_group: Whether recipient is a group (default: False)
    """
    try:
        if not request.text or not request.text.strip():
            raise HTTPException(status_code=400, detail="Message text cannot be empty")
        
        result = send_message(
            recipient=request.recipient,
            text=request.text,
            is_group=request.is_group
        )
        
        return {
            "success": True,
            "message": "Message sent",
            "result": result
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to send message: {str(e)}")


@app.post("/messages/send-file", response_model=Dict[str, Any])
async def send_file_message(request: SendFileRequest):
    """
    Send a file (image, video, document).
    
    Args:
        recipient: Phone number or JID
        file_path: Path to file
        is_group: Whether recipient is a group
    """
    try:
        if not os.path.exists(request.file_path):
            raise HTTPException(status_code=400, detail=f"File not found: {request.file_path}")
        
        result = send_file(
            recipient=request.recipient,
            file_path=request.file_path,
            is_group=request.is_group
        )
        
        return {
            "success": True,
            "message": "File sent",
            "result": result
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to send file: {str(e)}")


@app.post("/messages/send-audio", response_model=Dict[str, Any])
async def send_audio_message_endpoint(request: SendAudioRequest):
    """
    Send an audio message (as voice message).
    
    Args:
        recipient: Phone number or JID
        file_path: Path to audio file
        is_group: Whether recipient is a group
    """
    try:
        if not os.path.exists(request.file_path):
            raise HTTPException(status_code=400, detail=f"File not found: {request.file_path}")
        
        result = send_audio_message(
            recipient=request.recipient,
            file_path=request.file_path,
            is_group=request.is_group
        )
        
        return {
            "success": True,
            "message": "Audio message sent",
            "result": result
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to send audio: {str(e)}")


@app.post("/messages/upload")
async def upload_and_send_file(
    recipient: str = Query(..., description="Phone number or JID"),
    file: UploadFile = File(...),
    is_group: bool = Query(False, description="Is group chat")
):
    """
    Upload and send a file directly.
    
    Args:
        recipient: Phone number or JID
        file: File to upload and send
        is_group: Whether recipient is a group
    """
    try:
        # Create temp directory for uploads
        temp_dir = Path("/tmp/whatsapp-api-uploads")
        temp_dir.mkdir(exist_ok=True)
        
        # Save uploaded file
        file_path = temp_dir / file.filename
        with open(file_path, "wb") as f:
            content = await file.read()
            f.write(content)
        
        # Send file
        result = send_file(
            recipient=recipient,
            file_path=str(file_path),
            is_group=is_group
        )
        
        # Clean up
        try:
            os.remove(file_path)
        except:
            pass
        
        return {
            "success": True,
            "message": "File sent",
            "filename": file.filename,
            "result": result
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to send file: {str(e)}")


# ============================================================================
# Media Download Endpoints
# ============================================================================

@app.get("/media/download/{message_id}")
async def download_media_endpoint(message_id: str, chat_jid: str = Query(..., description="Chat JID")):
    """
    Download media from a message.
    
    Args:
        message_id: Message ID containing media
        chat_jid: Chat JID containing the message
    """
    try:
        file_path = download_media(message_id, chat_jid)
        if not file_path or not os.path.exists(file_path):
            raise HTTPException(status_code=404, detail="Media not found or already deleted")
        
        return FileResponse(
            path=file_path,
            media_type="application/octet-stream",
            filename=os.path.basename(file_path)
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to download media: {str(e)}")


# ============================================================================
# Claude AI Analysis Endpoints (Chatbot Features)
# ============================================================================

@app.post("/analyze/query", response_model=AnalyzeResponse)
async def analyze_query(request: AnalyzeQueryRequest):
    """
    Flexible message analysis endpoint.
    Retrieve messages based on filters and analyze with Claude AI.
    
    Args:
        after: ISO-8601 datetime for messages after this time
        before: ISO-8601 datetime for messages before this time
        contact_name: Fuzzy match contact name
        contact_phone: Exact phone number filter
        chat_jid: Exact JID filter
        keywords: List of keywords to search
        media_only: Only include messages with media
        query_type: "summarize", "topics", "sentiment", "action_items", or "custom"
        custom_query: Custom analysis prompt (required if query_type="custom")
        max_messages: Maximum messages to retrieve
    
    Returns:
        Analysis result with Claude AI insights
    """
    try:
        # Build query parameters
        after = request.after
        before = request.before
        
        # If neither date is provided, set reasonable defaults
        if not before:
            before = datetime.now().isoformat()
        if not after and not before:
            after = (datetime.now() - timedelta(days=7)).isoformat()
        
        # Retrieve messages based on filters
        messages = list_messages(
            after=after,
            before=before,
            chat_jid=request.chat_jid,
            query=" ".join(request.keywords) if request.keywords else None,
            limit=request.max_messages,
            page=0,
            include_context=False,
            return_raw=True
        )
        
        # Filter by contact if specified
        if request.contact_phone:
            messages = [m for m in messages if request.contact_phone in m.sender]
        
        if request.contact_name:
            messages = [m for m in messages if request.contact_name.lower() in (m.chat_name or "").lower()]
        
        if request.media_only:
            messages = [m for m in messages if m.media_type]
        
        # Determine time period description
        if after and before:
            after_dt = datetime.fromisoformat(after) if isinstance(after, str) else after
            before_dt = datetime.fromisoformat(before) if isinstance(before, str) else before
            period = f"{after_dt.strftime('%Y-%m-%d')} to {before_dt.strftime('%Y-%m-%d')}"
        else:
            period = "recent messages"
        
        # Perform analysis based on query_type
        if request.query_type == "summarize":
            result = claude_summarize_messages(messages, period)
        elif request.query_type == "topics":
            result = claude_extract_topics(messages, period)
        elif request.query_type == "sentiment":
            result = claude_analyze_sentiment(messages, period)
        elif request.query_type == "action_items":
            result = claude_extract_action_items(messages, period)
        elif request.query_type == "custom":
            if not request.custom_query:
                raise HTTPException(status_code=400, detail="custom_query required when query_type='custom'")
            result = claude_analyze_messages(messages, request.custom_query, period)
        else:
            raise HTTPException(status_code=400, detail=f"Unknown query_type: {request.query_type}")
        
        # Format response
        return AnalyzeResponse(
            query_type=request.query_type,
            period=period,
            messages_analyzed=len(messages),
            analysis=result.get("analysis", ""),
            metadata=result.get("metadata"),
            timestamp=datetime.now()
        )
        
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")


@app.post("/analyze/daily-summary", response_model=AnalyzeResponse)
async def daily_summary(request: DailySummaryRequest):
    """
    Get a summary of all messages from a specific day.
    
    Args:
        date: ISO-8601 date (defaults to today)
        include_media: Whether to include media messages
    
    Returns:
        Daily summary with Claude AI insights
    """
    try:
        # Determine the date
        if request.date:
            try:
                target_date = datetime.fromisoformat(request.date)
            except ValueError:
                # Try parsing as date only (YYYY-MM-DD)
                target_date = datetime.strptime(request.date, "%Y-%m-%d")
        else:
            target_date = datetime.now()
        
        # Set time range for the entire day
        after = target_date.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        before = target_date.replace(hour=23, minute=59, second=59, microsecond=999999).isoformat()
        
        # Retrieve messages
        messages = list_messages(
            after=after,
            before=before,
            limit=200,
            page=0,
            include_context=False,
            return_raw=True
        )
        
        if not request.include_media:
            messages = [m for m in messages if not m.media_type]
        
        # Summarize
        period = target_date.strftime("%Y-%m-%d")
        
        # Handle empty messages
        if not messages:
            analysis = f"No messages found for {period}. Start chatting to see a daily digest!"
        else:
            try:
                result = claude_summarize_messages(messages, period)
                analysis = result.get("analysis", "No analysis available")
            except Exception as claude_error:
                # If Claude fails (e.g., no API key), provide a basic summary
                print(f"Claude analysis failed: {str(claude_error)}")
                analysis = f"Analyzed {len(messages)} messages for {period}. Configure Claude API key for detailed AI insights."
        
        return AnalyzeResponse(
            query_type="daily_summary",
            period=period,
            messages_analyzed=len(messages),
            analysis=analysis,
            metadata={
                "include_media": request.include_media,
                "message_count": len(messages)
            },
            timestamp=datetime.now()
        )
        
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        print(f"Error in daily_summary: {str(e)}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Daily summary failed: {str(e)}")


@app.post("/analyze/contact-summary/{jid}", response_model=AnalyzeResponse)
async def contact_summary(
    jid: str,
    days: int = Query(7, description="Number of days to look back"),
    include_media: bool = Query(True, description="Include media messages")
):
    """
    Get a summary of conversation with a specific contact.
    
    Args:
        jid: Contact JID
        days: Number of days to look back (default: 7)
        include_media: Whether to include media messages
    
    Returns:
        Conversation summary with Claude AI insights
    """
    try:
        # Set time range
        before = datetime.now().isoformat()
        after = (datetime.now() - timedelta(days=days)).isoformat()
        
        # Retrieve messages from this contact
        messages = list_messages(
            after=after,
            before=before,
            chat_jid=jid,
            limit=200,
            page=0,
            include_context=False,
            return_raw=True
        )
        
        if not include_media:
            messages = [m for m in messages if not m.media_type]
        
        # Summarize
        period = f"last {days} days"
        result = claude_summarize_messages(messages, period)
        
        # Get contact name if available
        contact_name = messages[0].chat_name if messages and messages[0].chat_name else jid
        
        return AnalyzeResponse(
            query_type="contact_summary",
            period=f"{contact_name}: {period}",
            messages_analyzed=len(messages),
            analysis=result.get("analysis", ""),
            metadata={
                "contact_jid": jid,
                "contact_name": contact_name,
                "days_lookback": days,
                "message_count": len(messages)
            },
            timestamp=datetime.now()
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Contact summary failed: {str(e)}")


@app.post("/analyze/search", response_model=Dict[str, Any])
async def semantic_search_endpoint(request: SemanticSearchRequest):
    """
    Semantic search within messages using Claude AI.
    Find messages relevant to a query concept (not just keyword match).
    
    Args:
        search_query: What to search for (e.g., "meetings", "decisions", "problems")
        after: Optional start date (ISO-8601)
        before: Optional end date (ISO-8601)
        chat_jid: Optional filter by chat
        max_messages: Maximum messages to search (default: 100)
    
    Returns:
        Semantic search results with Claude's interpretation
    """
    try:
        # Retrieve messages
        messages = list_messages(
            after=request.after,
            before=request.before,
            chat_jid=request.chat_jid,
            limit=request.max_messages,
            page=0,
            include_context=False,
            return_raw=True
        )
        
        if not messages:
            return {
                "search_query": request.search_query,
                "results": "No messages found for the specified criteria.",
                "message_count": 0,
                "period": "no messages"
            }
        
        # Determine period
        if request.after and request.before:
            try:
                after_dt = datetime.fromisoformat(request.after)
                before_dt = datetime.fromisoformat(request.before)
                period = f"{after_dt.strftime('%Y-%m-%d')} to {before_dt.strftime('%Y-%m-%d')}"
            except:
                period = "recent messages"
        else:
            period = "recent messages"
        
        # Perform semantic search
        result = claude_semantic_search(messages, request.search_query, period)
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Semantic search failed: {str(e)}")


# ============================================================================
# WebSocket Endpoints (Real-time updates)
# ============================================================================

# In-memory store of connected clients
connected_clients = set()


@app.websocket("/ws/messages")
async def websocket_messages(websocket: WebSocket):
    """
    WebSocket endpoint for real-time message updates.
    
    Sends updates when new messages arrive or existing messages change.
    """
    await websocket.accept()
    connected_clients.add(websocket)
    
    try:
        # Keep connection alive and listen for messages
        while True:
            # Receive any message from client (for keepalive or subscriptions)
            data = await websocket.receive_text()
            # Echo back or process subscription
            await websocket.send_text(json.dumps({"type": "pong"}))
    except Exception as e:
        print(f"WebSocket error: {e}")
    finally:
        connected_clients.discard(websocket)


async def broadcast_message(message_data: Dict[str, Any]):
    """
    Broadcast a message to all connected WebSocket clients.
    Called when a new message arrives.
    """
    for client in connected_clients:
        try:
            await client.send_text(json.dumps({
                "type": "message",
                "data": message_data
            }))
        except Exception as e:
            print(f"Failed to broadcast to client: {e}")


# ============================================================================
# Run the server
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info"
    )
