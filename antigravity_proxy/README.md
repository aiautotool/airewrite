# 🛰️ Antigravity Proxy Server

Antigravity Proxy là một máy chủ trung gian (Proxy) hiệu năng cao được viết bằng Python, thiết kế để kết nối và tối ưu hóa việc sử dụng các API nội bộ của Google Cloud Code (`cloudcode-pa.googleapis.com`). Máy chủ này đóng vai trò là "xương sống" cho các ứng dụng AI Agent, cung cấp khả năng quản lý tài khoản, vượt rào cản hạn mức và hỗ trợ đa giao thức.

---

## 🏗️ Kiến trúc & Cơ chế hoạt động

### 1. Quản lý Tài khoản (Account Management)
*   **Lưu trữ**: Các tài khoản được lưu trữ cục bộ dưới dạng file JSON trong thư mục `accounts/`.
*   **Định dạng**: Mỗi file chứa `refresh_token`, `access_token`, `project_id`, và dữ liệu `quota`.
*   **Bảo mật**: Token được làm mới tự động thông qua giao thức OAuth2 khi gần hết hạn (buffer 5 phút).

### 2. Điều phối thông minh (Routing & Load Balancing)
*   Khi có yêu cầu gửi đến, Proxy sẽ quét toàn bộ Pool tài khoản.
*   **Retry Loop**: Nếu một tài khoản gặp lỗi hoặc hết quota, hệ thống sẽ tự động thử lại với tài khoản khả dụng tiếp theo.
*   **Xáo trộn (Shuffle)**: Các tài khoản được xáo trộn ngẫu nhiên cho mỗi phiên làm việc để đảm bảo tải được phân phối đều.

### 3. Proxy API nội bộ
Proxy hỗ trợ các endpoint chính của Google Internal:
*   `generateContent` & `streamGenerateContent`
*   `loadCodeAssist` (để lấy Project ID và Tier)
*   `fetchAvailableModels` (để quét danh sách model và quota thực tế)

---

## 🚀 Cấu hình & Chạy máy chủ

1.  **Cài đặt môi trường**:
    ```bash
    pip install -r antigravity_proxy/requirements.txt
    ```
2.  **Khởi chạy**:
    ```bash
    python3 antigravity_proxy/proxy_server.py
    ```
    *Mặc định chạy tại port 5007.*

---

## 📡 API Reference & CURL Test

Dưới đây là các endpoint kỹ thuật của Proxy để bạn có thể kiểm tra trực tiếp.

### 1. Lấy danh sách mô hình (Internal Format)
Kiểm tra xem Proxy có nhận diện được các tài khoản và gộp các model lại không.
```bash
curl http://localhost:5007/v1beta/models
```

### 2. Test Proxy Generate Content (Google Format)
Gửi yêu cầu trực tiếp theo định dạng API của Google.
```bash
curl -X POST http://localhost:5007/v1beta/models/gemini-3-flash:generateContent \
  -H "Content-Type: application/json" \
  -d '{
    "contents": [{
      "parts": [{"text": "Hello, explain how a proxy works."}]
    }]
  }'
```

### 3. Quản lý Tài khoản (Internal API)
*   **Liệt kê tài khoản**: `GET /api/accounts`
*   **Làm mới hạn mức**: `POST /api/accounts/refresh`

### 4. Giao diện người dùng
*   **Trang chủ Dashboard**: `http://localhost:5007/`
*   **Quản lý tài khoản**: `http://localhost:5007/ui/accounts`
*   **Trình khám phá Model**: `http://localhost:5007/ui/models`

---

## 📂 Cấu trúc thư mục
*   `proxy_server.py`: File thực thi chính (Flask App & TokenManager).
*   `accounts/`: Thư mục chứa các file cấu hình tài khoản cá nhân.
*   `templates/`: Giao diện Web (HTML/JS/CSS).
*   `README.md`: Hướng dẫn kỹ thuật (file này).

---
*Dự án thuộc hệ sinh thái Antigravity Agent.*
