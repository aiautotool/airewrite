
import requests
import json
import os
import glob
import uuid

ACCOUNTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "accounts")
V1_INTERNAL_BASE_URL = "https://cloudcode-pa.googleapis.com/v1internal"

def get_token():
    if not os.path.exists(ACCOUNTS_DIR): return None
    files = glob.glob(os.path.join(ACCOUNTS_DIR, "*.json"))
    for f in files:
        try:
            with open(f, 'r') as fp:
                data = json.load(fp)
                if 'token' in data:
                    return data['token']['access_token'], data['token']['project_id']
        except: pass
    return None, None

token, project_id = get_token()
if not token:
    print("No token found")
    exit(1)

headers = {
    "Authorization": f"Bearer {token}",
    "User-Agent": "antigravity/1.11.9 windows/amd64",
    "Content-Type": "application/json"
}

def test_endpoint(method, model_name, request_type, body_field="request"):
    url = f"{V1_INTERNAL_BASE_URL}:{method}"
    print(f"\n--- Testing {method} with model {model_name} (type: {request_type}) ---")
    
    inner_request = {
        "contents": [{"parts": [{"text": "A futuristic city"}]}],
        "generationConfig": {
            "imageConfig": {
                "aspectRatio": "1:1"
            }
        }
    }
    
    payload = {
        "project": project_id,
        "requestId": f"agent-{uuid.uuid4()}",
        "model": model_name,
        "userAgent": "antigravity",
        "requestType": request_type
    }
    payload[body_field] = inner_request
    
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=30)
        print(f"Status: {resp.status_code}")
        if resp.ok:
            print(f"Success! Response: {resp.text[:500]}")
        else:
            print(f"Error: {resp.text}")
    except Exception as e:
        print(f"Ex: {e}")

# 1. Try generateContent (Standard for v1internal)
test_endpoint("generateContent", "gemini-3-pro-image", "image_gen")

# 2. Try with models/ prefix
test_endpoint("generateContent", "models/gemini-3-pro-image", "image_gen")

# 3. Try with requestType: agent
test_endpoint("generateContent", "gemini-3-pro-image", "agent")

# 4. Try predict (just in case)
test_endpoint("predict", "gemini-3-pro-image", "image_gen")
