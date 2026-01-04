
import requests
import json
import base64
import os
import glob

ACCOUNTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "accounts")
V1_INTERNAL_BASE_URL = "https://cloudcode-pa.googleapis.com/v1internal"

def get_token():
    if not os.path.exists(ACCOUNTS_DIR):
        print(f"Accounts dir {ACCOUNTS_DIR} does not exist")
        return None, None
    files = glob.glob(os.path.join(ACCOUNTS_DIR, "*.json"))
    for f in files:
        try:
            with open(f, 'r') as fp:
                data = json.load(fp)
                if 'token' in data:
                    token_data = data['token']
                    access_token = token_data.get('access_token')
                    project_id = token_data.get('project_id')
                    if access_token and project_id:
                        print(f"Using account {data.get('email', 'unknown')}, project {project_id}")
                        return access_token, project_id
        except Exception as e:
            print(f"Error reading {f}: {e}")
    return None, None

def probe_edit():
    token, project_id = get_token()
    if not token: exit(1)

    image_path = "test_image.jpg"
    if not os.path.exists(image_path):
        print("Run test_image_gen.py first")
        return

    with open(image_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode('utf-8')

    headers = {
        "Authorization": f"Bearer {token}",
        "User-Agent": "antigravity/1.11.9 windows/amd64",
        "Content-Type": "application/json"
    }

    url = f"{V1_INTERNAL_BASE_URL}:generateContent"
    
    # Try different structures for edit
    # Attempt 1: Just include parts
    payload = {
        "project": project_id,
        "requestId": "probe-edit-1",
        "request": {
            "contents": [{
                "parts": [
                    {"inlineData": {"data": b64, "mimeType": "image/jpeg"}},
                    {"text": "Make the apple blue"}
                ]
            }],
            "generationConfig": {
                "imageConfig": {
                    "aspectRatio": "1:1"
                }
            }
        },
        "model": "gemini-3-pro-image",
        "userAgent": "antigravity",
        "requestType": "image_gen"
    }

    print("--- Attempt 1: Multi-part parts ---")
    resp = requests.post(url, headers=headers, json=payload, timeout=60)
    print(f"Status: {resp.status_code}")
    if resp.ok:
        print("Success! Response contains 'response'?" , "response" in resp.json())
        with open("probe_edit_res.json", "w") as f:
            json.dump(resp.json(), f, indent=2)
    else:
        print(resp.text)

if __name__ == "__main__":
    probe_edit()
