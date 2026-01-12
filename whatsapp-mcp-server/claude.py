"""
Claude AI integration for WhatsApp message analysis.
Uses Anthropic API to generate insights from messages.
"""

import os
from typing import List, Optional, Dict, Any
from anthropic import Anthropic
from datetime import datetime
from whatsapp import Message


class ClaudeAnalyzer:
    """Wrapper around Anthropic API for message analysis."""
    
    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        """Initialize Claude client with API key from environment or parameter."""
        key = api_key or os.getenv("ANTHROPIC_API_KEY")
        if not key:
            raise ValueError("ANTHROPIC_API_KEY environment variable not set")
        self.client = Anthropic(api_key=key)
        # Use model from parameter, environment variable, or default
        self.model = model or os.getenv("CLAUDE_MODEL", "claude-opus-4-1-20250805")
        self.max_tokens = 1024
    
    def _format_messages_for_claude(self, messages: List[Message]) -> str:
        """Format a list of Message objects into readable text for Claude."""
        if not messages:
            return "No messages found."
        
        formatted = []
        for msg in messages:
            sender = "You" if msg.is_from_me else (msg.chat_name or msg.sender)
            timestamp = msg.timestamp.strftime("%Y-%m-%d %H:%M:%S")
            
            # Handle media messages
            if msg.media_type:
                content = f"[{msg.media_type.upper()} message]"
                if msg.content:
                    content += f": {msg.content}"
            else:
                content = msg.content or "[No content]"
            
            formatted.append(f"[{timestamp}] {sender}: {content}")
        
        return "\n".join(formatted)
    
    def analyze_messages(
        self,
        messages: List[Message],
        query: str,
        period: str = "specified period"
    ) -> Dict[str, Any]:
        """
        Analyze messages with a custom query.
        
        Args:
            messages: List of Message objects to analyze
            query: Custom analysis query/prompt
            period: Time period description for context
        
        Returns:
            Dictionary with analysis results
        """
        if not messages:
            return {
                "analysis": "No messages found for the specified criteria.",
                "message_count": 0,
                "period": period
            }
        
        formatted_messages = self._format_messages_for_claude(messages)
        
        prompt = f"""Analyze the following WhatsApp messages from {period}:

{formatted_messages}

{query}

Please provide a clear, concise analysis."""
        
        response = self.client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            messages=[{
                "role": "user",
                "content": prompt
            }]
        )
        
        analysis_text = response.content[0].text
        
        return {
            "analysis": analysis_text,
            "message_count": len(messages),
            "period": period,
            "timestamp": datetime.now().isoformat()
        }
    
    def summarize_messages(
        self,
        messages: List[Message],
        period: str = "specified period"
    ) -> Dict[str, Any]:
        """
        Summarize conversation messages.
        
        Args:
            messages: List of Message objects to summarize
            period: Time period description
        
        Returns:
            Dictionary with summary and metadata
        """
        query = """Provide a concise summary of these messages including:
- Key topics discussed
- Important decisions or agreements
- Action items (if any)
- Overall sentiment of the conversation"""
        
        return self.analyze_messages(messages, query, period)
    
    def extract_topics(
        self,
        messages: List[Message],
        period: str = "specified period"
    ) -> Dict[str, Any]:
        """
        Extract main topics from conversation.
        
        Args:
            messages: List of Message objects
            period: Time period description
        
        Returns:
            Dictionary with topics and metadata
        """
        query = """Extract the main topics discussed in these messages. 
For each topic, provide a brief description and context.
Format as a numbered list."""
        
        result = self.analyze_messages(messages, query, period)
        result["analysis_type"] = "topics"
        return result
    
    def analyze_sentiment(
        self,
        messages: List[Message],
        period: str = "specified period"
    ) -> Dict[str, Any]:
        """
        Analyze sentiment of conversation.
        
        Args:
            messages: List of Message objects
            period: Time period description
        
        Returns:
            Dictionary with sentiment analysis
        """
        query = """Analyze the overall sentiment of this conversation:
- What is the dominant emotion/tone?
- Are there any significant mood shifts?
- Any conflicts or positive interactions?
Provide a detailed but concise analysis."""
        
        result = self.analyze_messages(messages, query, period)
        result["analysis_type"] = "sentiment"
        return result
    
    def extract_action_items(
        self,
        messages: List[Message],
        period: str = "specified period"
    ) -> Dict[str, Any]:
        """
        Extract action items from conversation.
        
        Args:
            messages: List of Message objects
            period: Time period description
        
        Returns:
            Dictionary with action items
        """
        query = """Extract any action items, tasks, or to-dos mentioned in these messages:
- What needs to be done?
- Who is responsible? (if mentioned)
- Any deadlines mentioned?
Format as a numbered checklist."""
        
        result = self.analyze_messages(messages, query, period)
        result["analysis_type"] = "action_items"
        return result
    
    def semantic_search(
        self,
        messages: List[Message],
        search_query: str,
        period: str = "specified period"
    ) -> Dict[str, Any]:
        """
        Semantically search messages for relevance to a query.
        
        Args:
            messages: List of Message objects to search
            search_query: What to search for (e.g., "meetings", "decisions")
            period: Time period description
        
        Returns:
            Dictionary with relevant messages and analysis
        """
        if not messages:
            return {
                "search_query": search_query,
                "relevant_messages": [],
                "summary": "No messages found for the specified criteria.",
                "message_count": 0,
                "period": period
            }
        
        formatted_messages = self._format_messages_for_claude(messages)
        
        prompt = f"""From the following WhatsApp messages from {period}, identify and summarize 
the messages most relevant to: "{search_query}"

{formatted_messages}

Provide:
1. Summary of relevant content
2. Any key quotes or important information
3. Overall relevance assessment"""
        
        response = self.client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            messages=[{
                "role": "user",
                "content": prompt
            }]
        )
        
        return {
            "search_query": search_query,
            "results": response.content[0].text,
            "message_count": len(messages),
            "period": period,
            "timestamp": datetime.now().isoformat()
        }


# Convenience functions for use in api.py
def analyze_messages(
    messages: List[Message],
    query: str,
    period: str = "specified period"
) -> Dict[str, Any]:
    """Convenience function to analyze messages."""
    analyzer = ClaudeAnalyzer()
    return analyzer.analyze_messages(messages, query, period)


def summarize_messages(
    messages: List[Message],
    period: str = "specified period"
) -> Dict[str, Any]:
    """Convenience function to summarize messages."""
    analyzer = ClaudeAnalyzer()
    return analyzer.summarize_messages(messages, period)


def extract_topics(
    messages: List[Message],
    period: str = "specified period"
) -> Dict[str, Any]:
    """Convenience function to extract topics."""
    analyzer = ClaudeAnalyzer()
    return analyzer.extract_topics(messages, period)


def analyze_sentiment(
    messages: List[Message],
    period: str = "specified period"
) -> Dict[str, Any]:
    """Convenience function to analyze sentiment."""
    analyzer = ClaudeAnalyzer()
    return analyzer.analyze_sentiment(messages, period)


def extract_action_items(
    messages: List[Message],
    period: str = "specified period"
) -> Dict[str, Any]:
    """Convenience function to extract action items."""
    analyzer = ClaudeAnalyzer()
    return analyzer.extract_action_items(messages, period)


def semantic_search(
    messages: List[Message],
    search_query: str,
    period: str = "specified period"
) -> Dict[str, Any]:
    """Convenience function for semantic search."""
    analyzer = ClaudeAnalyzer()
    return analyzer.semantic_search(messages, search_query, period)
