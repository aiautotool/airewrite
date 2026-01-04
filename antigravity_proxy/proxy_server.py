import os
import json
import glob
import time
import uuid
import requests
import random
import threading
import datetime
import re
import traceback
from urllib.parse import urlparse
from flask import Flask, request, jsonify, Response, stream_with_context, render_template

# Configuration
ACCOUNTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "accounts")
CLIENT_ID = "1071006060591-tmhssin2h21lcre235vtolojh4g403ep.apps.googleusercontent.com"
CLIENT_SECRET = "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"
V1_INTERNAL_BASE_URL = "https://cloudcode-pa.googleapis.com/v1internal"

def strip_blog_tags(text):
    if not isinstance(text, str): return text
    start_tag = "[startblog]"
    end_tag = "[endblog]"
    start_index = text.find(start_tag)
    end_index = text.find(end_tag)
    if start_index != -1 and end_index != -1:
        content = text[start_index + len(start_tag):end_index]
        return content.strip()
    return text.replace(start_tag, "").replace(end_tag, "").strip()

def slugify(text):
    import unicodedata
    import re
    if not text: return ""
    text = unicodedata.normalize('NFD', str(text))
    text = text.encode('ascii', 'ignore').decode('utf-8')
    text = text.lower()
    text = re.sub(r'\s+', '-', text)
    text = re.sub(r'[^\w\-]+', '', text)
    text = re.sub(r'\-\-+', '-', text)
    text = text.strip('-')
    return text

app = Flask(__name__, template_folder='templates')

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/ui/chat')
def chat_ui():
    return render_template('chat.html')

@app.route('/ui/models')
def models_ui():
    return render_template('models.html')

@app.route('/ui/accounts')
def accounts_ui():
    return render_template('accounts.html')

@app.route('/ui/docs')
def docs_ui():
    import markdown
    with open('README.md', 'r') as f:
        content = f.read()
    html_content = markdown.markdown(content)
    return render_template('docs.html', content=html_content)

@app.route('/api/accounts', methods=['GET'])
def list_accounts_api():
    accounts = token_manager.get_all_accounts()
    # Remove sensitive tokens for listing if needed, but for manage UI we might need them?
    # Let's keep them for now as it's a private proxy.
    return jsonify(accounts)

