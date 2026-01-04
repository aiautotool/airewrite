import json
import os
import re
import requests
from datetime import datetime
from bs4 import BeautifulSoup
from urllib.parse import urlparse, parse_qs
import uuid


class SheetManager:
    """Quản lý cấu hình Google Sheets/Forms cho ứng dụng rewrite"""
    
    REQUIRED_FIELDS = ['author_id', 'title', 'slug', 'content', 'publish', 
                       'date_year', 'date_month', 'date_day']
    
    def __init__(self, config_file=None):
        """
        Khởi tạo SheetManager
        
        Args:
            config_file: Đường dẫn file config JSON. Nếu None, dùng mặc định
        """
        if config_file is None:
            data_dir = os.path.expanduser("~/.airewrite_data")
            if not os.path.exists(data_dir):
                os.makedirs(data_dir)
            config_file = os.path.join(data_dir, "sheets_config.json")
        
        self.config_file = config_file
        self.config = self._load_config()
    
    def _load_config(self):
        """Tải config từ file JSON"""
        if not os.path.exists(self.config_file):
            return {"sheets": [], "default_sheet_id": None}
        
        try:
            with open(self.config_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[!] Lỗi tải config: {e}")
            return {"sheets": [], "default_sheet_id": None}
    
    def _save_config(self):
        """Lưu config vào file JSON"""
        try:
            with open(self.config_file, "w", encoding="utf-8") as f:
                json.dump(self.config, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            print(f"[!] Lỗi lưu config: {e}")
            return False
    
    def add_sheet(self, name, form_url, fields, set_as_default=False):
        """
        Thêm sheet mới
        
        Args:
            name: Tên sheet
            form_url: URL Google Form (formResponse)
            fields: Dict mapping field names to entry IDs
            set_as_default: Đặt làm sheet mặc định
            
        Returns:
            sheet_id nếu thành công, None nếu thất bại
        """
        # Validate required fields
        missing_fields = [f for f in self.REQUIRED_FIELDS if f not in fields]
        if missing_fields:
            print(f"[!] Thiếu các field bắt buộc: {', '.join(missing_fields)}")
            return None
        
        # Generate unique ID
        sheet_id = f"sheet_{uuid.uuid4().hex[:8]}"
        
        sheet = {
            "id": sheet_id,
            "name": name,
            "form_url": form_url,
            "fields": fields,
            "created_at": datetime.now().isoformat(),
            "last_used": None
        }
        
        self.config["sheets"].append(sheet)
        
        if set_as_default or len(self.config["sheets"]) == 1:
            self.config["default_sheet_id"] = sheet_id
        
        if self._save_config():
            print(f"[✓] Đã thêm sheet: {name} (ID: {sheet_id})")
            return sheet_id
        return None
    
    def remove_sheet(self, sheet_id):
        """
        Xóa sheet
        
        Args:
            sheet_id: ID của sheet cần xóa
            
        Returns:
            True nếu thành công, False nếu thất bại
        """
        original_count = len(self.config["sheets"])
        self.config["sheets"] = [s for s in self.config["sheets"] if s["id"] != sheet_id]
        
        if len(self.config["sheets"]) < original_count:
            # Nếu xóa sheet mặc định, reset default
            if self.config["default_sheet_id"] == sheet_id:
                self.config["default_sheet_id"] = None
                if self.config["sheets"]:
                    self.config["default_sheet_id"] = self.config["sheets"][0]["id"]
            
            if self._save_config():
                print(f"[✓] Đã xóa sheet ID: {sheet_id}")
                return True
        
        print(f"[!] Không tìm thấy sheet ID: {sheet_id}")
        return False
    
    def update_sheet(self, sheet_id, **kwargs):
        """
        Cập nhật thông tin sheet
        
        Args:
            sheet_id: ID của sheet
            **kwargs: Các field cần update (name, form_url, fields)
            
        Returns:
            True nếu thành công, False nếu thất bại
        """
        for sheet in self.config["sheets"]:
            if sheet["id"] == sheet_id:
                if "name" in kwargs:
                    sheet["name"] = kwargs["name"]
                if "form_url" in kwargs:
                    sheet["form_url"] = kwargs["form_url"]
                if "fields" in kwargs:
                    # Validate required fields
                    missing = [f for f in self.REQUIRED_FIELDS if f not in kwargs["fields"]]
                    if missing:
                        print(f"[!] Thiếu field bắt buộc: {', '.join(missing)}")
                        return False
                    sheet["fields"] = kwargs["fields"]
                
                return self._save_config()
        
        print(f"[!] Không tìm thấy sheet ID: {sheet_id}")
        return False
    
    def get_sheet(self, sheet_id):
        """
        Lấy thông tin sheet
        
        Args:
            sheet_id: ID của sheet
            
        Returns:
            Dict chứa thông tin sheet, None nếu không tìm thấy
        """
        for sheet in self.config["sheets"]:
            if sheet["id"] == sheet_id:
                return sheet
        return None
    
    def list_sheets(self):
        """
        Liệt kê tất cả sheets
        
        Returns:
            List các sheet dicts
        """
        return self.config["sheets"]
    
    def get_default_sheet(self):
        """
        Lấy sheet mặc định
        
        Returns:
            Dict sheet mặc định, None nếu không có
        """
        if self.config["default_sheet_id"]:
            return self.get_sheet(self.config["default_sheet_id"])
        return None
    
    def set_default_sheet(self, sheet_id):
        """
        Đặt sheet mặc định
        
        Args:
            sheet_id: ID của sheet
            
        Returns:
            True nếu thành công, False nếu thất bại
        """
        if self.get_sheet(sheet_id):
            self.config["default_sheet_id"] = sheet_id
            return self._save_config()
        
        print(f"[!] Không tìm thấy sheet ID: {sheet_id}")
        return False
    
    def mark_sheet_used(self, sheet_id):
        """
        Đánh dấu sheet vừa được sử dụng
        
        Args:
            sheet_id: ID của sheet
        """
        for sheet in self.config["sheets"]:
            if sheet["id"] == sheet_id:
                sheet["last_used"] = datetime.now().isoformat()
                self._save_config()
                break
    
    def extract_form_fields(self, form_url, timeout=10):
        """
        Tự động trích xuất entry fields từ Google Form bằng cách parse FB_PUBLIC_LOAD_DATA_
        Đây là phương pháp ổn định nhất để lấy Entry IDs.
        """
        try:
            # Convert form URL to viewform if needed
            if "/formResponse" in form_url:
                view_url = form_url.replace("/formResponse", "/viewform")
            elif "/viewform" in form_url:
                view_url = form_url
            else:
                if "/d/e/" in form_url:
                    view_url = form_url.split("?")[0]
                    if not view_url.endswith("/viewform"):
                        view_url = view_url.rstrip("/") + "/viewform"
                elif "/d/" in form_url:
                    view_url = form_url.replace("/edit", "/viewform")
                else:
                    view_url = form_url

            print(f"[*] Đang tải form từ: {view_url}")
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
            response = requests.get(view_url, headers=headers, timeout=timeout)
            response.raise_for_status()
            
            html_content = response.text
            fields = {}
            
            # --- PHƯƠNG PHÁP 1: Parse FB_PUBLIC_LOAD_DATA_ (Chính xác nhất) ---
            # Biến này chứa toàn bộ cấu trúc form trong script tag
            pattern = re.compile(r'var FB_PUBLIC_LOAD_DATA_ = (.*?);', re.DOTALL)
            match = pattern.search(html_content)
            
            if match:
                try:
                    data_str = match.group(1).strip()
                    # Đây là một mảng nested, dùng json.loads để parse
                    # Nhưng đôi khi nó có các giá trị null hoặc định dạng hơi lạ, cần cẩn thận
                    # Một số trường hợp dùng ,,,, thay vì ,null,null,null, - cần xử lý sơ bộ
                    data_str = re.sub(r',(?=,)', ',null', data_str)
                    form_data = json.loads(data_str)
                    
                    # Cấu trúc: form_data[1][1] thường chứa danh sách các câu hỏi
                    questions = form_data[1][1]
                    for q in questions:
                        if not q or len(q) < 5: continue
                        
                        label = (q[1] or "").lower() # Tiêu đề câu hỏi
                        entry_info = q[4] # Thông tin entry nằm ở index 4
                        
                        if not entry_info or not isinstance(entry_info, list): continue
                        
                        # Entry ID nằm ở index đầu tiên của mảng con đầu tiên trong entry_info
                        entry_id = f"entry.{entry_info[0][0]}"
                        
                        # Mapping logic (giữ nguyên logic cũ)
                        if 'author' in label or 'tác giả' in label:
                            fields['author_id'] = entry_id
                        elif 'title' in label or 'tiêu đề' in label:
                            fields['title'] = entry_id
                        elif 'slug' in label or 'đường dẫn' in label:
                            fields['slug'] = entry_id
                        elif 'content' in label or 'nội dung' in label:
                            fields['content'] = entry_id
                        elif 'publish' in label or 'xuất bản' in label:
                            fields['publish'] = entry_id
                        elif 'date' in label or 'ngày' in label:
                            # Với trường Date, nó có thể có nhiều entry IDs cho y/m/d
                            # Thường entry_info sẽ có nhiều phần tử
                            base_entry = entry_info[0][0]
                            fields['date_year'] = f"entry.{base_entry}_year"
                            fields['date_month'] = f"entry.{base_entry}_month"
                            fields['date_day'] = f"entry.{base_entry}_day"
                except Exception as e:
                    print(f"[!] Lỗi khi parse FB_PUBLIC_LOAD_DATA_: {e}")

            # --- PHƯƠNG PHÁP 2: Tìm thẻ input/textarea (Dự phòng) ---
            if len(fields) < 3: # Nếu phương pháp 1 không lấy được đủ fields
                print("[*] Thử phương pháp dự phòng: Tìm thẻ HTML trực tiếp...")
                soup = BeautifulSoup(html_content, 'html.parser')
                entry_elements = soup.find_all(['input', 'textarea'], attrs={'name': re.compile(r'^entry\.\d+')})
                
                for elem in entry_elements:
                    entry_name = elem.get('name')
                    label_text = ""
                    
                    if elem.get('aria-label'):
                        label_text = elem.get('aria-label').lower()
                    
                    if not label_text:
                        parent = elem.find_parent('div', class_=re.compile(r'.*question.*|.*item.*', re.I))
                        if parent:
                            label_elem = parent.find(['label', 'div', 'span'], class_=re.compile(r'.*label.*|.*title.*', re.I))
                            if label_elem:
                                label_text = label_elem.get_text().lower()
                    
                    if not label_text: continue
                    
                    if 'author' in label_text or 'tác giả' in label_text:
                        if 'author_id' not in fields: fields['author_id'] = entry_name
                    elif 'title' in label_text or 'tiêu đề' in label_text:
                        if 'title' not in fields: fields['title'] = entry_name
                    elif 'slug' in label_text or 'đường dẫn' in label_text:
                        if 'slug' not in fields: fields['slug'] = entry_name
                    elif 'content' in label_text or 'nội dung' in label_text:
                        if 'content' not in fields: fields['content'] = entry_name
                    elif 'publish' in label_text or 'xuất bản' in label_text:
                        if 'publish' not in fields: fields['publish'] = entry_name
                    elif 'date' in label_text or 'ngày' in label_text:
                        base_entry = entry_name.split('_')[0]
                        if 'year' in entry_name or 'năm' in label_text: fields['date_year'] = entry_name
                        elif 'month' in entry_name or 'tháng' in label_text: fields['date_month'] = entry_name
                        elif 'day' in entry_name or 'ngày' in label_text: fields['date_day'] = entry_name
                        else:
                            if 'date_year' not in fields: fields['date_year'] = f"{base_entry}_year"
                            if 'date_month' not in fields: fields['date_month'] = f"{base_entry}_month"
                            if 'date_day' not in fields: fields['date_day'] = f"{base_entry}_day"

            print(f"[*] Đã map được {len(fields)} fields")
            missing = [f for f in self.REQUIRED_FIELDS if f not in fields]
            
            # Convert formResponse URL
            if "/viewform" in view_url:
                form_response_url = view_url.replace("/viewform", "/formResponse")
            else:
                form_response_url = view_url.replace("/viewform", "/formResponse") # Fallback
            
            return {
                "fields": fields,
                "form_url": form_response_url,
                "missing_fields": missing
            }
            
        except requests.RequestException as e:
            print(f"[!] Lỗi tải form: {e}")
            return None
        except Exception as e:
            print(f"[!] Lỗi parse form: {e}")
            return None
    
    def validate_sheet_config(self, sheet_id):
        """
        Kiểm tra tính hợp lệ của sheet config
        
        Args:
            sheet_id: ID của sheet
            
        Returns:
            (is_valid, error_message)
        """
        sheet = self.get_sheet(sheet_id)
        if not sheet:
            return False, "Sheet không tồn tại"
        
        # Check required fields
        missing = [f for f in self.REQUIRED_FIELDS if f not in sheet["fields"]]
        if missing:
            return False, f"Thiếu fields: {', '.join(missing)}"
        
        # Check form URL
        if not sheet["form_url"]:
            return False, "Thiếu form URL"
        
        if "docs.google.com/forms" not in sheet["form_url"]:
            return False, "URL không phải Google Form"
        
        return True, "OK"


# Singleton instance
_manager_instance = None

def get_sheet_manager():
    """Lấy singleton instance của SheetManager"""
    global _manager_instance
    if _manager_instance is None:
        _manager_instance = SheetManager()
    return _manager_instance
