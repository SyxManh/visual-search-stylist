import os
import io
import threading
import uuid
import asyncio
from urllib.parse import quote
from pathlib import Path
from fastapi import FastAPI, UploadFile, File, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from PIL import Image, ImageOps, UnidentifiedImageError
from dotenv import dotenv_values
from ultralytics import YOLOWorld
from product_search import search_products_for_image
from tryon_cloudflare import create_tryon, get_settings, normalize_image, TryOnError
from style_advice import get_style_advice, prepare_profile, STYLE_MODEL
from feng_shui import birth_palette

app = FastAPI()

BASE_DIR = Path(__file__).resolve().parent
local_config = dotenv_values(BASE_DIR / ".env")
UPLOAD_DIR = BASE_DIR / "static" / "uploads"
CROP_DIR = BASE_DIR / "static" / "crops"
TEMPLATE_DIR = BASE_DIR / "templates"

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(CROP_DIR, exist_ok=True)

app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(TEMPLATE_DIR))

# Khởi tạo mô hình YOLO-World
model = YOLOWorld(str(BASE_DIR / "yolov8s-worldv2.pt"))
model_lock = threading.Lock()
tryon_lock = asyncio.Lock()
style_lock = asyncio.Lock()
PRODUCT_CLASSES = [
    "shirt", "t-shirt", "polo shirt", "hoodie", "jacket", "dress", "skirt",
    "jeans", "trousers", "pants", "shorts",
    "shoes", "sneakers", "sandals", "high heels", "boots",
    "backpack", "handbag", "wallet", "sunglasses", "cap", "belt", "wristwatch",
    "laptop", "mechanical keyboard", "computer mouse", "headphone",
    "earphones", "smartphone", "smartwatch", "water bottle", "perfume bottle"
]
model.set_classes(PRODUCT_CLASSES)

SERPAPI_KEY = str(os.getenv("SERPAPI_KEY") or local_config.get("SERPAPI_KEY") or "").strip()
PUBLIC_BASE_URL = str(os.getenv("PUBLIC_BASE_URL") or local_config.get("PUBLIC_BASE_URL") or "").rstrip("/")


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse(request=request, name="index.html", headers={"Cache-Control": "no-store"})


@app.get("/health")
async def health():
    settings = get_settings()
    return {"status": "ok", "search_provider": "serpapi" if SERPAPI_KEY else "not_configured",
            "search_contract_version": 2, "tryon_provider": "cloudflare",
            "tryon_configured": settings.configured, "tryon_model": settings.model,
            "style_advice_version": 1, "style_model": STYLE_MODEL}


@app.post("/feng-shui")
async def feng_shui(birth_date: str = Form(...)):
    try:
        return {"feng_shui":birth_palette(birth_date)}
    except ValueError as error:
        return JSONResponse({"error":str(error),"code":"invalid_birth_date"},status_code=400)


@app.post("/style-advice")
async def style_advice(
    person: UploadFile = File(...), height_cm: str = Form(...), weight_kg: str = Form(...),
    birth_date: str = Form(default=""), occasion: str = Form(default="daily"),
    preference: str = Form(default="minimal"), consent: bool = Form(default=False),
    consent_provider: str = Form(default=""),
):
    if not consent or consent_provider != "cloudflare":
        return JSONResponse({"error":"Cần đồng ý gửi ảnh, chiều cao và cân nặng tới Cloudflare để nhận tư vấn.","code":"consent_required"},status_code=400)
    try:
        height,weight,palette = prepare_profile(height_cm,weight_kg,birth_date,occasion,preference)
        raw = await person.read(12*1024*1024+1)
        normalized = await asyncio.to_thread(normalize_image,raw)
    except ValueError as error:
        return JSONResponse({"error":str(error),"code":"invalid_profile"},status_code=400)
    except TryOnError as error:
        return JSONResponse({"error":str(error),"code":error.code},status_code=error.status_code)
    if style_lock.locked():
        return JSONResponse({"error":"AI đang tư vấn một yêu cầu khác. Vui lòng chờ rồi thử lại.","code":"busy"},status_code=429)
    try:
        async with style_lock:
            text = await asyncio.to_thread(get_style_advice,normalized,height,weight,occasion,preference,palette)
        return {"status":"ready","advice":text,"feng_shui":palette,"provider":"cloudflare","model":STYLE_MODEL}
    except TryOnError as error:
        # Keep the deterministic, local palette available when quota/auth fails.
        return JSONResponse({"status":"ai_unavailable","advice":"","feng_shui":palette,
                             "error":str(error),"code":error.code},status_code=error.status_code)


