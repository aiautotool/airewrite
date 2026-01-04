
import requests
import json
import os
import glob
import random

# Initial setup to get token
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

print(f"Using project: {project_id}")

headers = {
    "Authorization": f"Bearer {token}",
    "User-Agent": "antigravity/1.11.9 windows/amd64",
    "Content-Type": "application/json"
}

# 1. Try generateChat with gemini-3-pro-image (using the existing flow)
print("\n--- Test 1: generateChat with gemini-3-pro-image ---")
url = f"{V1_INTERNAL_BASE_URL}:generateChat"
body = {
    "project": project_id,
    "userMessage": "Generate an image of a futuristic city",
    "metadata": {"ideType": "ANTIGRAVITY"},
    # Maybe we need to specify model here? older tests didn't seem to pass 'model' field in generateChat body
    # But let's check if we can.
}
try:
    resp = requests.post(url, headers=headers, json=body, timeout=30)
    print(f"Status: {resp.status_code}")
    if resp.ok:
        print(f"Response: {resp.text[:500]}")
    else:
        print(f"Error: {resp.text}")
except Exception as e:
    print(f"Ex: {e}")


# 2. Try implicit 'image generation' request
print("\n--- Test 2: generateChat requesting image explicitly in prompt ---")
# Already did that above.

# 3. Try to guess an endpoint for image generation
# Common internal ones: :predict, :generateImage
potential_actions = ["generateImage", "predict", "generateImages", "imageGeneration"]
for action in potential_actions:
    print(f"\n--- Test 3.{action}: {action} ---")
    url = f"{V1_INTERNAL_BASE_URL}:{action}"
    
    # Try different bodies
    bodies = [
        # Gemini/Vertex style
        {
            "instances": [{"prompt": "A cute cat"}],
            "parameters": {"sampleCount": 1}
        },
        # Simple style
        {
            "prompt": "A cute cat",
            "n": 1,
            "size": "1024x1024"
        }
    ]
    
    for b in bodies:
        try:
            resp = requests.post(url, headers=headers, json=b, timeout=5)
            print(f"Action: {action}, Body keys: {list(b.keys())} -> Status: {resp.status_code}")
            if resp.status_code != 404:
                print(f"  Response: {resp.text[:200]}")
        except: pass

