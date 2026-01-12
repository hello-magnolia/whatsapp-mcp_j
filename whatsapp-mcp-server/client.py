"""
WhatsApp MCP API Client Library
Convenient Python client for the FastAPI REST server
"""

import requests
import json
from typing import List, Dict, Optional, Any
from dataclasses import dataclass
from datetime import datetime
import asyncio
import websockets


@dataclass
class Message:
    id: str
    timestamp: str
    sender: str
    content: str
    is_from_me: bool
    chat_jid: str
    chat_name: Optional[str] = None
    media_type: Optional[str] = None


@dataclass
class Chat:
    jid: str
    name: Optional[str]
    last_message_time: Optional[str]
    last_message: Optional[str]
    last_sender: Optional[str]
    last_is_from_me: Optional[bool]
    is_group: bool


@dataclass
class Contact:
    phone_number: str
    name: Optional[str]
    jid: str


class WhatsAppAPIClient:
    """Client for WhatsApp MCP FastAPI Server"""

    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url.rstrip('/')
        self.session = requests.Session()

    def _request(self, method: str, endpoint: str, **kwargs) -> Dict[str, Any]:
        """Make HTTP request to API"""
        url = f"{self.base_url}{endpoint}"
        response = self.session.request(method, url, **kwargs)
        response.raise_for_status()
        
        try:
            return response.json()
        except:
            return {"status": "ok"}

    def health(self) -> bool:
        """Check API health"""
        try:
            response = self._request("GET", "/health")
            return response.get("status") == "healthy"
        except:
            return False

    # =====================================================================
    # CONTACTS
    # =====================================================================

    def search_contacts(self, query: str) -> List[Contact]:
        """Search contacts by name or phone"""
        data = self._request("GET", f"/contacts?q={query}")
        return [Contact(**c) for c in data]

    # =====================================================================
    # CHATS
    # =====================================================================

    def list_chats(self, limit: int = 20, page: int = 0, sort: str = "last_active") -> List[Chat]:
        """Get list of chats"""
        data = self._request("GET", f"/chats?limit={limit}&page={page}&sort={sort}")
        return [Chat(**c) for c in data]

    def get_chat(self, jid: str) -> Optional[Chat]:
        """Get specific chat by JID"""
        try:
            data = self._request("GET", f"/chats/{jid}")
            return Chat(**data)
        except:
            return None

    def get_chat_by_phone(self, phone_number: str) -> Optional[Chat]:
        """Get chat by phone number"""
        try:
            data = self._request("GET", f"/chats/by-phone/{phone_number}")
            return Chat(**data)
        except:
            return None

    def get_contact_chats(self, phone_number: str) -> List[Chat]:
        """Get all chats involving a contact"""
        data = self._request("GET", f"/contacts/{phone_number}/chats")
        return [Chat(**c) for c in data]

    # =====================================================================
    # MESSAGES
    # =====================================================================

    def search_messages(
        self,
        after: Optional[str] = None,
        before: Optional[str] = None,
        sender_phone_number: Optional[str] = None,
        chat_jid: Optional[str] = None,
        query: Optional[str] = None,
        limit: int = 20,
        page: int = 0
    ) -> List[Message]:
        """Search messages with filters"""
        payload = {
            "after": after,
            "before": before,
            "sender_phone_number": sender_phone_number,
            "chat_jid": chat_jid,
            "query": query,
            "limit": limit,
            "page": page
        }
        data = self._request("POST", "/messages/search", json=payload)
        return [Message(**m) for m in data]

    def get_chat_messages(self, jid: str, limit: int = 20, page: int = 0) -> List[Message]:
        """Get messages from specific chat"""
        data = self._request("GET", f"/chats/{jid}/messages?limit={limit}&page={page}")
        return [Message(**m) for m in data]

    def get_message_context(self, message_id: str, before: int = 5, after: int = 5) -> Dict[str, Any]:
        """Get message with surrounding context"""
        return self._request("GET", f"/messages/{message_id}/context?before={before}&after={after}")

    # =====================================================================
    # SEND MESSAGES
    # =====================================================================

    def send_message(self, recipient: str, text: str, is_group: bool = False) -> bool:
        """Send text message"""
        try:
            payload = {
                "recipient": recipient,
                "text": text,
                "is_group": is_group
            }
            response = self._request("POST", "/messages/send", json=payload)
            return response.get("success", False)
        except Exception as e:
            print(f"Error sending message: {e}")
            return False

    def send_file(self, recipient: str, file_path: str, is_group: bool = False) -> bool:
        """Send file (image, video, document)"""
        try:
            payload = {
                "recipient": recipient,
                "file_path": file_path,
                "is_group": is_group
            }
            response = self._request("POST", "/messages/send-file", json=payload)
            return response.get("success", False)
        except Exception as e:
            print(f"Error sending file: {e}")
            return False

    def send_audio(self, recipient: str, file_path: str, is_group: bool = False) -> bool:
        """Send audio as voice message"""
        try:
            payload = {
                "recipient": recipient,
                "file_path": file_path,
                "is_group": is_group
            }
            response = self._request("POST", "/messages/send-audio", json=payload)
            return response.get("success", False)
        except Exception as e:
            print(f"Error sending audio: {e}")
            return False

    def upload_and_send(self, recipient: str, file_path: str, is_group: bool = False) -> bool:
        """Upload file from disk and send"""
        try:
            with open(file_path, 'rb') as f:
                files = {'file': f}
                response = self.session.post(
                    f"{self.base_url}/messages/upload",
                    files=files,
                    params={
                        "recipient": recipient,
                        "is_group": is_group
                    }
                )
                response.raise_for_status()
                data = response.json()
                return data.get("success", False)
        except Exception as e:
            print(f"Error uploading and sending file: {e}")
            return False

    # =====================================================================
    # MEDIA DOWNLOAD
    # =====================================================================

    def download_media(self, message_id: str, output_path: str) -> bool:
        """Download media from message"""
        try:
            response = self.session.get(f"{self.base_url}/media/download/{message_id}")
            response.raise_for_status()
            with open(output_path, 'wb') as f:
                f.write(response.content)
            return True
        except Exception as e:
            print(f"Error downloading media: {e}")
            return False

    # =====================================================================
    # WEBSOCKET (Real-time)
    # =====================================================================

    async def connect_message_stream(self, callback):
        """Connect to real-time message stream
        
        Args:
            callback: Async function to call with each message
                      Will be called with message dict
        """
        ws_url = self.base_url.replace("http://", "ws://").replace("https://", "wss://")
        uri = f"{ws_url}/ws/messages"
        
        async with websockets.connect(uri) as websocket:
            try:
                while True:
                    data = await websocket.recv()
                    message = json.loads(data)
                    if message.get("type") == "message":
                        await callback(message.get("data"))
            except KeyboardInterrupt:
                print("Disconnected from message stream")

    def listen_messages(self, callback):
        """Synchronous wrapper for message stream
        
        Args:
            callback: Function to call with each message
        """
        async def async_callback(msg):
            callback(msg)

        try:
            asyncio.run(self.connect_message_stream(async_callback))
        except KeyboardInterrupt:
            print("Stopped listening")


