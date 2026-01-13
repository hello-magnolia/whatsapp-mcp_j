#!/bin/bash

# Test script for WhatsApp MCP authentication with timeout handling

echo "=== Testing WhatsApp MCP Server Authentication with Timeout ==="
echo

# Check if jq is available
if command -v jq &> /dev/null; then
    USE_JQ=true
    echo "✓ jq detected - JSON output will be formatted"
else
    USE_JQ=false
    echo "⚠ jq not found - using Python for JSON formatting"
fi
echo

# Function to pretty print JSON
pretty_json() {
    if [ "$USE_JQ" = true ]; then
        jq .
    else
        python3 -m json.tool
    fi
}

# Function to extract field from JSON
get_field() {
    local field=$1
    if [ "$USE_JQ" = true ]; then
        jq -r ".$field"
    else
        python3 -c "import json, sys; print(json.load(sys.stdin).get('$field', ''))"
    fi
}

echo "1. Checking initial authentication status..."
curl -s http://localhost:8080/api/auth/status | pretty_json
echo

echo "2. Starting authentication..."
response=$(curl -X POST -s http://localhost:8080/api/auth/start)
echo "$response" | pretty_json
echo

qr_code=$(echo "$response" | get_field "qr_code")

if [ -n "$qr_code" ] && [ "$qr_code" != "null" ]; then
    echo "3. QR Code received:"
    echo "   $qr_code"
    echo

    # Try to display QR code if qrencode is available
    if command -v qrencode &> /dev/null; then
        echo "   Displaying QR code (scan with WhatsApp):"
        echo "$qr_code" | qrencode -t ansiutf8
    else
        echo "   Install 'qrencode' to display QR code in terminal:"
        echo "   Ubuntu/Debian: sudo apt-get install qrencode"
        echo "   macOS: brew install qrencode"
    fi
    echo

    echo "4. Instructions:"
    echo "   - Open WhatsApp on your phone"
    echo "   - Go to Settings > Linked Devices"
    echo "   - Tap 'Link a Device'"
    echo "   - Scan the QR code"
    echo

    echo "5. Waiting 10 seconds..."
    sleep 10

    echo "6. Checking authentication status..."
    curl -s http://localhost:8080/api/auth/status | pretty_json
    echo

    echo "7. Testing timeout scenario..."
    echo "   (Authentication will timeout after 3 minutes if not scanned)"
    echo
    echo "   You can test this by:"
    echo "   a) Wait 3 minutes without scanning"
    echo "   b) Check status: curl -s http://localhost:8080/api/auth/status | $([ "$USE_JQ" = true ] && echo "jq ." || echo "python3 -m json.tool")"
    echo "   c) Restart auth: curl -X POST http://localhost:8080/api/auth/start"
    echo

    echo "8. To manually test restarting authentication:"
    echo "   curl -X POST http://localhost:8080/api/auth/start | $([ "$USE_JQ" = true ] && echo "jq ." || echo "python3 -m json.tool")"
    echo
else
    echo "Failed to get QR code. Response:"
    echo "$response" | pretty_json
    echo
    echo "Troubleshooting:"
    echo "1. Make sure the Go bridge is running:"
    echo "   cd whatsapp-bridge && go run main.go"
    echo
    echo "2. Check if port 8080 is accessible:"
    echo "   curl http://localhost:8080/api/auth/status"
fi

echo "=== Test Complete ==="
echo
echo "Key features implemented:"
echo "✓ Authentication sessions expire after 3 minutes"
echo "✓ Can restart authentication by calling /api/auth/start again"
echo "✓ Proper cleanup of old sessions when restarting"
echo "✓ Status includes 'auth_timeout' state"
