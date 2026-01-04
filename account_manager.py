import os
import json
import glob
import time
import uuid
import requests
import random
import threading
import datetime
import traceback
from urllib.parse import urlparse

# Configuration
DATA_DIR = os.path.expanduser("~/.airewrite_data")
ACCOUNTS_DIR = os.path.join(DATA_DIR, "accounts")
V1_INTERNAL_BASE_URL = "https://cloudcode-pa.googleapis.com/v1internal"

class AccountManager:
    
    # Load config relative to this file
    _config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.json')
    _config = {}
    if os.path.exists(_config_path):
        try:
            with open(_config_path, 'r', encoding='utf-8') as f:
                _config = json.load(f)
        except Exception as e:
            print(f"Error loading config.json: {e}")

    CLIENT_ID = _config.get("google_client_id")
    CLIENT_SECRET = _config.get("google_client_secret")
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(AccountManager, cls).__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
        if self._initialized: return
        self.accounts_dir = ACCOUNTS_DIR
        self.accounts = {} # id -> account_data
        self.available_models = set()
        self.lock = threading.RLock()
        self.load_accounts()
        self._initialized = True

    def load_accounts(self):
        with self.lock:
            self.accounts = {}
            self.available_models = set()
            if not os.path.exists(self.accounts_dir):
                os.makedirs(self.accounts_dir, exist_ok=True)
                return

            files = glob.glob(os.path.join(self.accounts_dir, "*.json"))
            for f in files:
                try:
                    with open(f, 'r', encoding='utf-8') as fp:
                        data = json.load(fp)
                        if 'id' in data and 'token' in data:
                            self.accounts[data['id']] = {
                                'data': data,
                                'path': f
                            }
                            if 'quota' in data and 'models' in data['quota']:
                                for m in data['quota']['models']:
                                    if 'name' in m:
                                        self.available_models.add(m['name'])
                except Exception as e:
                    print(f"Failed to load {f}: {e}")

    def get_all_accounts(self):
        with self.lock:
            return [acc['data'] for acc in self.accounts.values()]

    def get_account(self, account_id):
        with self.lock:
            return self.accounts.get(account_id, {}).get('data')

    def delete_account(self, account_id):
        with self.lock:
            if account_id in self.accounts:
                path = self.accounts[account_id]['path']
                try:
                    if os.path.exists(path):
                        os.remove(path)
                    del self.accounts[account_id]
                    return True
                except Exception as e:
                    print(f"Failed to delete account {account_id}: {e}")
            return False

    def save_account(self, account_id):
        with self.lock:
            if account_id in self.accounts:
                acc = self.accounts[account_id]
                try:
                    with open(acc['path'], 'w', encoding='utf-8') as fp:
                        json.dump(acc['data'], fp, indent=2, ensure_ascii=False)
                except Exception as e:
                    print(f"Failed to save account {account_id}: {e}")

    def refresh_and_get(self, account_id):
        with self.lock:
            if account_id not in self.accounts:
                raise Exception("Account not found")
            acc_entry = self.accounts[account_id]
            token_data = acc_entry['data']['token']
            
        access_token = token_data.get('access_token')
        refresh_token = token_data.get('refresh_token')
        expiry_timestamp = token_data.get('expiry_timestamp', 0)
        project_id = token_data.get('project_id')
        
        now = time.time()
        
        if now >= expiry_timestamp - 300:
            new_tokens = self.perform_refresh(refresh_token)
            with self.lock:
                acc_entry = self.accounts[account_id]
                t_data = acc_entry['data']['token']
                t_data['access_token'] = new_tokens['access_token']
                t_data['expires_in'] = new_tokens['expires_in']
                t_data['expiry_timestamp'] = int(now + new_tokens['expires_in'])
                self.save_account(account_id)
                access_token = new_tokens['access_token']
        
        if not project_id:
             project_id, tier = self.fetch_project_info_network(access_token)
             with self.lock:
                 acc_entry = self.accounts[account_id]
                 acc_entry['data']['token']['project_id'] = project_id
                 if 'quota' in acc_entry['data']:
                     acc_entry['data']['quota']['subscription_tier'] = tier
                 self.save_account(account_id)
                 
        return access_token, project_id, acc_entry['data'].get('email')

    def perform_refresh(self, refresh_token):
        url = "https://oauth2.googleapis.com/token"
        data = {
            "client_id": self.CLIENT_ID,
            "client_secret": self.CLIENT_SECRET,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token"
        }
        resp = requests.post(url, data=data, timeout=20)
        if not resp.ok:
            raise Exception(f"Refresh failed: {resp.text}")
        return resp.json()

    def fetch_project_info_network(self, access_token):
        url = f"{V1_INTERNAL_BASE_URL}:loadCodeAssist"
        headers = {
            "Authorization": f"Bearer {access_token}",
            "User-Agent": "antigravity/1.11.3 Darwin/arm64",
            "Content-Type": "application/json"
        }
        for ide_type in ["ANTIGRAVITY", "VSCODE", "INTELLIJ"]:
            data = {"metadata": {"ideType": ide_type}}
            try:
                resp = requests.post(url, headers=headers, json=data, timeout=10)
                if resp.ok:
                    j = resp.json()
                    pid = j.get('cloudaicompanionProject')
                    paid_tier = j.get('paidTier', {}) if isinstance(j.get('paidTier'), dict) else {}
                    current_tier = j.get('currentTier', {}) if isinstance(j.get('currentTier'), dict) else {}
                    tier = paid_tier.get('id') or current_tier.get('id') or "free-tier"
                    if pid: return pid, tier
            except: pass
        return f"gen-project-{random.randint(1000,9999)}", "free-tier"

    def fetch_available_models_network(self, access_token, project_id):
        url = f"{V1_INTERNAL_BASE_URL}:fetchAvailableModels"
        headers = {
            "Authorization": f"Bearer {access_token}",
            "User-Agent": "antigravity/1.11.3 Darwin/arm64",
            "Content-Type": "application/json"
        }
        data = {"project": project_id}
        try:
            resp = requests.post(url, headers=headers, json=data, timeout=10)
            if resp.ok:
                models_data = resp.json().get('models', {})
                parsed_models = []
                for name, info in models_data.items():
                    quota_info = info.get('quotaInfo', {})
                    percentage = int(quota_info.get('remainingFraction', 0) * 100)
                    reset_time = quota_info.get('resetTime', "")
                    if any(x in name.lower() for x in ["gemini", "claude", "gpt"]):
                        parsed_models.append({
                            "name": name,
                            "percentage": percentage,
                            "reset_time": reset_time
                        })
                parsed_models.sort(key=lambda x: x['name'])
                return parsed_models
        except: pass
        return []

    def register_account(self, refresh_token):
        new_tokens = self.perform_refresh(refresh_token)
        access_token = new_tokens['access_token']
        email = "unknown@gmail.com"
        name = "Unknown User"
        try:
            userinfo_resp = requests.get("https://www.googleapis.com/oauth2/v3/userinfo", 
                                       headers={"Authorization": f"Bearer {access_token}"}, timeout=5)
            if userinfo_resp.ok:
                uinfo = userinfo_resp.json()
                email = uinfo.get('email', email)
                name = uinfo.get('name', name)
        except: pass
        project_id, tier = self.fetch_project_info_network(access_token)
        models = self.fetch_available_models_network(access_token, project_id)
        if not models:
            models = [{"name": "gemini-3-flash", "percentage": 100}]
        
        account_id = str(uuid.uuid4())
        now = int(time.time())
        account_data = {
            "id": account_id, "email": email, "name": name,
            "token": {
                "access_token": access_token, "refresh_token": refresh_token,
                "expires_in": new_tokens['expires_in'], "expiry_timestamp": now + new_tokens['expires_in'],
                "email": email, "project_id": project_id
            },
            "quota": {
                "models": models, "last_updated": now, "subscription_tier": tier
            },
            "created_at": now, "last_used": now
        }
        file_path = os.path.join(self.accounts_dir, f"{account_id}.json")
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(account_data, f, indent=2, ensure_ascii=False)
        self.load_accounts()
        return account_id, email

    def list_blogs(self, access_token):
        url = "https://www.googleapis.com/blogger/v3/users/self/blogs"
        headers = {"Authorization": f"Bearer {access_token}"}
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.ok:
            return resp.json().get('items', [])
        else:
            raise Exception(f"Blogger API Error {resp.status_code}: {resp.text}")

    def get_token_info(self, access_token):
        # Verify scopes
        url = f"https://oauth2.googleapis.com/tokeninfo?access_token={access_token}"
        try:
            resp = requests.get(url, timeout=10)
            if resp.ok:
                return resp.json()
        except: pass
        return {}

    def update_account_token_data(self, account_id, new_token_data):
        with self.lock:
            if account_id in self.accounts:
                acc = self.accounts[account_id]
                # Update keys
                acc['data']['token'].update(new_token_data)
                self.save_account(account_id)
                return True
        return False

    def check_blog_url_availability(self, access_token, subdomain):
        # Check if a blog subdomain is available (e.g. my-blog.blogspot.com)
        # GET https://www.googleapis.com/blogger/v3/blogs/test_url?url=...
        # Returns { "status": "AVAILABLE" | "TAKEN" }
        url = "https://www.googleapis.com/blogger/v3/blogs/test_url"
        headers = {"Authorization": f"Bearer {access_token}"}
        params = {"url": f"http://{subdomain}.blogspot.com"}
        try:
            resp = requests.get(url, headers=headers, params=params, timeout=10)
            if resp.ok:
                return resp.json() #{ "status": "AVAILABLE" }
        except Exception as e:
            print(f"Check avail error: {e}")
        return None

    def create_blog(self, access_token, title, subdomain):
        # Attempt to create a blog via API.
        # Note: 'insert' operations are restricted in Blogger v3 API and may fail.
        # Unknown/Private endpoints might be needed for guaranteed creation.
        url = "https://www.googleapis.com/blogger/v3/blogs"
        headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
        
        # We try to pass 'url' which is usually the subdomain handle.
        # Sometimes 'subdomain' is mapped to 'url' or 'host'.
        # This payload is a best-effort consistent with Google APIs.
        data = {
            "name": title,
            "description": f"New blog: {title}",
            "locale": {"language": "en", "country": "US"}
            # "url": f"http://{subdomain}.blogspot.com" # Read-only field usually
        }
        
        try:
             # Since v3 standard doesn't documented creation clearly, 
             # we might also try an internal way? 
             # But for now, standard POST.
             resp = requests.post(url, headers=headers, json=data, timeout=15)
             if resp.ok:
                 return resp.json()
             else:
                 return {"error": f"API Error {resp.status_code}: {resp.text}"}
        except Exception as e:
            return {"error": str(e)}

    def set_blog_custom_domain(self, access_token, blog_id, domain):
         url = f"https://www.googleapis.com/blogger/v3/blogs/{blog_id}"
         headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
         
         # First get the blog to preserve other fields?
         # Or PATCH if supported. Blogger v3 supports PATCH.
         # But 'customMetaData' or 'customDomain' is the key.
         # In v3, the field is 'customMetaData' (No), it is 'customDomain'.
         # It is usually:
         # "customDomain": "example.com"
         
         data = {
             "customDomain": domain
         }
         
         try:
             # Using PATCH to only update the specific field
             resp = requests.patch(url, headers=headers, json=data, timeout=15)
             if resp.ok:
                 return resp.json()
             else:
                 return {"error": resp.text}
         except Exception as e:
             return {"error": str(e)}

def get_account_manager():
    return AccountManager()