# =========================================================================
# CONVENIENCE FUNCTIONS
# =========================================================================

def create_client(base_url: str = "http://localhost:8000") -> WhatsAppAPIClient:
    """Create API client instance"""
    return WhatsAppAPIClient(base_url)


# =========================================================================
# EXAMPLE USAGE
# =========================================================================

if __name__ == "__main__":
    # Initialize client
    client = WhatsAppAPIClient()

    # Check health
    if client.health():
        print("✓ API is healthy")
    else:
        print("✗ API is not responding")
        exit(1)

    # List chats
    print("\n📱 Recent Chats:")
    chats = client.list_chats(limit=5)
    for chat in chats:
        print(f"  - {chat.name or chat.jid}: {chat.last_message}")

    # Search contacts
    print("\n👤 Searching for 'John':")
    contacts = client.search_contacts("John")
    for contact in contacts:
        print(f"  - {contact.name}: {contact.phone_number}")

    # Get messages from first chat
    if chats:
        chat = chats[0]
        print(f"\n📧 Messages from {chat.name}:")
        messages = client.get_chat_messages(chat.jid, limit=5)
        for msg in messages:
            sender = "You" if msg.is_from_me else msg.sender
            print(f"  {sender}: {msg.content}")

    # Listen for new messages (uncomment to use)
    # print("\n🔔 Listening for new messages (Ctrl+C to stop)...")
    # def on_message(msg):
    #     print(f"New message from {msg.get('sender')}: {msg.get('content')}")
    # client.listen_messages(on_message)
