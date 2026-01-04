import requests
import json
from datetime import datetime
import os
import time
import openai
import re
import unicodedata
import random

# Đường dẫn file lưu trữ các tiêu đề đã xử lý
LOG_FILE = os.path.join(os.path.dirname(__file__), "processed_titles.log")

from ai_agent import AIAgent

def load_processed_titles():
    """Tải danh sách các tiêu đề đã được xử lý từ file log."""
    if not os.path.exists(LOG_FILE):
        return set()
    with open(LOG_FILE, "r", encoding="utf-8") as f:
        return set(line.strip() for line in f if line.strip())

def save_processed_title(title):
    """Lưu tiêu đề đã xử lý thành công vào file log."""
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(title + "\n")

SYSTEM_PROMPT = (
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
    "5. **Tự đánh giá**: Trước khi xuất bài, hãy tự hỏi: 'Nếu là người đọc, tôi có muốn chia sẻ bài này cho bạn bè không? Nội dung này có đủ tốt để được trích dẫn trong một ấn phẩm uy tín không?'\n\n"
    "HÃY SUY NGHĨ VÀ TÌM KIẾM THÔNG TIN LIÊN QUAN TRƯỚC KHI VIẾT ĐỂ ĐẢM BẢO TÍNH XÁC THỰC VÀ CHUYÊN SÂU. output bắt buộc sử dụng markdown mà không phải là các thẻ H, CTA"
    "Tuyệt đối không ghi rõ các mở bài,Mở đầu, kết bài, Lời kết,Tổng kết và hành động thực tế hay các từ đồng nghĩa,  lời kêu gọi mà cần viết như một bài văn , người dùng đọc sẽ tự hiểu từng phần. mở bài thì chắc chắn là lời dẫn đầu mở bài rồi, không được ghi rõ ## Mở đầu, không được ghi rõ kết bài, một bài văn tuyệt đối sẽ không có những mục như vậy "
)

# --- STYLE 2: MULTI-STEP GENERATION (OUTLINE FIRST) ---
SYSTEM_PROMPT_STYLE2_OUTLINE = (
    "Bạn là một chuyên gia lập kế hoạch nội dung (Content Architect). "
    "Nhiệm vụ của bạn là phân tích tiêu đề và tạo ra một Outline (Dàn ý) chi tiết, logic và hấp dẫn cho bài viết blog.\n\n"
    "YÊU CẦU OUTLINE:\n"
    "- Phải bao gồm các phần: Mở đầu, Các tiêu đề phụ (H2, H3), và Kết luận.\n"
    "- Mỗi phần phải có mô tả ngắn gọn về nội dung cần viết.\n"
    "- Đảm bảo cấu trúc chuẩn SEO và hướng tới người đọc (Helpful Content).\n"
    "- Chỉ trả về Outline dưới dạng Markdown, không nói thêm lời dẫn."
    "Tuyệt đối không ghi rõ các mở bài,Mở đầu, kết bài, Lời kết, Tổng kết và hành động thực tế hay các từ đồng nghĩa,  lời kêu gọi mà cần viết như một bài văn , người dùng đọc sẽ tự hiểu từng phần. mở bài thì chắc chắn là lời dẫn đầu mở bài rồi, không được ghi rõ ## Mở đầu, không được ghi rõ kết bài, một bài văn tuyệt đối sẽ không có những mục như vậy "
)

