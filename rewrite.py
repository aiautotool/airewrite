import requests
import json
from datetime import datetime
import os
import time
import random
import re
import unicodedata


# Default paths (backward compatibility)
# Use user-writable directory
DATA_DIR = os.path.expanduser("~/.airewrite_data")
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)

LOG_FILE = os.path.join(DATA_DIR, "processed_titles.log")
PROGRESS_FILE = os.path.join(DATA_DIR, "progress.json")

from ai_agent import AIAgent
from wp_api_manager import get_wp_manager

def load_processed_titles(log_file=LOG_FILE):
    """Tải danh sách các tiêu đề đã được xử lý từ file log."""
    if not os.path.exists(log_file):
        return set()
    with open(log_file, "r", encoding="utf-8") as f:
        return set(line.strip() for line in f if line.strip())

def save_processed_title(title, log_file=LOG_FILE):
    """Lưu tiêu đề đã xử lý thành công vào file log."""
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(title + "\n")

def load_progress(progress_file=PROGRESS_FILE):
    """Tải tiến trình (số trang) từ file JSON."""
    if not os.path.exists(progress_file):
        return {"current_page": 1}
    try:
        with open(progress_file, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"   [!] Lỗi tải file tiến trình: {e}")
        return {"current_page": 1}

def save_progress(page, last_title="", progress_file=PROGRESS_FILE):
    """Lưu tiến trình hiện tại vào file JSON."""
    data = {
        "current_page": page,
        "last_title": last_title,
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    try:
        with open(progress_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
    except Exception as e:
        print(f"   [!] Lỗi lưu file tiến trình: {e}")

SYSTEM_PROMPT = (
    "CHỈ VIẾT BÀI MÀ KHÔNG NÓI GÌ THÊM. Tuyệt đối không chào hỏi, không dẫn dắt, không giải thích. "
    "Bạn là một chuyên gia sáng tạo nội dung cao cấp (Senior Editor & Rewriter). "
    "Nhiệm vụ của bạn là VIẾT LẠI (REWRITE) bài viết gốc thành một phiên bản mới tốt hơn, sâu sắc hơn, tuân thủ tiêu chí 'Helpful Content' nội dung không thay đổi ý nghĩa của bài viết gốc "
    "Mục tiêu: Nội dung mới phải Unique, văn phong tự nhiên, chuyên nghiệp, không bị phát hiện là AI.\n\n"
    "CẤU TRÚC BẮT BUỘC:\n"
    "- Bắt đầu bằng [startblog] và kết thúc bằng [endblog].\n"
    "- Tiêu đề (H1): Giữ nguyên tiêu đề gốc hoặc tinh chỉnh nhẹ cho hấp dẫn hơn nhưng vẫn sát nghĩa.\n"
    "- Mở đầu: Viết lại phần dẫn dắt một cách cuốn hút.\n"
    "- Thân bài: Tái cấu trúc lại các ý của bài gốc. Có thể bổ sung thêm ví dụ, phân tích sâu hơn nếu cần. Sử dụng H2, H3 hợp lý.\n"
    "- Kết bài: Tóm tắt và kêu gọi hành động (CTA) tự nhiên.\n\n"
    "HÌNH ẢNH MINH HỌA:\n"
    "Bài viết gốc có chứa các hình ảnh minh họa được đánh dấu bằng [IMG_1], [IMG_2], [IMG_3]...\n"
    "Bạn BẮT BUỘC phải giữ lại toàn bộ các thẻ này và chèn chúng vào các vị trí phù hợp trong bài viết mới để minh họa cho nội dung.\n"
    "Tuyệt đối không được bỏ sót hình ảnh nào.\n\n"
    "QUY TẮC REWRITE:\n"
    "1. **Không sao chép y nguyên**: Phải diễn đạt lại bằng ngôn từ mới.\n"
    "2. **Giữ nguyên thông tin cốt lõi**: Không bịa đặt thông tin sai lệch so với bài gốc.\n"
    "3. **Văn phong**: Tiếng Việt chuẩn, mượt mà, dễ đọc.\n"
    "4. **Format**: Sử dụng Markdown (Bold, Intalic, List, Table) để trình bày đẹp mắt.\n\n"
    "Output bắt buộc sử dụng markdown. Tuyệt đối không ghi rõ các mục như 'Mở bài', 'Thân bài', 'Kết bài' mà hãy viết liền mạch như một bài báo."
    "Quan trọng: Loại bỏ toàn bộ các thông tin liên hệ, nhận diện thương hiệu, số điện thoại, địa chỉ, tên công ty, tên blog, tên website có trong bài viết."
   
)

GEN_SYSTEM_PROMPT = (
    "CHỈ VIẾT BÀI MÀ KHÔNG NÓI GÌ THÊM. Tuyệt đối không chào hỏi, không dẫn dắt, không giải thích. "
    "Bạn là một chuyên gia sáng tạo nội dung cao cấp, am hiểu sâu sắc về tiêu chí 'Helpful Content' và 'E-E-A-T' của Google. "
    "Mục tiêu của bạn là tạo ra bài viết có giá trị thực sự, ưu tiên con người và xây dựng lòng tin, chứ không phải để thao túng công cụ tìm kiếm.\n\n"
    "CẤU TRÚC BẮT BUỘC:\n"
    "- Bắt đầu bằng [startblog] và kết thúc bằng [endblog]. Toàn bộ bài viết phải nằm giữa hai thẻ này.\n"
    "- Tiêu đề (H1): Phải hấp dẫn, hữu ích và mô tả đúng nội dung, tuyệt đối không giật tít phóng đại.\n"
    "- Mở đầu: Gây ấn tượng bằng cách nêu bật giá trị mà người đọc sẽ nhận được.\n"
    "- Thân bài: Chia nhỏ bằng các tiêu đề phụ (H2, H3). Sử dụng danh sách gạch đầu dòng, bảng so sánh hoặc các khối thông tin chuyên sâu để tăng tính dễ đọc và giá trị.\n"
    "- Kết bài: Tóm tắt ý chính và có lời kêu gọi hành động (CTA) tự nhiên.\n\n"
    "QUY TẮC CHẤT LƯỢNG (GOOGLE HELPFUL CONTENT):\n"
    "1. **Ưu tiên con người**: Nội dung phải giải quyết được vấn đề của người đọc hoặc giúp họ đạt được mục tiêu sau khi đọc xong.\n"
    "2. **Thể hiện E-E-A-T**: "
    "   - Kinh nghiệm (Experience): Viết như người đã từng trải nghiệm thực tế.\n"
    "   - Chuyên môn (Expertise): Cung cấp thông tin phân tích chuyên sâu, không chỉ tóm tắt lại từ nguồn khác.\n"
    "   - Độ tin cậy (Trustworthiness): Dẫn dắt thông tin minh bạch, rõ ràng.\n"
    "3. **Tính độc đáo**: Gia tăng thêm giá trị đáng kể, góc nhìn mới mẻ hoặc dữ liệu so sánh mà các trang khác không có.\n"
    "4. **Văn phong**: Tiếng Việt chuẩn, chuyên nghiệp nhưng gần gũi, không có lỗi chính tả, trình bày bài bản.\n"
    "Output bắt buộc sử dụng markdown. Tuyệt đối không ghi rõ các phần như 'Mở bài', 'Thân bài', 'Kết luận' hay các từ tương tự vậy, ngoài ra bắt buộc quan trọng không ghi rõ H2, H3 vào nội dung."
)

GEN_OUTLINE_PROMPT = (
    "Bạn là một chuyên gia lập kế hoạch nội dung (Content Architect). "
    "Nhiệm vụ của bạn là phân tích tiêu đề và tạo ra một Outline (Dàn ý) chi tiết, logic và hấp dẫn cho bài viết blog.\n\n"
    "YÊU CẦU OUTLINE:\n"
    "- Phải bao gồm các phần: Mở đầu, Các tiêu đề phụ (H2, H3), và Kết luận.\n"
    "- Mỗi phần phải có mô tả ngắn gọn về nội dung cần viết.\n"
    "- Đảm bảo cấu trúc chuẩn SEO và hướng tới người đọc (Helpful Content).\n"
    "- Chỉ trả về Outline dưới dạng Markdown, không nói thêm lời dẫn."
)

GEN_CONTENT_PROMPT = (
    "CHỈ VIẾT BÀI MÀ KHÔNG NÓI GÌ THÊM. Tuyệt đối không chào hỏi, không dẫn dắt.\n"
    "Bạn là một chuyên gia viết lách (Senior Content Writer). "
    "Hãy dựa vào OUTLINE được cung cấp để viết một bài blog hoàn chỉnh, chuyên sâu và hấp dẫn.\n\n"
    "CẤU TRÚC BẮT BUỘC:\n"
    "- Bắt đầu bằng [startblog] và kết thúc bằng [endblog].\n"
    "- Viết chi tiết từng phần trong outline.\n"
    "- Sử dụng ngôn từ chuyên nghiệp, giàu cảm xúc và đáng tin cậy (E-E-A-T).\n"
    "- Trình bày bài bản bằng Markdown.\n\n"
    "HÃY VIẾT NỘI DUNG CHẤT LƯỢNG CAO, ƯU TIÊN GIÁ TRỊ CHO ĐỘC GIẢ."
)

TITLE_GEN_PROMPT = (
    "Bạn là một chuyên gia lập kế hoạch nội dung. Hãy tạo ra 50 tiêu đề bài viết blog hấp dẫn, hữu ích và chuẩn SEO. "
    "Yêu cầu:\n"
    "1. Tiêu đề phải mang tính tích cực, truyền cảm hứng hoặc giải quyết một vấn đề cụ thể.\n"
    "2. Chỉ trả về danh sách các tiêu đề, mỗi tiêu đề một dòng, không đánh số, không thêm lời giải thích nào khác.\n"
    "3. Đảm bảo các tiêu đề ĐA DẠNG và KHÁC BIỆT."
)

def select_author(title):
    # Thử gọi AI với fallback
    return AIAgent.select_author(title)

def strip_blog_tags(text):
    return AIAgent.strip_blog_tags(text)

def call_ai_agent(prompt, system_prompt=None, temperature=0.7, max_tokens=8000, model=None):
    return AIAgent.call_ai_agent(prompt, system_prompt, temperature, max_tokens, model=model)

def slugify(text):
    return AIAgent.slugify(text)

def strip_html_tags(text):
    """Xóa thẻ HTML đơn giản khỏi nội dung source để AI dễ đọc hơn."""
    clean = re.compile('<.*?>')
    return re.sub(clean, '', text)

def extract_images_to_placeholders(html_content):
    """
    Tìm các thẻ img trong HTML, thay thế bằng placeholder [IMG_n] và trả về dict map.
    """
    images = {}
    counter = 1
    
    def replace_match(match):
        nonlocal counter
        img_tag = match.group(0)
        # Tạo placeholder có khoảng trắng để AI dễ nhận diện
        placeholder = f" [IMG_{counter}] " 
        key = f"[IMG_{counter}]"
        images[key] = img_tag
        counter += 1
        return placeholder

    # Regex bắt thẻ img (cơ bản)
    processed_html = re.sub(r'<img[^>]*?/?>', replace_match, html_content, flags=re.IGNORECASE | re.DOTALL)
    return processed_html, images

def restore_images_from_placeholders(content, images_dict):
    """
    Thay thế các placeholder [IMG_n] trong content bằng thẻ img dạng markdown ![alt](url "title").
    """
    year_pattern = r'\b20(1[0-9]|2[0-5])\b' 

    for key, img_tag in images_dict.items():
        # Lấy src, alt và title từ thẻ img gốc (linh hoạt hơn với dấu ngoặc và khoảng trắng)
        src_match = re.search(r'src\s*=\s*(?:["\']([^"\']*)["\']|([^\s>]+))', img_tag, re.IGNORECASE)
        alt_match = re.search(r'alt\s*=\s*(?:["\']([^"\']*)["\']|([^\s>]+))', img_tag, re.IGNORECASE)
        title_match = re.search(r'title\s*=\s*(?:["\']([^"\']*)["\']|([^\s>]+))', img_tag, re.IGNORECASE)
        
        src = (src_match.group(1) or src_match.group(2) or "") if src_match else ""
        alt = (alt_match.group(1) or alt_match.group(2) or "") if alt_match else ""
        title = (title_match.group(1) or title_match.group(2) or "") if title_match else ""
        
        # Cập nhật năm trong alt và title
        if alt:
            alt = re.sub(year_pattern, "2026", alt)
        if title:
            title = re.sub(year_pattern, "2026", title)
        
        # Format markdown: ![alt](src "title")
        if title:
            markdown_img = f"![{alt}]({src} \"{title}\")"
        else:
            markdown_img = f"![{alt}]({src})"

        # Thay thế placeholder (hỗ trợ cả trường hợp bị kèm markdown khác như bold)
        # Sử dụng escape cho key vì key có thể chứa [ và ]
        escaped_key = re.escape(key)
        # Regex tìm placeholder, có thể bao quanh bởi dấu sao hoặc gạch dưới
        pattern = rf'[\*_]*{escaped_key}[\*_]*'
        content = re.sub(pattern, f"\n\n{markdown_img}\n\n", content)
        
    return content

def aiautotool_pingbackstatus(title, content, author_id=1, dest_config=None, sheet_config=None):
    """
    Gửi dữ liệu bài viết đến đích (Google Form hoặc WordPress API)
    
    Args:
        title: Tiêu đề bài viết
        content: Nội dung bài viết
        author_id: ID tác giả (hoặc mapping tương ứng)
        dest_config: Dict dạng {"type": "sheet", "config": ...} hoặc {"type": "wp", "config": ...}
        sheet_config: (Deprecated) dùng để tương thích ngược
    
    Returns:
        HTTP status code hoặc None nếu lỗi
    """
    # 1. Routing logic
    if dest_config:
        dest_type = dest_config.get("type")
        config = dest_config.get("config")
        
        if dest_type == "wp":
            # Direct WordPress API Mode
            wp_manager = get_wp_manager()
            cat_id = config.get("category_id")
            res = wp_manager.post_article(
                config, 
                title, 
                content, 
                slug=AIAgent.slugify(title),
                status="publish", # Mặc định đăng bài luôn
                categories=[cat_id] if cat_id else None,
                author_id=author_id
            )
            if res.get("success"):
                print(f"   [WP-API] Đăng bài thành công! ID: {res.get('id')}")
                return res.get("status")
            else:
                print(f"   [WP-API] Lỗi: {res.get('error')}")
                return res.get("status")
        
        # Nếu là sheet, gán vào sheet_config để xử lý bên dưới
        if dest_type == "sheet":
            sheet_config = config

    # 2. Google Form Mode (Legacy / Default)
    publish = 1
    today = datetime.now()
    year = today.year 
    month = today.month
    day = today.day
    
    # Backward compatibility: Nếu không có sheet_config, dùng hardcoded
    if sheet_config is None:
        form_url = "https://docs.google.com/forms/u/1/d/e/1FAIpQLSf3QvNGVHgI6GjVEt9xNEzS6kix-vc_kkVDhHAhEdWBWUbf0A/formResponse"
        fields = {
            "author_id": "entry.1171459721",
            "title": "entry.1177795647",
            "slug": "entry.327767971",
            "content": "entry.634618594",
            "publish": "entry.1496062259",
            "date_year": "entry.266364423_year",
            "date_month": "entry.266364423_month",
            "date_day": "entry.266364423_day"
        }
    else:
        form_url = sheet_config.get("form_url")
        fields = sheet_config.get("fields", {})
        
        if not form_url or not fields:
            print("   [PINGBACK] Lỗi: Sheet config không hợp lệ")
            return None
   
    # Dữ liệu gửi
    content = content.replace("[endblog]", "").replace("[Endblog]", "")
    slug = slugify(title)
    
    # Build form_data dynamically từ fields mapping
    form_data = {}
    
    if "author_id" in fields:
        form_data[fields["author_id"]] = str(author_id)
    
    if "title" in fields:
        form_data[fields["title"]] = title
    
    if "slug" in fields:
        form_data[fields["slug"]] = slug
    
    if "content" in fields:
        form_data[fields["content"]] = content
    
    if "publish" in fields:
        form_data[fields["publish"]] = str(publish)
    
    if "date_year" in fields:
        form_data[fields["date_year"]] = str(year)
    
    if "date_month" in fields:
        form_data[fields["date_month"]] = str(month)
    
    if "date_day" in fields:
        form_data[fields["date_day"]] = str(day)
    
    try:
        response = requests.post(form_url, data=form_data, timeout=10)
        print(f"   [PINGBACK] Status Code: {response.status_code}")
        return response.status_code
    except Exception as e:
        print(f"   [PINGBACK] Lỗi gửi form: {e}")
        return None

# --- AI FUNCTIONS (REWRITE MODE) ---

def rewrite_content_with_fallback(title, source_content, max_retries=3, system_prompt=None, model=None):
    # Prepare Content
    # 1. Extract Images
    content_with_placeholders, img_map = extract_images_to_placeholders(source_content)
    
    # 2. Year Replacement (Legacy/User requested)
    year_pattern = r'\b20(1[0-9]|2[0-5])\b' 
    clean_title = re.sub(year_pattern, "2026", title)
    prepared_content = re.sub(year_pattern, "2026", content_with_placeholders)
    
    # 3. Strip HTML
    prepared_content = strip_html_tags(prepared_content)
    if len(prepared_content) > 20000:
        prepared_content = prepared_content[:20000] + "...(truncated)..."

    final_new_content = None

    for attempt in range(1, max_retries + 1):
        print(f"\n--- Đang viết lại nội dung cho: {clean_title} (Lần thử {attempt}/{max_retries}) ---")
        
        user_prompt = f"Tiêu đề: {clean_title}\n\nNội dung gốc tham khảo:\n{prepared_content}\n\nYêu cầu: Hãy viết lại bài viết trên dựa theo tiêu đề và nội dung gốc, tuân thủ System Prompt."
        
        # Use provided system_prompt or global default
        sp = system_prompt if system_prompt else SYSTEM_PROMPT
        
        content = call_ai_agent(user_prompt, sp, model=model)
        if content:
            print(f"=> Thành công với AI Agent ở lần thử {attempt}!")
            final_new_content = content
            break

        print(f"   [!] Lần thử {attempt} thất bại.")
        if attempt < max_retries:
            wait_time = attempt * 5
            print(f"   => Đang đợi {wait_time} giây trước khi thử lại...")
            time.sleep(wait_time)

    if final_new_content:
        # 4. Restore Images
        if img_map:
            print("   => Đang khôi phục hình ảnh gốc vào bài viết mới...")
            final_new_content = restore_images_from_placeholders(final_new_content, img_map)
        return final_new_content

    print(f"   [!] Tất cả {max_retries} lần thử đều thất bại.")
    return None

def generate_new_content_with_fallback(title, max_retries=3, model=None, multi_step=False):
    for attempt in range(1, max_retries + 1):
        print(f"\n--- Đang tạo nội dung mới cho: {title} (Lần thử {attempt}/{max_retries}) ---")
        
        if multi_step:
            # Step 1: Outline
            print("   [Step 1] Đang tạo Outline...")
            outline = call_ai_agent(title, GEN_OUTLINE_PROMPT, model=model)
            if not outline:
                print(f"   [!] Thất bại khi tạo Outline ở lần thử {attempt}.")
                continue
                
            # Step 2: Content
            print("   [Step 2] Đang viết nội dung dựa trên Outline...")
            content = call_ai_agent(f"Dàn ý:\n{outline}\n\nTiêu đề: {title}", GEN_CONTENT_PROMPT, model=model)
        else:
            # Direct Generation
            content = call_ai_agent(f"Hãy viết bài blog về chủ đề: {title}", GEN_SYSTEM_PROMPT, model=model)

        if content:
            print(f"=> Thành công ở lần thử {attempt}!")
            return content

        if attempt < max_retries:
            wait_time = attempt * 5
            time.sleep(wait_time)

    return None

def auto_generate_titles(topic_prompt, model=None, exclude_titles=None):
    print(f"\n--- Đang tự động tạo thêm tiêu đề mới cho chủ đề: {topic_prompt} ---")
    prompt = f"{TITLE_GEN_PROMPT}\n\nChủ đề: {topic_prompt}"
    
    if exclude_titles and len(exclude_titles) > 0:
        # Lấy tối đa 50 tiêu đề gần nhất để tránh (giảm token usage)
        avoid_list = list(exclude_titles)[-50:]
        avoid_text = "\n- ".join(avoid_list)
        prompt += f"\n\nLƯU Ý QUAN TRỌNG: Tuyệt đối KHÔNG được trùng với các tiêu đề dưới đây:\n- {avoid_text}"

    new_titles_text = call_ai_agent(prompt, model=model, temperature=0.9) # Tăng temperature để sáng tạo hơn
    
    if not new_titles_text:
        return []

    raw_titles = [line.strip() for line in new_titles_text.split('\n') if line.strip()]
    cleaned = []
    for t in raw_titles:
        # Remove numbering 1. 2. etc
        t = re.sub(r'^\d+[\.\)]\s*', '', t)
        # Remove quotes if any
        t = t.strip('"').strip("'")
        
        if t and (not exclude_titles or t not in exclude_titles):
            cleaned.append(t)
            
    return cleaned

    return cleaned

def generate_titles_from_topic(topic, model=None, exclude_titles=None):
    """
    Wrapper để tạo tiêu đề từ 1 topic, dùng cho app UI.
    """
    return auto_generate_titles(topic, model=model, exclude_titles=exclude_titles)

def fetch_wp_posts(page=1, per_page=10, base_url="https://healthmart.vn/wp-json/wp/v2/posts"):
    url = f"{base_url}?page={page}&per_page={per_page}"
    print(f"\n>>> Đang tải danh sách bài viết trang {page} từ {url} ...")
    
    try:
        response = requests.get(url, timeout=30)
        if response.status_code == 200:
            posts = response.json()
            print(f"   => Tìm thấy {len(posts)} bài viết.")
            return posts
        elif response.status_code == 400:
            print("   => Đã hết bài viết (Page out of bounds).")
            return []
        else:
            print(f"   => Lỗi tải trang: {response.status_code}")
            return []
    except Exception as e:
        print(f"   => Lỗi kết nối crawl: {e}")
        return []

# --- JSONL CONSUMER FOR SCRAPY ---

def fetch_from_jsonl(file_path):
    """
    Generator đọc từng dòng từ file jsonl.
    Trả về dict bài viết hoặc None nếu lỗi parsing.
    """
    if not os.path.exists(file_path):
        return

    with open(file_path, "r", encoding="utf-8") as f:
        # Đọc tất cả dòng (cẩn thận memory, nhưng text thường nhỏ)
        # Hoặc đọc từng dòng
        for line in f:
            line = line.strip()
            if not line: continue
            try:
                data = json.loads(line)
                # Chuẩn hóa format để giống WP API response
                # WP: title -> rendered, content -> rendered
                if "title" in data and isinstance(data["title"], str):
                    data["title"] = {"rendered": data["title"]}
                if "content" in data and isinstance(data["content"], str):
                    data["content"] = {"rendered": data["content"]}
                yield data
            except:
                continue

if __name__ == "__main__":
    print("\n" + "="*50)
    print("BẮT ĐẦU CRAWL VÀ REWRITE TỪ BLOGTOC.COM (GIỮ LẠI HÌNH ẢNH)")
    print("="*50)

    # Tải tiến trình đã lưu
    progress = load_progress()
    current_page = progress.get("current_page", 1)
    last_title = progress.get("last_title", "")
    
    print(f"[*] Tiếp tục từ trang: {current_page}")
    if last_title:
        print(f"[*] Bài viết cuối cùng được xử lý: {last_title}")
    
    while True:
        posts = fetch_wp_posts(page=current_page)
        
        if not posts:
            print("\n>>> Đã hoàn thành hoặc không lấy được thêm bài viết. Kết thúc chương trình.")
            break
            
        processed_titles = load_processed_titles()
        
        count_processed_in_page = 0
        
        for post in posts:
            title = post.get("title", {}).get("rendered", "")
            content_html = post.get("content", {}).get("rendered", "")
            
            import html
            title = html.unescape(title)
            
            if not title: continue
            if title in processed_titles:
                count_processed_in_page += 1
                continue
            
            # (Năm cũ sẽ được thay thế sau khi tách hình ảnh ở Bước 1.5)

            print(f"\n--- Đang xử lý: {title} ---")
            
            # --- BƯỚC 1: Tách hình ảnh và thay bằng placeholder ---
            content_with_placeholders, img_map = extract_images_to_placeholders(content_html)
            
            # --- BƯỚC 1.5: Thay thế các năm cũ thành 2026 (sau khi đã tách hình ảnh) ---
            year_pattern = r'\b20(1[0-9]|2[0-5])\b' 
            title = re.sub(year_pattern, "2026", title)
            content_with_placeholders = re.sub(year_pattern, "2026", content_with_placeholders)

            if img_map:
                print(f"   => Tìm thấy {len(img_map)} hình ảnh trong bài viết gốc.")
            else:
                print("   => Không tìm thấy hình ảnh nào.")
                
            # --- BƯỚC 2: Làm sạch code HTML thừa (chỉ giữ lại placeholder và text) ---
            clean_source_content = strip_html_tags(content_with_placeholders)
            
            if len(clean_source_content) > 20000:
                 clean_source_content = clean_source_content[:20000] + "...(đã cắt bớt)..."

            # --- BƯỚC 3: Rewrite nội dung ---
            new_content = rewrite_content_with_fallback(title, clean_source_content)
            
            if new_content:
                print(f"   => Rewrite thành công ({len(new_content)} ký tự)")
                
                # --- BƯỚC 4: Khôi phục hình ảnh từ placeholder ---
                if img_map:
                    print("   => Đang khôi phục hình ảnh gốc vào bài viết mới...")
                    new_content = restore_images_from_placeholders(new_content, img_map)
                
                # Xác định tác giả
                author_id = select_author(title)
                author_name = next((a['name'] for a in AIAgent.AUTHORS if a['id'] == author_id), "N/A")
                print(f"   => Đã chọn tác giả ID: {author_id} ({author_name})")

                # --- BƯỚC 5: Gửi form ---
                print("   => Đang gửi pingback...")
                status = aiautotool_pingbackstatus(title, new_content, author_id)
                
                if status == 200:
                    save_processed_title(title)
                    processed_titles.add(title) 
                else:
                    print(f"   [!] Gửi form thất bại (Status: {status})")
            else:
                print("   [!] Rewrite thất bại. Bỏ qua bài này.")
            
            time.sleep(random.randint(2, 5))
        
        current_page += 1
        save_progress(current_page)
        print(f"\n>>> Hoàn thành trang {current_page - 1}. Nghỉ 5 giây trước khi sang trang {current_page}...")
        time.sleep(5)