@app.post("/detect-objects")
async def detect_objects(file: UploadFile = File(...)):
    raw = await file.read(12 * 1024 * 1024 + 1)
    if not raw or len(raw) > 12 * 1024 * 1024:
        return JSONResponse({"error": "Ảnh trống hoặc vượt quá 12 MB."}, status_code=400)
    unique_id = uuid.uuid4().hex
    file_ext = ".jpg"
    raw_img_path = str(UPLOAD_DIR / f"{unique_id}{file_ext}")
    try:
        with Image.open(io.BytesIO(raw)) as image:
            if image.width * image.height > 25_000_000:
                raise ValueError("Ảnh quá lớn (tối đa 25 triệu điểm ảnh).")
            image = ImageOps.exif_transpose(image).convert("RGB")
            image.thumbnail((2000, 2000))
            image.save(raw_img_path, "JPEG", quality=90)
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        return JSONResponse({"error": "Ảnh không hợp lệ. Hãy chọn JPEG, PNG hoặc WebP dưới 25 triệu điểm ảnh."}, status_code=400)

    # Nhận diện các đồ vật riêng lẻ trong ảnh
    def predict():
        with model_lock:
            return model.predict(raw_img_path, conf=0.15, iou=0.45, verbose=False)
    results = await asyncio.to_thread(predict)
    crops_info = []

    with Image.open(raw_img_path) as original_img:
        if original_img.mode in ("RGBA", "P", "LA"):
            original_img = original_img.convert("RGB")

        img_w, img_h = original_img.size

        # Vòng lặp duyệt qua từng vật thể YOLO tìm thấy để cắt riêng từng món
        for idx, box in enumerate(results[0].boxes):
            cls_id = int(box.cls[0])
            label_name = PRODUCT_CLASSES[cls_id]
            x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())

            # Bỏ qua các hộp quá nhỏ
            if (x2 - x1) < 25 or (y2 - y1) < 25:
                continue

            # Nới nhẹ biên để lấy trọn form dáng món đồ
            pad_x = int((x2 - x1) * 0.08)
            pad_y = int((y2 - y1) * 0.08)
            x1_c = max(0, x1 - pad_x)
            y1_c = max(0, y1 - pad_y)
            x2_c = min(img_w, x2 + pad_x)
            y2_c = min(img_h, y2 + pad_y)

            cropped_img = original_img.crop((x1_c, y1_c, x2_c, y2_c))
            crop_filename = f"{unique_id}_crop_{idx}.jpg"
            crop_filepath = str(CROP_DIR / crop_filename)
            cropped_img.save(crop_filepath, format="JPEG", quality=95)

            crops_info.append({
                "id": idx,
                "label": label_name,
                "crop_url": f"/static/crops/{crop_filename}",
                "crop_path": crop_filepath
            })

    if not crops_info:
        crop_filename = f"{unique_id}_full.jpg"
        with Image.open(raw_img_path) as image:
            image.save(CROP_DIR / crop_filename, "JPEG", quality=90)
        crops_info.append({"id": 0, "label": "", "crop_url": f"/static/crops/{crop_filename}",
                           "crop_path": str(CROP_DIR / crop_filename)})
    return JSONResponse({
        "original_image": f"/static/uploads/{unique_id}{file_ext}",
        "detected_items": crops_info
    })