SYSTEM_PROMPT_STYLE2_CONTENT = (
    "CHỈ VIẾT BÀI MÀ KHÔNG NÓI GÌ THÊM. Tuyệt đối không chào hỏi, không dẫn dắt.\n"
    "Bạn là một chuyên gia viết lách (Senior Content Writer). "
    "Hãy dựa vào OUTLINE được cung cấp để viết một bài blog hoàn chỉnh, chuyên sâu và hấp dẫn.\n\n"
    "CẤU TRÚC BẮT BUỘC:\n"
    "- Bắt đầu bằng [startblog] và kết thúc bằng [endblog].\n"
    "- Viết chi tiết từng phần trong outline.\n"
    "- Sử dụng ngôn từ chuyên nghiệp, giàu cảm xúc và đáng tin cậy (E-E-A-T).\n"
    "- Trình bày bài bản bằng Markdown.\n\n"
    "HÃY VIẾT NỘI DUNG CHẤT LƯỢNG CAO, ƯU TIÊN GIÁ TRỊ CHO ĐỘC GIẢ."
    "Tuyệt đối không ghi rõ các mở bài,Mở đầu, kết bài, Lời kết, Tổng kết và hành động thực tế hay các từ đồng nghĩa,  lời kêu gọi mà cần viết như một bài văn , người dùng đọc sẽ tự hiểu từng phần. mở bài thì chắc chắn là lời dẫn đầu mở bài rồi, không được ghi rõ ## Mở đầu, không được ghi rõ kết bài, một bài văn tuyệt đối sẽ không có những mục như vậy "
)

TITLE_GENERATION_PROMPT = (
    "Bạn là một chuyên gia lập kế hoạch nội dung. Hãy tạo ra 100 tiêu đề bài viết blog hấp dẫn, hữu ích và chuẩn SEO. "
    "Các tiêu đề phải xoay quanh các chủ đề: phát triển bản thân, kỹ năng sống, tâm lý, động lực, và những bài học cuộc sống. "
    "Yêu cầu:\n"
    "1. Tiêu đề phải mang tính tích cực, truyền cảm hứng hoặc giải quyết một vấn đề cụ thể.\n"
    "2. Không trùng lặp với các phong cách tiêu đề cũ nhưng vẫn giữ được sự tinh tế.\n"
    "3. Chỉ trả về danh sách các tiêu đề, mỗi tiêu đề một dòng, không đánh số, không thêm lời giải thích nào khác."
    "4. Mỗi tiêu đề đều bắt đầu bằng: Những câu nói tích cực về "
    
)

def select_author(title):
    # Thử gọi AI với fallback
    return AIAgent.select_author(title)

def strip_blog_tags(text):
    return AIAgent.strip_blog_tags(text)

def slugify(text):
    return AIAgent.slugify(text)

def aiautotool_pingbackstatus(title, content, author_id=1):
    publish = 1
    
    # Ngày hiện tại được đặt cố định là 20/12/2025 theo yêu cầu
    today = datetime.now()
    year = today.year      # 2025
    month = today.month    # 12
    day = today.day        # 20
    
    # URL của Google Form
    form_url = "https://docs.google.com/forms/d/1QGOhe7-LRXLUMpxcjqrhlt5jN56dx0PPcV7D7y08JIM/formResponse"
    form_url = "https://docs.google.com/forms/u/1/d/e/1FAIpQLSf3QvNGVHgI6GjVEt9xNEzS6kix-vc_kkVDhHAhEdWBWUbf0A/formResponse"
    # Dữ liệu gửi
    # URLs and strings cleaning
    content = content.replace("[endblog]", "").replace("[Endblog]", "")
    slug = slugify(title)
    authorid = author_id
    form_data = {
        "entry.1171459721": authorid,
        "entry.1177795647": title,
        "entry.327767971": slug,
        "entry.634618594": content,
        "entry.1496062259": str(publish),
        "entry.266364423_year": str(year),
        "entry.266364423_month": str(month),
        "entry.266364423_day": str(day),
        "entry.1171459721": str(author_id)
    }

    #  form_data = {
    #     "entry.1171459721": authorid,
    #     "entry.1177795647": title,
    #     "entry.327767971": slug,
    #     "entry.634618594": content,
    #     "entry.1496062259": str(publish),
    #     "entry.266364423_year": str(year),
    #     "entry.266364423_month": str(month),
    #     "entry.266364423_day": str(day),
    #     "entry.1171459721": str(author_id)
    # }
    
    try:
        # Gửi POST request
        response = requests.post(form_url, data=form_data, timeout=10)
        
        # In ra kết quả để xem thử
        print("Status Code:", response.status_code)
        if response.status_code == 200:
            print("Gửi pingback thành công!")
        elif response.status_code == 0:
            print("Không nhận được phản hồi từ Google (có thể bị chặn hoặc form không tồn tại).")
        else:
            print(f"Lỗi khi gửi: {response.status_code}")
            print("Nội dung phản hồi:", response.text[:500])  # In một phần để debug
            
        return response.status_code
        
    except requests.exceptions.Timeout:
        print("Lỗi: Request timeout (quá thời gian chờ)")
        return None
    except requests.exceptions.ConnectionError:
        print("Lỗi: Không thể kết nối đến Google Forms")
        return None
    except requests.exceptions.RequestException as e:
        print(f"Lỗi kết nối khác: {e}")
        return None

