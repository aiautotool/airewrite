
import requests
import json
import os
import glob

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
                    return data['token']['access_token']
        except: pass
    return None

token = get_token()
if not token:
    print("No token found")
    exit(1)

headers = {
    "Authorization": f"Bearer {token}",
    "User-Agent": "antigravity/1.11.9 windows/amd64",
    "Content-Type": "application/json"
}

url = f"{V1_INTERNAL_BASE_URL}:fetchAvailableModels"
try:
    resp = requests.post(url, headers=headers, json={}, timeout=30)
    if resp.ok:
        models = resp.json()
        print(json.dumps(models, indent=2))
    else:
        print(f"Error: {resp.status_code} - {resp.text}")
except Exception as e:
    print(f"Ex: {e}")
