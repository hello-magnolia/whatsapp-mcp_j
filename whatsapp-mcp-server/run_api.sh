#!/bin/bash
# Quick startup script for WhatsApp MCP FastAPI Server

set -e

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${BLUE}🚀 WhatsApp MCP FastAPI Server Startup${NC}\n"

# Check if Go bridge is running
echo -e "${BLUE}Checking Go bridge status...${NC}"
if ! lsof -i :8080 > /dev/null 2>&1; then
    echo -e "${YELLOW}⚠️  Go bridge not running on port 8080${NC}"
    echo -e "${YELLOW}Start it with: cd whatsapp-bridge && go run main.go${NC}\n"
else
    echo -e "${GREEN}✓ Go bridge is running on port 8080${NC}\n"
fi

# Check if Python dependencies are installed
echo -e "${BLUE}Checking Python dependencies...${NC}"
if ! python3 -c "import fastapi" 2>/dev/null; then
    echo -e "${YELLOW}Installing dependencies...${NC}"
    pip install -e .
    echo -e "${GREEN}✓ Dependencies installed${NC}\n"
else
    echo -e "${GREEN}✓ Dependencies already installed${NC}\n"
fi

# Start the API server
echo -e "${BLUE}Starting FastAPI server...${NC}"
echo -e "${GREEN}✓ Server will be available at http://localhost:8000${NC}"
echo -e "${GREEN}✓ Interactive docs at http://localhost:8000/docs${NC}"
echo -e "${GREEN}✓ ReDoc at http://localhost:8000/redoc${NC}\n"

# Run the server with auto-reload
python3 -m uvicorn api:app --reload --host 0.0.0.0 --port 8000 --log-level info