def call_ai_agent(prompt, system_prompt=None, temperature=0.7, max_tokens=4000):
    return AIAgent.call_ai_agent(prompt, system_prompt, temperature, max_tokens)

def generate_content_with_fallback(title):
    print(f"\n--- Đang tạo nội dung cho: {title} ---")
    content = call_ai_agent(f"Tiêu đề bài viết: {title}", SYSTEM_PROMPT)
    if content:
        print("=> Thành công với AI Agent!")
        return content
    
    print(f"   [!] Tất cả AI đều thất bại.")
    return None

def generate_content_multi_step(title):
    print(f"\n--- [STYLE 2] Đang tạo nội dung đa bước cho: {title} ---")
    
    # Bước 1: Tạo Outline
    print("Step 1: Đang tạo Outline...")
    outline = call_ai_agent(title, SYSTEM_PROMPT_STYLE2_OUTLINE)
    
    if not outline:
        print(f"   [!] Thất bại khi tạo Outline.")
        return None
        
    print(f"   => Outline đã sẵn sàng ({len(outline)} ký tự)")
    
    # Bước 2: Viết Content dựa trên Outline
    print("Step 2: Đang viết nội dung chi tiết dựa trên Outline...")
    content = call_ai_agent(f"Dàn ý:\n{outline}\n\nTiêu đề: {title}", SYSTEM_PROMPT_STYLE2_CONTENT)
    
    if content:
        print(f"   => Thành công với Style 2!")
        return content
        
    return None

def generate_content_random(title):
    # Lựa chọn ngẫu nhiên phong cách viết: 50/50
    style = random.choice(["STYLE_1", "STYLE_2"])
    
    if style == "STYLE_1":
        print("\n--- [STYLE 1] Đang tạo nội dung theo cách cũ (Direct) ---")
        return generate_content_with_fallback(title)
    else:
        return generate_content_multi_step(title)

def auto_generate_titles(existing_titles_set, processed_titles_set):
    print("\n--- Đang tự động tạo thêm tiêu đề mới... ---")
    
    # Thử gọi AI Agent để lấy danh sách tiêu đề mới
    new_titles_text = call_ai_agent(TITLE_GENERATION_PROMPT, temperature=0.8, max_tokens=2048)
    
    if not new_titles_text:
        print("   [!] Không thể tạo tiêu đề mới từ bất kỳ AI nào.")
        return []

    # Xử lý văn bản trả về thành danh sách tiêu đề
    raw_titles = [line.strip() for line in new_titles_text.split('\n') if line.strip()]
    
    # Lọc bỏ trùng lặp
    unique_new_titles = []
    for t in raw_titles:
        if t not in existing_titles_set and t not in processed_titles_set and t not in unique_new_titles:
            unique_new_titles.append(t)
    
    if unique_new_titles:
        print(f"   => Đã tạo được {len(unique_new_titles)} tiêu đề mới không trùng lặp.")
        titles_file = os.path.join(os.path.dirname(__file__), "titles.txt")
        with open(titles_file, "a", encoding="utf-8") as f:
            for t in unique_new_titles:
                f.write(t + "\n")
        return unique_new_titles
    else:
        print("   [!] Không có tiêu đề mới nào hợp lệ được tạo ra.")
        return []