@app.post("/search-products")
async def search_products(request: Request, crop_path: str = Form(...), label: str = Form(default="")):
    try:
        crop = Path(crop_path).resolve()
        if crop.parent != CROP_DIR.resolve() or not crop.is_file():
            raise ValueError()
    except (OSError, ValueError):
        return JSONResponse({"error": "Ảnh cần tìm không hợp lệ hoặc đã bị xóa."}, status_code=400)
    # A local tunnel launcher can update this file without restarting the model.
    public_url = PUBLIC_BASE_URL
    tunnel_file = BASE_DIR / "run_logs" / "public_url.txt"
    if not public_url and tunnel_file.exists():
        public_url = tunnel_file.read_text().strip().rstrip("/")
    if not public_url:
        public_url = str(request.base_url).rstrip("/")
    image_url = f"{public_url}/static/crops/{quote(crop.name)}"
    return await asyncio.to_thread(search_products_for_image, image_url, label, SERPAPI_KEY)


@app.post("/virtual-try-on")
async def virtual_try_on(
    person: UploadFile = File(...),
    crop_path: str = Form(...),
    cloth_type: str = Form(default="upper"),
    consent: bool = Form(default=False),
    consent_provider: str = Form(default=""),
):
    """Send two reference images to Cloudflare only after explicit user consent."""
    if not consent or consent_provider != "cloudflare":
        return JSONResponse({"error": "Cần xác nhận gửi ảnh tới Cloudflare để thử đồ. Nếu dùng app cũ, hãy cập nhật bản mới.",
                             "code": "consent_required"}, status_code=400)
    try:
        crop = Path(crop_path).resolve()
        if crop.parent != CROP_DIR.resolve() or not crop.is_file():
            raise ValueError()
    except (OSError, ValueError):
        return JSONResponse({"error": "Ảnh trang phục không hợp lệ."}, status_code=400)
    if cloth_type not in {"upper", "lower", "overall"}:
        return JSONResponse({"error": "Loại trang phục không hợp lệ."}, status_code=400)
    settings = get_settings()
    if not settings.configured:
        return JSONResponse({"error": "Chưa cấu hình Cloudflare. Điền CLOUDFLARE_API_TOKEN và CLOUDFLARE_ACCOUNT_ID vào file .env ở máy tính rồi lưu.",
                             "code": "not_configured"}, status_code=503)
    if tryon_lock.locked():
        return JSONResponse({"error": "Máy chủ đang tạo một ảnh thử đồ. Vui lòng chờ xong rồi thử lại.",
                             "code": "busy"}, status_code=429)
    try:
        async with tryon_lock:
            person_bytes = await person.read(12 * 1024 * 1024 + 1)
            if crop.stat().st_size > 12 * 1024 * 1024:
                return JSONResponse({"error": "Ảnh trang phục vượt quá 12 MB."}, status_code=400)
            garment_bytes = crop.read_bytes()
            output = await asyncio.to_thread(create_tryon, person_bytes, garment_bytes, cloth_type, settings)
            output_dir = BASE_DIR / "static" / "tryon"
            output_dir.mkdir(parents=True, exist_ok=True)
            output_name = f"{uuid.uuid4().hex}.png"
            (output_dir / output_name).write_bytes(output)
            return JSONResponse({"result_url": f"/static/tryon/{output_name}", "provider": "cloudflare"})
    except TryOnError as error:
        return JSONResponse({"error": str(error), "code": error.code}, status_code=error.status_code)
    except OSError:
        return JSONResponse({"error": "Không đọc hoặc lưu được ảnh trên máy chủ.", "code": "storage_error"}, status_code=500)


@app.post("/upload-garment")
async def upload_garment(file: UploadFile = File(...)):
    """Select a clothing reference directly, without detector labels or search."""
    try:
        raw = await file.read(12 * 1024 * 1024 + 1)
        image = await asyncio.to_thread(normalize_image, raw)
        filename = f"{uuid.uuid4().hex}_garment.png"
        path = CROP_DIR / filename
        path.write_bytes(image)
        return {"crop_path": str(path), "crop_url": f"/static/crops/{filename}",
                "label": "Trang phục đã chọn"}
    except TryOnError as error:
        return JSONResponse({"error": str(error), "code": error.code}, status_code=error.status_code)
    except OSError:
        return JSONResponse({"error": "Không lưu được ảnh trang phục."}, status_code=500)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
