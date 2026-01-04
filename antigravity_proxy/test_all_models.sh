
#!/bin/bash

# Base URL for the proxy
PROXY_URL="http://localhost:5007/v1beta/models"

# List of models to test
MODELS=(
    "gemini-2.0-flash-exp"
    "gemini-2.5-flash"
    "gemini-exp-1206"
    "gemini-3-pro-high"
    "gemini-3-pro-low"
    "gemini-3-flash"
    "claude-sonnet-4.5"
    "claude-sonnet-4.5-thinking"
    "claude-opus-4.5-thinking"
    "gpt-oss-120b"
)

echo "Starting tests for ${#MODELS[@]} models..."
echo "----------------------------------------"

for model in "${MODELS[@]}"; do
    echo "Testing model: $model"
    
    ENDPOINT="$PROXY_URL/$model:generateContent"
    
    RESPONSE=$(curl -s -X POST -H "Content-Type: application/json" \
        -d '{
            "contents": [{
                "parts": [{
                    "text": "giới thiệu tên model của mình đi :  "
                }]
            }]
        }' \
        "$ENDPOINT")

    if [[ $RESPONSE == *"candidates"* ]]; then
        echo "✅ SUCCESS"
        # Extract text using python to be safe and clean
        echo "$RESPONSE" | python3 -c "import sys, json; print('   Response: ' + json.load(sys.stdin)['candidates'][0]['content']['parts'][0]['text'][:100] + '...')"
    else
        echo "❌ FAILED"
        echo "   Response: $RESPONSE"
    fi
    echo "----------------------------------------"
    sleep 1
done

echo "All tests completed."