# ================== CHƯƠNG TRÌNH CHÍNH ==================
if __name__ == "__main__":
    # Đường dẫn file titles.txt nằm cùng thư mục với script này
    titles_file = os.path.join(os.path.dirname(__file__), "titles.txt")
    
    print("\n" + "="*50)
    print("BẮT ĐẦU CHẾ ĐỘ TỰ ĐỘNG CHẠY LIÊN TỤC (CONTINUOUS MODE)")
    print("="*50)

    while True:
        # Đảm bảo file tồn tại
        if not os.path.exists(titles_file):
            print(f"[!] Không tìm thấy file: {titles_file}. Đang tạo file mới...")
            with open(titles_file, "w", encoding="utf-8") as f:
                pass
            titles = []
        else:
            with open(titles_file, "r", encoding="utf-8") as f:
                titles = [line.strip() for line in f if line.strip()]
            
        # Tải danh sách đã xử lý
        processed_titles = load_processed_titles()
        
        # Kiểm tra tiêu đề chưa xử lý
        unprocessed_titles = [t for t in titles if t not in processed_titles]
        
        if not unprocessed_titles:
            print("\n--- [!] Tất cả tiêu đề đã xử lý hoặc file rỗng. Đang tạo tiêu đề mới... ---")
            new_titles = auto_generate_titles(set(titles), processed_titles)
            if new_titles:
                # Sau khi tạo thành công, quay lại đầu vòng lặp để reload và xử lý
                print(f"   => Đã nạp thêm {len(new_titles)} tiêu đề. Bắt đầu xử lý ngay...")
                continue
            else:
                print("   [!] Không thể tạo thêm tiêu đề. Sẽ thử lại sau 60 giây...")
                time.sleep(60)
                continue

        print(f"\n>>> Tìm thấy {len(unprocessed_titles)} tiêu đề mới cần xử lý.")
        
        success_count = 0
        fail_count = 0
        
        for i, title in enumerate(unprocessed_titles, 1):
            # Kiểm tra lại lần nữa trong log thực tế để tránh trùng lặp
            if title in load_processed_titles():
                continue
                
            print(f"\n--- [{i}/{len(unprocessed_titles)}] Đang xử lý: {title} ---")
            
            generated_content = generate_content_random(title)
            
            if generated_content:
                print(f"   => Đã tạo nội dung thành công ({len(generated_content)} ký tự)")
                
                # Xác định tác giả
                author_id = select_author(title)
                author_name = next((a['name'] for a in AIAgent.AUTHORS if a['id'] == author_id), "N/A")
                print(f"   => Đã chọn tác giả ID: {author_id} ({author_name})")

                # Gửi pingback lên Google Form
                print("   => Đang gửi pingback lên Google Form...")
                status = aiautotool_pingbackstatus(title, generated_content, author_id)
                
                if status == 200:
                    success_count += 1
                    save_processed_title(title)
                else:
                    fail_count += 1
            else:
                print(f"   [!] Thất bại: Không thể tạo nội dung cho tiêu đề này.")
                fail_count += 1
            
            # Tạm nghỉ giữa các lần gửi
            wait_time = random.randint(3, 7)
            print(f"   --- Đợi {wait_time} giây trước nhiệm vụ tiếp theo... ---")
            time.sleep(wait_time)
            
        print(f"\n>>> Hoàn thành đợt xử lý hiện tại. (Thành công: {success_count}, Thất bại: {fail_count})")
        print(">>> Đang nghỉ 10 giây trước khi kiểm tra đợt tiếp theo...")
        time.sleep(10)