@app.route('/api/accounts/<account_id>', methods=['DELETE'])
def delete_account_api(account_id):
    try:
        success = token_manager.delete_account(account_id)
        if success:
            return jsonify({"status": "success"})
        return jsonify({"error": "Account not found"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/accounts/refresh', methods=['POST'])
def refresh_accounts_api():
    # Refresh quotas for all or specific accounts
    data = request.json or {}
    account_ids = data.get('account_ids')
    if not account_ids:
        account_ids = [acc['id'] for acc in token_manager.get_all_accounts()]
    
    results = []
    for aid in account_ids:
        try:
            # Getting token triggers refresh and project_id fetch
            access_token, project_id, email = token_manager.refresh_and_get(aid)
            # Also fetch latest models/quotas
            models = token_manager.fetch_available_models_network(access_token, project_id)
            if models:
                with token_manager.lock:
                    acc = token_manager.accounts[aid]
                    acc['data']['quota']['models'] = models
                    acc['data']['quota']['last_updated'] = int(time.time())
                    token_manager.save_account(aid)
            results.append({"id": aid, "status": "success", "email": email})
        except Exception as e:
            results.append({"id": aid, "status": "error", "error": str(e)})
            
    return jsonify(results)

@app.route('/ui/login')
def login_ui():
    return render_template('login.html')

@app.route('/api/login', methods=['POST'])
def api_login():
    data = request.json
    refresh_token = data.get('refresh_token')
    if not refresh_token:
        return jsonify({"error": "Missing refresh_token"}), 400
    
    try:
        account_id, email = token_manager.register_account(refresh_token)
        return jsonify({"status": "success", "account_id": account_id, "email": email})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@app.route('/api/oauth/start')
def oauth_start():
    # Use localhost:5007 as redirect URI as it's common for desktop-auth style apps
    # We use http because it's locally hosted.
    redirect_uri = f"http://localhost:5007/oauth-callback"
    scopes = [
        "https://www.googleapis.com/auth/cloud-platform",
        "https://www.googleapis.com/auth/userinfo.email",
        "https://www.googleapis.com/auth/userinfo.profile",
        "https://www.googleapis.com/auth/cclog",
        "https://www.googleapis.com/auth/experimentsandconfigs"
    ]
    auth_url = (
        "https://accounts.google.com/o/oauth2/v2/auth?"
        f"client_id={CLIENT_ID}&"
        f"redirect_uri={redirect_uri}&"
        "response_type=code&"
        f"scope={' '.join(scopes)}&"
        "access_type=offline&"
        "prompt=consent&"
        "include_granted_scopes=true"
    )
    return jsonify({"auth_url": auth_url})

@app.route('/oauth-callback')
def oauth_callback():
    code = request.args.get('code')
    if not code:
        return "Error: Missing code", 400
    
    # Exchange code for tokens
    redirect_uri = f"http://localhost:5007/oauth-callback"
    url = "https://oauth2.googleapis.com/token"
    data = {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "code": code,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code"
    }
    
    try:
        resp = requests.post(url, data=data, timeout=10)
        if not resp.ok:
            return f"Error: Token exchange failed: {resp.text}", 500
        
        token_data = resp.json()
        refresh_token = token_data.get('refresh_token')
        if not refresh_token:
            return "Error: Google did not return a refresh_token. If you have already authorized this app, please revoke access and try again.", 400
        
        # Register account
        account_id, email = token_manager.register_account(refresh_token)
        
        return f"""
        <html>
            <body style="font-family: sans-serif; text-align: center; padding: 50px; background: #0f172a; color: white;">
                <h1 style="color: #22c55e;">✅ Success!</h1>
                <p>Account <strong>{email}</strong> has been registered.</p>
                <p>You can now close this tab and return to the dashboard.</p>
                <script>setTimeout(() => window.location.href = '/ui/accounts', 3000);</script>
            </body>
        </html>
        """
    except Exception as e:
        return f"Error: {str(e)}", 500

class TokenManager:
    def __init__(self, accounts_dir):
        self.accounts_dir = accounts_dir
        self.accounts = {} # id -> account_data
        self.available_models = set()
        self.lock = threading.RLock()
        self.load_accounts()

    def load_accounts(self):
        with self.lock:
            self.accounts = {}
            self.available_models = set()
            if not os.path.exists(self.accounts_dir):
                print(f"Accounts directory not found: {self.accounts_dir}")
                # Fallback to defaults
                self.available_models = {
                    "gemini-2.0-flash-exp", "gemini-2.5-flash", "gemini-exp-1206",
                    "gemini-3-pro-high", "gemini-3-pro-low", "gemini-3-flash",
                    "claude-sonnet-4.5", "claude-sonnet-4.5-thinking", "claude-opus-4.5-thinking", 
                    "gpt-oss-120b"
                }
                return

            files = glob.glob(os.path.join(self.accounts_dir, "*.json"))
            for f in files:
                try:
                    with open(f, 'r') as fp:
                        data = json.load(fp)
                        # Basic validation
                        if 'id' in data and 'token' in data:
                            self.accounts[data['id']] = {
                                'data': data,
                                'path': f
                            }
                            # Aggregate models
                            if 'quota' in data and 'models' in data['quota']:
                                for m in data['quota']['models']:
                                    if 'name' in m:
                                        self.available_models.add(m['name'])
                                        
                except Exception as e:
                    print(f"Failed to load {f}: {e}")
            
            # If no models found in any accounts, fallback to defaults
            if not self.available_models:
                self.available_models = {
                    "gemini-2.0-flash-exp", "gemini-2.5-flash", "gemini-exp-1206",
                    "gemini-3-pro-high", "gemini-3-pro-low", "gemini-3-flash",
                    "claude-sonnet-4.5", "claude-sonnet-4.5-thinking", "claude-opus-4.5-thinking", 
                    "gpt-oss-120b"
                }
                
            print(f"Loaded {len(self.accounts)} accounts and {len(self.available_models)} unique models.")

    def get_all_models(self):
        with self.lock:
            models_list = []
            for m_name in self.available_models:
                # Basic normalization for display name
                display_name = m_name.replace("-", " ").title()
                display_name = display_name.replace(" 4 5", " 4.5").replace(" 2 5", " 2.5").replace(" 2 0", " 2.0").replace(" 3 5", " 3.5").replace(" 3 Pro", " 3 Pro")
                
                models_list.append({
                    "name": f"models/{m_name}",
                    "displayName": display_name,
                    "supportedGenerationMethods": ["generateContent"]
                })
            
            models_list.sort(key=lambda x: x['name'])
            return models_list

    def save_account(self, account_id):
        with self.lock:
            if account_id in self.accounts:
                acc = self.accounts[account_id]
                try:
                    with open(acc['path'], 'w') as fp:
                        json.dump(acc['data'], fp, indent=2)
                except Exception as e:
                    print(f"Failed to save account {account_id}: {e}")

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
                    # Re-aggregate available models after deletion
                    self.load_accounts()
                    return True
                except Exception as e:
                    print(f"Failed to delete account {account_id}: {e}")
                    raise
            return False

    def get_token_for_account(self, account_id):
        # Specific token retrieval for a given account
        return self.refresh_and_get(account_id)

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
        
        # Check if needs refresh (buffer 5 mins)
        if now >= expiry_timestamp - 300:
            # print(f"Refreshing token for {acc_entry['data'].get('email')}...")
            new_tokens = self.perform_refresh(refresh_token)
            
            # Update state
            with self.lock:
                # Re-read to ensure we are updating latest
                acc_entry = self.accounts[account_id]
                t_data = acc_entry['data']['token']
                t_data['access_token'] = new_tokens['access_token']
                t_data['expires_in'] = new_tokens['expires_in']
                t_data['expiry_timestamp'] = int(now + new_tokens['expires_in'])
                
                self.save_account(account_id)
                access_token = new_tokens['access_token']
        
        # Check project_id
        if not project_id:
             # Token valid but missing project_id
             # print(f"Fetching project_id for {acc_entry['data'].get('email')}...")
             project_id, tier = self.fetch_project_info_network(access_token)
             with self.lock:
                 acc_entry = self.accounts[account_id] # Re-fetch to be safe
                 acc_entry['data']['token']['project_id'] = project_id
                 if 'quota' in acc_entry['data']:
                     acc_entry['data']['quota']['subscription_tier'] = tier
                 self.save_account(account_id)
                 
        return access_token, project_id, acc_entry['data'].get('email')

    def perform_refresh(self, refresh_token):
        url = "https://oauth2.googleapis.com/token"
        data = {
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token"
        }
        try:
            # print(f"Sending refresh request to Google...")
            resp = requests.post(url, data=data, timeout=20)
            if not resp.ok:
                print(f"Refresh response error: {resp.status_code} - {resp.text}")
                raise Exception(f"Refresh failed: {resp.text}")
            # print("Refresh successful.")
            return resp.json()
        except Exception as e:
            print(f"Refresh request exception: {e}")
            raise

    def fetch_project_info_network(self, access_token):
        print("Fetching project info from network...")
        url = f"{V1_INTERNAL_BASE_URL}:loadCodeAssist"
        headers = {
            "Authorization": f"Bearer {access_token}",
            "User-Agent": "antigravity/1.11.3 Darwin/arm64",
            "Content-Type": "application/json",
            "Host": "cloudcode-pa.googleapis.com"
        }
        
        # Try multiple IDE types
        for ide_type in ["ANTIGRAVITY", "VSCODE", "INTELLIJ"]:
            data = {"metadata": {"ideType": ide_type}}
            try:
                resp = requests.post(url, headers=headers, json=data, timeout=10)
                if resp.ok:
                    j = resp.json()
                    pid = j.get('cloudaicompanionProject')
                    # Detect tier
                    paid_tier = j.get('paidTier', {}) if isinstance(j.get('paidTier'), dict) else {}
                    current_tier = j.get('currentTier', {}) if isinstance(j.get('currentTier'), dict) else {}
                    tier = paid_tier.get('id') or current_tier.get('id') or "free-tier"
                    
                    if pid:
                        print(f"Got project ID: {pid}, Tier: {tier}")
                        return pid, tier
            except Exception as e:
                print(f"Error fetching project_info ({ide_type}): {e}")
        
        return self.generate_mock_project_id(), "free-tier"

    def fetch_available_models_network(self, access_token, project_id):
        print(f"Fetching available models for project {project_id}...")
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
                    
                    # Store common models
                    if any(x in name.lower() for x in ["gemini", "claude", "gpt"]):
                        parsed_models.append({
                            "name": name,
                            "percentage": percentage,
                            "reset_time": reset_time
                        })
                
                # Sort models by name
                parsed_models.sort(key=lambda x: x['name'])
                print(f"Found {len(parsed_models)} available models.")
                return parsed_models
        except Exception as e:
            print(f"Error fetching models: {e}")
        return []

    def generate_mock_project_id(self):
        adjectives = ["useful", "bright", "swift", "calm", "bold"]
        nouns = ["fuze", "wave", "spark", "flow", "core"]
        adj = random.choice(adjectives)
        noun = random.choice(nouns)
        chars = "abcdefghijklmnopqrstuvwxyz0123456789"
        rand_str = "".join(random.choice(chars) for _ in range(5))
        return f"{adj}-{noun}-{rand_str}"

    def register_account(self, refresh_token):
        """Exchange refresh token for access token, fetch details, and save as new account."""
        print(f"Registering new account with refresh token: {refresh_token[:10]}...")
        
        # 1. Fetch initial access token
        new_tokens = self.perform_refresh(refresh_token)
        access_token = new_tokens['access_token']
        
        # 2. Try to get email from userinfo endpoint
        email = "unknown@gmail.com"
        name = "Unknown User"
        try:
            userinfo_resp = requests.get("https://www.googleapis.com/oauth2/v3/userinfo", 
                                       headers={"Authorization": f"Bearer {access_token}"}, timeout=5)
            if userinfo_resp.ok:
                uinfo = userinfo_resp.json()
                email = uinfo.get('email', email)
                name = uinfo.get('name', name)
        except Exception as e:
            print(f"Failed to fetch userinfo: {e}")
            
        # 3. Fetch project and tier info
        project_id, tier = self.fetch_project_info_network(access_token)
        
        # 4. Fetch real available models and quotas
        models = self.fetch_available_models_network(access_token, project_id)
        
        # If no models found, use defaults as fallback
        if not models:
            models = [
                {"name": "gemini-3-flash", "percentage": 100},
                {"name": "gemini-3-pro-high", "percentage": 100},
                {"name": "gemini-3-pro-low", "percentage": 100},
                {"name": "gemini-3-pro-image", "percentage": 100},
                {"name": "claude-sonnet-4-5", "percentage": 100}
            ]
        
        # 5. Create account data
        account_id = str(uuid.uuid4())
        now = int(time.time())
        
        account_data = {
            "id": account_id,
            "email": email,
            "name": name,
            "token": {
                "access_token": access_token,
                "refresh_token": refresh_token,
                "expires_in": new_tokens['expires_in'],
                "expiry_timestamp": now + new_tokens['expires_in'],
                "token_type": "Bearer",
                "email": email,
                "project_id": project_id
            },
            "quota": {
                "models": models,
                "last_updated": now,
                "is_forbidden": False,
                "subscription_tier": tier
            },
            "created_at": now,
            "last_used": now
        }
        
        # 6. Save to file
        file_path = os.path.join(self.accounts_dir, f"{account_id}.json")
        os.makedirs(self.accounts_dir, exist_ok=True)
        with open(file_path, 'w') as f:
            json.dump(account_data, f, indent=2)
            
        print(f"Successfully registered account: {email} (ID: {account_id})")
        
        # 6. Reload accounts
        self.load_accounts()
        return account_id, email

class ToolExecutor:
    @staticmethod
    def get_current_time():
        return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    @staticmethod
    def visit_url(url):
        try:
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"}
            resp = requests.get(url, headers=headers, timeout=10)
            if not resp.ok:
                return f"Error visiting URL: {resp.status_code}"
            
            # Simple stripped text (simulating strip_blog_tags logic but for full html)
            text = resp.text
            # Remove scripts and styles
            text = re.sub(r'<script.*?>.*?</script>', '', text, flags=re.DOTALL)
            text = re.sub(r'<style.*?>.*?</style>', '', text, flags=re.DOTALL)
            text = re.sub(r'<[^>]+>', ' ', text)
            text = re.sub(r'\s+', ' ', text).strip()
            return text[:4000] + "..." if len(text) > 4000 else text # Truncate
        except Exception as e:
            return f"Exception visiting URL: {e}"

    @staticmethod
    def python_exec(code):
        # Basic Security Sandbox (WARNING: Still risky, use with caution)
        # We strip import of dangerous modules
        if any(x in code for x in ["os.system", "subprocess", "sys.exit", "shutil", "open("]):
            return "Security Error: Dangerous keywords detected."
        
        buffer = []
        def print_capture(*args):
            buffer.append(" ".join(map(str, args)))
            
        safe_globals = {
            "print": print_capture,
            "math": __import__("math"),
            "datetime": datetime,
            "json": json,
            "random": random
        }
        
        try:
            exec(code, safe_globals)
            return "\n".join(buffer) if buffer else "[No Output]"
        except Exception as e:
            return f"Execution Error: {e}"

    @staticmethod
    def execute_tool(tool_name, args_str):
        print(f"[ToolExecutor] Call: {tool_name} with {args_str}")
        if tool_name == "get_current_time":
            return ToolExecutor.get_current_time()
        elif tool_name == "visit_url":
            # Extract URL safely
            url_match = re.search(r'["\'](.*?)["\']', args_str)
            url = url_match.group(1) if url_match else args_str.strip()
            return ToolExecutor.visit_url(url)
        elif tool_name == "python_exec":
            # Extract code - expectation is raw code or string
            return ToolExecutor.python_exec(args_str)
        return "Unknown tool"

# Initialize TokenManager
token_manager = TokenManager(ACCOUNTS_DIR)

@app.route('/v1beta/models', methods=['GET'])
def list_models():
    # Dynamic list based on what accounts have access to
    models = token_manager.get_all_models()
    return jsonify({"models": models})

@app.route('/v1beta/models/<path:model_path>', methods=['GET'])
def get_model(model_path):
    # Mock response
    model_name = model_path.split(':')[0] if ':' in model_path else model_path
    
    # Try to find specific display name
    display_name = model_name
    all_models = token_manager.get_all_models()
    for m in all_models:
        if m['name'] == model_name or m['name'] == f"models/{model_name}":
            display_name = m['displayName']
            break
            
    return jsonify({
        "name": f"models/{model_name}",
        "displayName": display_name,
        "supportedGenerationMethods": ["generateContent"]
    })

@app.route('/v1/agent/smart', methods=['POST'])
def smart_agent(return_openai_format=False):
    # An intelligent router that picks the best tool/model for the task
    body = request.json
    messages = body.get('messages', [])
    prompt = body.get('prompt', '')
    
    # If using OpenAI style, history is in 'messages'
    if messages and not prompt:
        prompt = messages[-1].get('content', '')

    if not prompt and not messages:
        return jsonify({"error": "No prompt or messages provided"}), 400

    # 1. Routing & Setup
    model_name = "gemini-3-flash"
    
    # Simple Heuristics for initial model selection
    image_keywords = ["draw", "generate image", "vẽ", "tạo ảnh", "create a picture", "make an image"]
    if any(k in prompt.lower() for k in image_keywords):
        model_name = "gemini-3-pro-image"
    
    # ReAct Loop capability check
    # Only engage ReAct loop for complex queries or explicit tool needs
    # Otherwise fast path
    react_keywords = ["url", "link", "visit", "đọc báo", "web", "tính toán", "calculate", "code", "run", "thời gian", "time", "analysis", "execute"]
    enable_react = any(k in prompt.lower() for k in react_keywords)

    use_search = False
    
    final_response_text = ""
    
    if enable_react and "gemini-3-pro-image" not in model_name:
        # === REACT LOOP START ===
        print(f"[SmartAgent] Engaging ReAct Loop (Model: {model_name})")
        
        max_turns = 5
        current_messages = messages if messages else [{"role": "user", "content": prompt}]
        
        # System Prompt Injection (Ephemeral)
        system_instr = """
You are a smart AI assistant. You have access to the following tools:
1. get_current_time(): Returns current date and time.
2. visit_url(url): Fetches text from a given URL.
3. python_exec(code): Executes Python code (e.g. for math).

If you need to use a tool, OUTPUT ONLY the tool call in this format:
<tool_code>
function_name(args)
</tool_code>

Example: <tool_code>visit_url("https://google.com")</tool_code>
Or: <tool_code>python_exec("print(2+2)")</tool_code>

If you have the details, reply normally.
"""
        # Prepend system instruction to the last user message or add as system role if supported (using user for compat)
        # We'll just append to history for the context of this turn
        react_history = list(current_messages)
        react_history[0]['content'] = system_instr + "\n\nUser Query: " + react_history[0]['content']

        for turn in range(max_turns):
            print(f"[SmartAgent] Turn {turn} history roles: {[m['role'] for m in react_history]}")
            success, result_text = process_generation_core(react_history, False, model_name)
            if not success:
                print(f"[SmartAgent] Step failed at turn {turn}: {result_text}")
                final_response_text = f"Error: Agent Process Failed at turn {turn}. {result_text}"
                break
                
            # Check for tool call - be more flexible with markdown/tags/codeblocks
            # This regex looks for function calls like func(args) following tool_code tags
            tool_match = re.search(r'(?:<tool_code>|tool_code>|```tool_code)\s*([a-zA-Z_]\w*)\((.*?)\)', result_text, re.DOTALL | re.IGNORECASE)
            
            if tool_match:
                func_name = tool_match.group(1).strip()
                args_str = tool_match.group(2).strip()
                
                # Execute
                tool_output = ToolExecutor.execute_tool(func_name, args_str)
                
                # Append to history - ensure role is model for assistant messages
                react_history.append({"role": "assistant", "content": result_text})
                react_history.append({"role": "user", "content": f"TOOL OUTPUT: {tool_output}\n\nContinue providing the answer."})
                print(f"[SmartAgent] Turn {turn} Tool {func_name} output len: {len(tool_output)}")
            else:
                # No tool call, final answer
                final_response_text = result_text
                break
        else:
             final_response_text = "Agent reached maximum turns without final conclusion."

    else:
        # Standard Path
        # Online / Search detection
        search_keywords = ["search", "tìm kiếm", "online", "current", "latest", "mới nhất", "hôm nay"]
        use_search = any(k in prompt.lower() for k in search_keywords) or "-online" in body.get('model', '')
        
        print(f"[SmartAgent] Fast Path: {model_name} (Search: {use_search})")
        success, final_response_text = process_generation_core(messages if messages else prompt, False, model_name, use_search=use_search)
        if not success:
            return jsonify({"error": "Agent failed to process request", "details": final_response_text}), 500

    # Return Format
    if return_openai_format:
        return jsonify({
            "id": f"chatcmpl-{uuid.uuid4()}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": f"smart-agent({model_name})",
            "choices": [{
                "index": 0,
                "message": {"role": "assistant", "content": final_response_text},
                "finish_reason": "stop"
            }],
            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        })
    
    return jsonify({"result": final_response_text, "model": model_name, "search_used": use_search})

def call_external_provider(model_name, prompt_parts):
    # Support for external providers as failover
    providers = [
        {"name": "pollinations", "url": "https://text.pollinations.ai/openai", "model": "openai"},
        {"name": "duckduckgo", "url": "https://duckduckgo.com/aivc/v1/chat/completions", "model": "gpt-4o-mini"} # Hypothetical/Common
    ]
    
    user_message = next((p['text'] for p in prompt_parts if 'text' in p), "")
    
    for provider in providers:
        if provider['name'] in model_name.lower():
            print(f"Calling backup provider: {provider['name']}...")
            try:
                resp = requests.post(provider['url'], json={
                    "model": provider['model'],
                    "messages": [{"role": "user", "content": user_message}]
                }, timeout=15)
                if resp.ok:
                    return True, resp.json()['choices'][0]['message']['content']
            except: pass
    return False, None

def process_generation_core(prompt_input, is_stream, model_name="gemini-3-flash", use_search=False):
    # Handle Input: could be a string, a list of Gemini parts, or a list of OpenAI messages
    gemini_contents = []
    
    if isinstance(prompt_input, str):
        gemini_contents = [{"role": "user", "parts": [{"text": prompt_input}]}]
    elif isinstance(prompt_input, list):
        if len(prompt_input) > 0 and 'role' in prompt_input[0]:
            # Convert OpenAI Messages to Gemini Contents
            for m in prompt_input:
                role = "user" if m["role"] == "user" else "model"
                if m["role"] in ["assistant", "model"]:
                    role = "model"
                elif m["role"] in ["user", "system"]:
                    role = "user"
                content = m.get("content", "")
                parts = []
                if isinstance(content, str):
                    parts.append({"text": content})
                elif isinstance(content, list):
                    for p in content:
                        if p.get("type") == "text":
                            parts.append({"text": p.get("text", "")})
                        elif p.get("type") == "image_url":
                            img_url = p.get("image_url", {}).get("url", "")
                            if img_url.startswith("data:"):
                                mime = img_url.split(";")[0].split(":")[1]
                                b64 = img_url.split("base64,")[1]
                                parts.append({"inlineData": {"data": b64, "mimeType": mime}})
                gemini_contents.append({"role": role, "parts": parts})
        else:
            # Already a list of Gemini parts (legacy/simple)
            gemini_contents = [{"role": "user", "parts": prompt_input}]
    
    # Auto-detect search from model name
    if "-online" in model_name:
        use_search = True
        model_name = model_name.replace("-online", "")

    # Extract just the parts of the latest user message for external/legacy compatibility
    prompt_parts = gemini_contents[-1]["parts"] if gemini_contents else []

    # Try external providers if requested by model name (e.g. pollination-*)
    ext_success, ext_res = call_external_provider(model_name, prompt_parts)
    if ext_success:
        return True, ext_res

    # Retry Loop
    account_ids = [acc['id'] for acc in token_manager.get_all_accounts()]
    random.shuffle(account_ids)
    
    last_error_resp = None
    
    is_image_gen = "gemini-3-pro-image" in model_name
    
    for account_id in account_ids:
        try:
            # 1. Get Token
            access_token, project_id, email = token_manager.get_token_for_account(account_id)
        except Exception as e:
            print(f"Skipping account {account_id} due to token error: {e}")
            continue

        # 2. Call Upstream
        headers = {
            "Authorization": f"Bearer {access_token}",
            "User-Agent": "antigravity/1.11.3 Darwin/arm64",
            "Content-Type": "application/json"
        }

        if is_image_gen:
            # Image Generation Payload (uses only the last prompt usually)
            last_parts = gemini_contents[-1]["parts"]
            upstream_url = f"{V1_INTERNAL_BASE_URL}:generateContent"
            aspect_ratio = "1:1"
            if "16x9" in model_name: aspect_ratio = "16:9"
            elif "9x16" in model_name: aspect_ratio = "9:16"
            elif "4x3" in model_name: aspect_ratio = "4:3"
            elif "3x4" in model_name: aspect_ratio = "3:4"
            
            final_request = {
                "project": project_id,
                "requestId": f"gen-{uuid.uuid4()}",
                "request": {
                    "contents": [{"parts": last_parts}],
                    "generationConfig": {
                        "imageConfig": {
                            "aspectRatio": aspect_ratio
                        }
                    }
                },
                "model": "gemini-3-pro-image",
                "userAgent": "antigravity",
                "requestType": "image_gen"
            }
        elif use_search:
            # Use generateContent for tools/grounding support
            upstream_url = f"{V1_INTERNAL_BASE_URL}:generateContent"
            final_request = {
                "project": project_id,
                "request": {
                    "contents": gemini_contents,
                    "tools": [{"googleSearch": {}}]
                },
                "model": model_name,
                "requestType": "agent"
            }
        else:
            # Standard Chat/Code Generation (generateChat)
            # generateChat in internal API is often single-turn or takes context in special ways.
            # However, we'll try to use generateContent (which is more powerful) for everything if possible
            # But the v1internal:generateChat is verified for fast responses.
            # Map history into a single message for generateChat or use the last message.
            user_message = next((p['text'] for p in gemini_contents[-1]['parts'] if 'text' in p), "")
            
            upstream_url = f"{V1_INTERNAL_BASE_URL}:generateChat"
            final_request = {
                "project": project_id,
                "userMessage": user_message,
                "metadata": {"ideType": "ANTIGRAVITY"}
            }
            # Note: For real history in generateChat, we'd need to append previous turns to userMessage 
            # Or use generateContent if the account supports it.
            # Let's check if we can switch to generateContent for all standard chats to get true history.
            if len(gemini_contents) > 1:
                upstream_url = f"{V1_INTERNAL_BASE_URL}:generateContent"
                final_request = {
                    "project": project_id,
                    "request": {
                        "contents": gemini_contents
                    },
                    "model": model_name
                }

        print(f"DEBUG: Upstream Request to {upstream_url}: {json.dumps(final_request)[:500]}")
        try:
            resp = requests.post(upstream_url, headers=headers, json=final_request, timeout=120) 
            print(f"DEBUG: Upstream Status: {resp.status_code}")
            
            if resp.ok:
                print(f"Success with account {email} (Search: {use_search})")
                internal_data = resp.json()
                
                if is_image_gen:
                    if "response" in internal_data:
                        return True, internal_data["response"]
                    return True, internal_data
                elif use_search:
                    # Extract text from candidates (Gemini style)
                    try:
                        # v1internal might wrap the response in a "response" field
                        res_obj = internal_data.get("response", internal_data)
                        text = res_obj['candidates'][0]['content']['parts'][0]['text']
                        return True, strip_blog_tags(text)
                    except Exception as e:
                        print(f"DEBUG: Failed to parse search response: {e}. Data: {json.dumps(internal_data)[:500]}")
                        return True, internal_data # Fallback to raw
                else:
                    markdown_text = internal_data.get('markdown', '')
                    if not markdown_text and 'response' in internal_data:
                        # Maybe it's a generateContent response inside 'response'
                        try:
                            markdown_text = internal_data['response']['candidates'][0]['content']['parts'][0]['text']
                        except: pass
                    
                    if not markdown_text and 'candidates' in internal_data:
                        # Direct generateContent response
                        try:
                            markdown_text = internal_data['candidates'][0]['content']['parts'][0]['text']
                        except: pass
                        
                    return True, strip_blog_tags(markdown_text)
            else:
                print(f"Failed with account {email} (PID: {project_id}): {resp.status_code} - {resp.text[:500]}")
                last_error_resp = (resp.text, resp.status_code)
                    
        except Exception as e:
            print(f"Network exception with account {email}: {e}")
            last_error_resp = (str(e), 502)
            continue
            
    # All failed
    return False, last_error_resp

@app.route('/v1beta/models/<path:model_action>', methods=['POST'])
def generate_content(model_action):
    print(f"Received Gemini request for {model_action}")
    request_body = request.json
    is_stream = "streamGenerateContent" in model_action
    
    # Extract Prompt Parts
    try:
        user_parts = extract_prompt_parts(request_body)
    except Exception as e:
        return jsonify({"error": f"Invalid request format: {e}"}), 400

    # Extract model name if possible
    model_name = "gemini-3-flash"
    if "models/" in model_action:
        model_name = model_action.split('/')[-1]
    else:
        model_name = model_action.split(':')[0]

    success, result = process_generation_core(user_parts, is_stream, model_name)
    
    if success:
        if "gemini-3-pro-image" in model_name:
             # Just return what we got, it's already a Gemini response object (possibly wrapped)
             # But if simulate_stream is needed we might need to be careful.
             if is_stream:
                 return simulate_stream_response(result)
             else:
                 return jsonify(result)
        
        # result is markdown_text for chat
        gemini_resp = wrap_as_gemini_response(result)
        if is_stream:
            return simulate_stream_response(gemini_resp)
        else:
            return jsonify(gemini_resp)
    else:
        # result is (error_text, status_code)
        if result:
            return Response(result[0], status=result[1], mimetype="application/json")
        return jsonify({"error": "No valid accounts found"}), 503

@app.route('/v1/chat/completions', methods=['POST'])
def openai_chat_completions():
    print("Received OpenAI request")
    request_body = request.json
    is_stream = request_body.get("stream", False)
    model_name = request_body.get("model", "gemini-3-flash")

    if model_name == "smart-agent":
        return smart_agent(return_openai_format=True)
    
    # Extract messages
    messages = request_body.get("messages", [])
    if not messages:
        return jsonify({"error": "Missing messages"}), 400
        
    # Pass the full message list for history
    success, result = process_generation_core(messages, is_stream, model_name)
    
    if success:
        # If image, result is the Gemini JSON response. We need to convert it to OpenAI format?
        # Or just return a "Image generated" text if it's too complex.
        # But wait, Python example in ApiProxy.tsx expects text content.
        # The image data is likely in result['candidates'][0]['content']['parts'][0]['inlineData']['data']
        # We should put that base64 into the content or as an image_url?
        
        if "gemini-3-pro-image" in model_name:
             # Try to extract base64 from parts
             try:
                 parts = result['candidates'][0]['content']['parts']
                 b64 = None
                 mime = "image/jpeg"
                 for p in parts:
                     if 'inlineData' in p:
                         b64 = p['inlineData']['data']
                         mime = p['inlineData']['mimeType']
                         break
                 
                 if b64:
                     markdown_text = f"![Generated Image](data:{mime};base64,{b64})"
                 else:
                     markdown_text = "Image generation successful but no image data found in response parts."
             except Exception as e:
                 markdown_text = f"Image generation successful but parsing failed: {e}"
        else:
             markdown_text = result
             
        openai_resp = {
            "id": f"chatcmpl-{uuid.uuid4()}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": model_name,
            "choices": [{
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": markdown_text
                },
                "finish_reason": "stop"
            }],
            "usage": {
                "prompt_tokens": len(str(messages)),
                "completion_tokens": len(str(markdown_text)),
                "total_tokens": len(str(messages)) + len(str(markdown_text))
            }
        }
        
        if is_stream:
            def generate():
                chunk_resp = openai_resp.copy()
                chunk_resp["object"] = "chat.completion.chunk"
                del chunk_resp["choices"][0]["message"]
                
                # Content chunk
                chunk_resp["choices"][0]["delta"] = {"role": "assistant", "content": markdown_text}
                chunk_resp["choices"][0]["finish_reason"] = None
                yield f"data: {json.dumps(chunk_resp)}\n\n"
                
                # End chunk
                chunk_resp["choices"][0]["delta"] = {}
                chunk_resp["choices"][0]["finish_reason"] = "stop"
                yield f"data: {json.dumps(chunk_resp)}\n\n"
                yield "data: [DONE]\n\n"
            return Response(stream_with_context(generate()), mimetype="text/event-stream")
        else:
            return jsonify(openai_resp)
            
    else:
        if result:
            return Response(result[0], status=result[1], mimetype="application/json")
        return jsonify({"error": "No valid accounts found"}), 503

def extract_prompt_parts(body):
    if "contents" in body:
        return body["contents"][-1].get("parts", [])
    if "prompt" in body:
        return [{"text": body["prompt"]}]
    return [{"text": "Hello"}]

def wrap_as_gemini_response(text):
    return {
        "candidates": [
            {
                "content": {
                    "parts": [{"text": text}],
                    "role": "model"
                },
                "finishReason": "STOP",
                "index": 0,
                "safetyRatings": []
            }
        ],
        "usageMetadata": {
            "promptTokenCount": 0,
            "candidatesTokenCount": len(text),
            "totalTokenCount": len(text)
        }
    }

def simulate_stream_response(json_data):
    def generate():
        yield f"data: {json.dumps(json_data)}\n\n"
        yield "data: [DONE]\n\n"
    return Response(stream_with_context(generate()), mimetype="text/event-stream")

if __name__ == '__main__':
    print("Starting Antigravity Proxy Server on 0.0.0.0:5007...")
    app.run(host='0.0.0.0', port=5007, debug=True, use_reloader=False)
