# Visual Search + Stylist

Ứng dụng Flutter và FastAPI để tìm sản phẩm từ ảnh, thử trang phục bằng AI và tư vấn phong cách cá nhân.

## Tính năng

- Phát hiện và cắt vật thể bằng YOLO-World.
- Tìm sản phẩm tương tự qua SerpApi Google Lens, hiển thị ảnh, tên, giá và liên kết theo sàn.
- Tạo ảnh thử đồ từ ảnh người và ảnh trang phục bằng Cloudflare Workers AI / FLUX.2 Klein 4B.
- Tư vấn phối đồ theo ảnh, chiều cao, cân nặng, dịp mặc và phong cách yêu thích bằng Llama 4 Scout Vision.
- Tra Can Chi, mệnh nạp âm và gợi ý màu theo ngày sinh. Ngày sinh dương lịch được đối chiếu mốc Tết theo UTC+7. Phần này là tham khảo theo quan niệm truyền thống.
- Giao diện web dùng trên điện thoại và ứng dụng Flutter cho Android/iOS.

## Cấu trúc

```text
backend/      FastAPI, xử lý ảnh, nhà cung cấp AI, giao diện web và kiểm thử
mobile/       Mã nguồn Flutter, Android và iOS
```

## Chạy backend

Cần Python 3.12, pip và Internet cho lần tải mô hình đầu tiên. Trọng số YOLO và các thành phần mô hình sẽ được tải khi cần.

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Điền thông tin của bạn trong file `backend/.env`.

```dotenv
SERPAPI_KEY=
CLOUDFLARE_API_TOKEN=
CLOUDFLARE_ACCOUNT_ID=
```

Cloudflare cần Workers AI API Token và Account ID. SerpApi phục vụ tìm sản phẩm bằng ảnh. Dịch vụ áp dụng hạn mức và chính sách thanh toán của từng nhà cung cấp. Tra bảng màu phong thủy chạy tại backend.

```powershell
.\.venv\Scripts\python.exe -m uvicorn main:app --host 0.0.0.0 --port 8000
```

Trên macOS/Linux, thay đường dẫn Python trong môi trường ảo bằng `.venv/bin/python`.

Mở web tại http://127.0.0.1:8000 . Khi dùng điện thoại qua Internet, mở tunnel HTTPS tới cổng 8000, ví dụ `ngrok http 8000`. Đặt `PUBLIC_BASE_URL` trong `.env` thành URL công khai nếu cần để dịch vụ tìm ảnh tải được ảnh tham chiếu. Giữ máy chủ và tunnel hoạt động trong lúc sử dụng.

## Chạy Flutter

Cần Flutter có Dart tương thích `pubspec.yaml` (Dart >= 3.13.2).

```powershell
cd mobile
flutter pub get
flutter run --dart-define=API_BASE_URL=https://YOUR-BACKEND-URL
```

Cũng có thể nhập URL ở biểu tượng kết nối trong app. Android Emulator có thể dùng `http://10.0.2.2:8000`. Bản native iOS được build bằng macOS và Xcode. iPhone có thể dùng giao diện web qua Safari.

## Kiểm thử

Trong thư mục backend, các bài kiểm thử dưới đây dùng dữ liệu giả lập cho nhà cung cấp.

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m unittest test_product_search test_search_api test_tryon_cloudflare test_style_advice -v
node test_web_tryon.cjs
node test_web_style.cjs
```

Trong thư mục mobile.

```powershell
flutter analyze
flutter test
```

## Cấu hình riêng tư

Khóa được đọc từ `.env` trên máy chủ. File mẫu để trống các giá trị, còn `.gitignore` loại cấu hình riêng, ảnh tải lên, kết quả ảnh, log, môi trường Python, trọng số mô hình và file build khỏi Git.

Phần tư vấn gửi ảnh và số đo tới Cloudflare khi người dùng đồng ý. Ngày sinh đầy đủ được xử lý tại backend, AI chỉ nhận nhóm màu gợi ý. Kết quả phong thủy dùng làm cảm hứng phối màu. Size thực tế cần đối chiếu số đo và bảng size của sản phẩm.

## Tài liệu nhà cung cấp

- [Cloudflare Workers AI](https://developers.cloudflare.com/workers-ai/get-started/rest-api/)
- [SerpApi Google Lens](https://serpapi.com/google-lens-api)
- [Ultralytics YOLO-World](https://docs.ultralytics.com/models/yolo-world/)
