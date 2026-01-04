import requests
import json
import base64
import os
from datetime import datetime

class WPAPIManager:
    """Manages direct communication with WordPress REST API"""
    
    def __init__(self, config_file=None):
        if config_file is None:
            self.config_dir = os.path.expanduser("~/.airewrite_data")
            if not os.path.exists(self.config_dir):
                os.makedirs(self.config_dir)
            self.config_file = os.path.join(self.config_dir, "wp_destinations.json")
        else:
            self.config_file = config_file
            
        self.destinations = self.load_destinations()

    def load_destinations(self):
        """Load WordPress site configurations from JSON file"""
        if not os.path.exists(self.config_file):
            return []
        try:
            with open(self.config_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading WP destinations: {e}")
            return []

    def save_destinations(self):
        """Save current destinations to JSON file"""
        try:
            with open(self.config_file, "w", encoding="utf-8") as f:
                json.dump(self.destinations, f, indent=4, ensure_ascii=False)
            return True
        except Exception as e:
            print(f"Error saving WP destinations: {e}")
            return False

    def add_destination(self, name, site_url, username, app_password):
        """Add a new WordPress site destination"""
        dest_id = datetime.now().strftime("%Y%m%d%H%M%S")
        new_dest = {
            "id": dest_id,
            "name": name,
            "site_url": site_url.rstrip('/'),
            "username": username,
            "app_password": app_password
        }
        self.destinations.append(new_dest)
        self.save_destinations()
        return dest_id

    def remove_destination(self, dest_id):
        """Remove a WordPress site destination by ID"""
        self.destinations = [d for d in self.destinations if d['id'] != dest_id]
        return self.save_destinations()

    def list_destinations(self):
        """Return list of all registered destinations"""
        return self.destinations

    def get_destination(self, dest_id):
        """Find a destination by its ID"""
        for d in self.destinations:
            if d['id'] == dest_id:
                return d
        return None

    def _get_auth_header(self, username, app_password):
        """Generate Basic Auth header for WordPress REST API"""
        credentials = f"{username}:{app_password}"
        token = base64.b64encode(credentials.encode()).decode()
        return {"Authorization": f"Basic {token}"}

    def post_article(self, dest_config, title, content, slug=None, status="publish", categories=None, author_id=None):
        """
        Post a new article to a WordPress site via REST API
        """
        site_url = dest_config.get("site_url")
        username = dest_config.get("username")
        app_password = dest_config.get("app_password")
        
        if not all([site_url, username, app_password]):
            return {"error": "Invalid site configuration", "status": 0}

        api_url = f"{site_url}/wp-json/wp/v2/posts"
        headers = self._get_auth_header(username, app_password)
        
        payload = {
            "title": title,
            "content": content,
            "status": status
        }
        
        if slug:
            payload["slug"] = slug
        if categories:
            # categories should be a list of IDs
            payload["categories"] = categories if isinstance(categories, list) else [categories]
        if author_id:
            payload["author"] = author_id

        try:
            response = requests.post(api_url, headers=headers, json=payload, timeout=20)
            if response.status_code in [200, 201]:
                return {"success": True, "id": response.json().get("id"), "status": response.status_code}
            else:
                return {"success": False, "error": response.text, "status": response.status_code}
        except Exception as e:
            return {"success": False, "error": str(e), "status": 0}

    def get_categories(self, dest_config):
        """Fetch categories from the WordPress site"""
        site_url = dest_config.get("site_url")
        username = dest_config.get("username")
        app_password = dest_config.get("app_password")
        
        api_url = f"{site_url}/wp-json/wp/v2/categories?per_page=100"
        headers = self._get_auth_header(username, app_password)
        
        try:
            response = requests.get(api_url, headers=headers, timeout=10)
            if response.status_code == 200:
                return response.json()
            return []
        except:
            return []

# Singleton instance access
_wp_manager = None
def get_wp_manager():
    global _wp_manager
    if _wp_manager is None:
        _wp_manager = WPAPIManager()
    return _wp_manager
