import os
import json
import glob
import requests

ACCOUNTS_DIR = os.path.expanduser("~/.antigravity_tools/accounts")
V1_INTERNAL_BASE_URL = "https://cloudcode-pa.googleapis.com/v1internal"

def load_accounts():
    accounts = []
    if not os.path.exists(ACCOUNTS_DIR):
        print("No accounts dir")
        return []
    files = glob.glob(os.path.join(ACCOUNTS_DIR, "*.json"))
    for f in files:
        try:
            with open(f, 'r') as fp:
                data = json.load(fp)
                if 'token' in data and 'access_token' in data['token']:
                    accounts.append(data)
        except: pass
    return accounts

def test_fetch_project_id(access_token, ide_type="ANTIGRAVITY"):
    url = f"{V1_INTERNAL_BASE_URL}:loadCodeAssist"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "User-Agent": "antigravity/1.11.9 windows/amd64",
        "Content-Type": "application/json",
        "Host": "cloudcode-pa.googleapis.com"
    }
    data = {"metadata": {"ideType": ide_type}}
    try:
        resp = requests.post(url, headers=headers, json=data, timeout=10)
        print(f"[{ide_type}] Status: {resp.status_code}")
        if resp.ok:
            j = resp.json()
            print(f"[{ide_type}] Response: {json.dumps(j)}")
            return j.get('cloudaicompanionProject')
        else:
            print(f"[{ide_type}] Error: {resp.text}")
    except Exception as e:
        print(f"[{ide_type}] Exception: {e}")
    return None

accounts = load_accounts()
print(f"Found {len(accounts)} accounts.")

for acc in accounts:
    email = acc.get('email', 'unknown')
    print(f"\n--- Testing {email} ---")
    token = acc['token']['access_token']
    
    # Test 1: ANTIGRAVITY (Default)
    pid = test_fetch_project_id(token, "ANTIGRAVITY")
    if pid:
        print(f"SUCCESS: Found project_id: {pid}")
        continue
        
    # Test 2: VSCODE
    pid = test_fetch_project_id(token, "VSCODE")
    if pid:
        print(f"SUCCESS (VSCODE): Found project_id: {pid}")
        continue

    # Test 3: INTELLIJ
    pid = test_fetch_project_id(token, "INTELLIJ")
    if pid:
        print(f"SUCCESS (INTELLIJ): Found project_id: {pid}")
