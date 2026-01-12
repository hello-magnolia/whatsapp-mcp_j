#!/bin/bash

# Quick Start Guide for Claude AI Chatbot REST API
# This script helps start the WhatsApp MCP server with Claude integration

set -e

echo "=================================================="
echo "WhatsApp MCP Server - Claude AI Integration"
echo "=================================================="
echo ""

# Check if ANTHROPIC_API_KEY is set
if [ -z "$ANTHROPIC_API_KEY" ]; then
    echo "⚠️  ANTHROPIC_API_KEY environment variable not set!"
    echo ""
    echo "To set it, run:"
    echo "  export ANTHROPIC_API_KEY='sk-ant-your-actual-key-here'"
    echo ""
    echo "Without this, the /analyze endpoints will fail."
    echo ""
    read -p "Continue anyway? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

echo "Starting dependencies check..."

# Check Python version
python_version=$(python3 --version 2>&1)
echo "✓ Python: $python_version"

# Check if anthropic is installed
python3 -c "import anthropic" 2>/dev/null && echo "✓ Anthropic SDK installed" || echo "✗ Anthropic SDK not installed - run: pip install anthropic"

# Check if FastAPI is installed
python3 -c "import fastapi" 2>/dev/null && echo "✓ FastAPI installed" || echo "✗ FastAPI not installed"

echo ""
echo "Starting Go WhatsApp bridge..."
echo "Make sure the Go bridge is running:"
echo "  cd whatsapp-bridge && go run main.go"
echo ""
echo "In this terminal, starting FastAPI server..."
echo ""
echo "=================================================="
echo "API Server running at: http://localhost:8000"
echo "Swagger UI: http://localhost:8000/docs"
echo "ReDoc: http://localhost:8000/redoc"
echo "=================================================="
echo ""

# Start the API server
cd "$(dirname "$0")"
python3 -m uvicorn api:app --host 0.0.0.0 --port 8000 --reload
