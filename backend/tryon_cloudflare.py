"""Cloudflare FLUX.2 Klein try-on; configuration and credentials stay on the server."""
import base64
import binascii
import io
import os
import re
from dataclasses import dataclass
from pathlib import Path

import requests
from dotenv import dotenv_values
from PIL import Image, ImageOps, UnidentifiedImageError

try:
    import pillow_heif
    pillow_heif.register_heif_opener()
except ImportError:
    pass

BASE_DIR = Path(__file__).resolve().parent
MAX_IMAGE_BYTES = 12 * 1024 * 1024
DEFAULT_MODEL = "@cf/black-forest-labs/flux-2-klein-4b"


class TryOnError(Exception):
    def __init__(self, message, code, status_code=400):
        super().__init__(message)
        self.code = code
        self.status_code = status_code


@dataclass(frozen=True)
class TryOnSettings:
    api_token: str
    account_id: str
    width: int = 768
    height: int = 1024
    model: str = DEFAULT_MODEL

    @property
    def configured(self):
        return bool(self.api_token and self.account_id)


def get_settings():
    # Reading on each request lets users save new credentials without restarting.
    values = dotenv_values(BASE_DIR / ".env")

    def value(name, default=""):
        result = str(os.environ.get(name) or values.get(name) or default).strip()
        return "" if result.lower() in {"your_api_token", "your_account_id", "paste_your_key_here"} else result

    def dimension(name, default):
        try:
            return int(value(name, str(default)))
        except ValueError:
            return 0

    return TryOnSettings(value("CLOUDFLARE_API_TOKEN"), value("CLOUDFLARE_ACCOUNT_ID"),
                         dimension("CLOUDFLARE_IMAGE_WIDTH", 768),
                         dimension("CLOUDFLARE_IMAGE_HEIGHT", 1024))


def validate_settings(settings):
    if not settings.configured:
        raise TryOnError("Chưa cấu hình Cloudflare. Điền CLOUDFLARE_API_TOKEN và CLOUDFLARE_ACCOUNT_ID trong file .env ở máy tính rồi lưu.", "not_configured", 503)
    if not re.fullmatch(r"[a-fA-F0-9]{32}", settings.account_id):
        raise TryOnError("CLOUDFLARE_ACCOUNT_ID phải là Account ID gồm 32 ký tự hex; không dùng email, Zone ID hoặc API Token.", "configuration_error", 503)
    if any(c.isspace() or c in "\"'" for c in settings.api_token):
        raise TryOnError("CLOUDFLARE_API_TOKEN có ký tự thừa. Chỉ dán giá trị token, không thêm chữ Bearer hoặc nguyên lệnh cURL.", "configuration_error", 503)
    if settings.model != DEFAULT_MODEL:
        raise TryOnError("Máy chủ chỉ cấu hình mô hình FLUX.2 Klein 4B cho luồng này.", "configuration_error", 503)
    if any(not isinstance(v, int) or not 256 <= v <= 1920 for v in (settings.width, settings.height)):
        raise TryOnError("Kích thước ảnh Cloudflare trong .env phải từ 256 đến 1920 pixel.", "configuration_error", 503)


def normalize_image(raw):
    if not raw or len(raw) > MAX_IMAGE_BYTES:
        raise TryOnError("Ảnh trống hoặc vượt quá 12 MB.", "invalid_image")
    try:
        with Image.open(io.BytesIO(raw)) as original:
            if original.width * original.height > 25_000_000:
                raise ValueError("Image too large")
            image = ImageOps.exif_transpose(original).convert("RGB")
            image.thumbnail((1536, 2048))
            output = io.BytesIO()
            image.save(output, "PNG")
            return output.getvalue()
    except (OSError, UnidentifiedImageError, ValueError, Image.DecompressionBombError):
        raise TryOnError("Ảnh không hợp lệ. Chọn JPEG, PNG, WebP hoặc HEIC dưới 25 triệu điểm ảnh.", "invalid_image") from None


def provider_error(response, payload):
    """Classify known machine codes without exposing raw errors or credentials."""
    errors = payload.get("errors", [])
    codes = {str(item.get("code")) for item in errors if isinstance(item, dict)} if isinstance(errors, list) else set()
    if response.status_code == 401 or codes & {"10000", "9109"}:
        raise TryOnError("Cloudflare từ chối xác thực. Kiểm tra CLOUDFLARE_API_TOKEN, thời hạn và Account ID; dùng Workers AI API Token.", "auth_error", 503)
    if "5035" in codes:
        raise TryOnError("Cloudflare báo mô hình cần gói trả phí. Dừng tạo ảnh và kiểm tra chính sách hiện tại của FLUX.2 Klein 4B trước khi tiếp tục.", "paid_plan_required", 503)
    if response.status_code == 403:
        raise TryOnError("Token chưa có quyền dùng Workers AI trên Account ID này. Kiểm tra quyền Workers AI Read/Edit và account được chọn khi tạo token.", "permission_denied", 503)
    if "3036" in codes:
        raise TryOnError("Đã dùng hết hạn mức Workers AI miễn phí trong ngày. Hạn mức đặt lại lúc 07:00 giờ Việt Nam; hãy chờ lần đặt lại rồi thử tiếp.", "daily_quota_exceeded", 429)
    if "3040" in codes:
        raise TryOnError("GPU Cloudflare đang bận, chưa đủ tài nguyên xử lý. Chờ một lúc rồi thử lại; chưa thể kết luận bạn đã hết hạn mức ngày.", "provider_busy", 429)
    if response.status_code == 429:
        raise TryOnError("Cloudflare đã chạm giới hạn tốc độ hoặc hạn mức Workers AI. Kiểm tra Usage trong Cloudflare; gói Free hiện có 10.000 Neurons/ngày và đặt lại lúc 07:00 giờ Việt Nam. Nếu hết hạn mức ngày, chờ lần đặt lại; tránh bấm tạo liên tục.", "rate_limited", 429)
    if response.status_code == 404 or "5007" in codes:
        raise TryOnError("Cloudflare không tìm thấy account hoặc mô hình. Kiểm tra CLOUDFLARE_ACCOUNT_ID và quyền truy cập Workers AI.", "model_unavailable", 503)
    if response.status_code == 400:
        raise TryOnError("Cloudflare không chấp nhận ảnh hoặc cấu hình. Chọn ảnh JPEG/PNG rõ nét và kiểm tra kích thước đầu ra trong .env.", "invalid_request", 422)
    if response.status_code == 413:
        raise TryOnError("Cloudflare báo dữ liệu ảnh quá lớn. Chọn ảnh dung lượng nhỏ hơn rồi thử lại.", "invalid_image", 413)
    if not response.ok or payload.get("success") is False or errors:
        raise TryOnError("Cloudflare chưa tạo được ảnh. Dịch vụ có thể đang bận; thử lại sau.", "provider_error", 502)


def create_tryon(person_bytes, garment_bytes, cloth_type, settings):
    validate_settings(settings)
    if cloth_type not in {"upper", "lower", "overall"}:
        raise TryOnError("Loại trang phục không hợp lệ.", "invalid_cloth_type")
    person = normalize_image(person_bytes)
    garment = normalize_image(garment_bytes)
    area = {"upper": "upper-body garment", "lower": "lower-body garment", "overall": "full outfit or dress"}[cloth_type]
    prompt = (
        "Create one photorealistic virtual clothing try-on photo. "
        "Image 0 (input_image_0) is the person to edit. Image 1 (input_image_1) is the garment reference. "
        f"Replace only the person's {area} in image 0 with the garment from image 1. "
        "Preserve the person's identity, face, skin tone, hairstyle, body proportions, pose, hands, "
        "background, lighting and framing from image 0. Preserve the reference garment's color, "
        "fabric, patterns, logos and cut. Fit it naturally with realistic folds and shadows. "
        "Keep the person fully clothed; do not beautify their face or change their physique. "
        "Do not copy the reference model, mannequin or background. Return only one edited photo "
        "without captions, collage or comparison panels."
    )
    try:
        response = requests.post(
            f"https://api.cloudflare.com/client/v4/accounts/{settings.account_id}/ai/run/{settings.model}",
            headers={"Authorization": f"Bearer {settings.api_token}"},
            data={"prompt": prompt, "width": str(settings.width), "height": str(settings.height)},
            files=[("input_image_0", ("person.png", person, "image/png")),
                   ("input_image_1", ("garment.png", garment, "image/png"))],
            timeout=(10, 240), allow_redirects=False,
        )
        content_type = str(response.headers.get("Content-Type", "")).split(";")[0].lower()
        if response.ok and content_type in {"image/png", "image/jpeg", "image/webp"}:
            raw = response.content
        else:
            try:
                payload = response.json()
            except ValueError:
                payload = {}
            payload = payload if isinstance(payload, dict) else {}
            provider_error(response, payload)
            result = payload.get("result")
            encoded = result.get("image") if isinstance(result, dict) else None
            if not isinstance(encoded, str) or len(encoded) > 48 * 1024 * 1024:
                raise ValueError("Missing image")
            if encoded.startswith("data:image/"):
                prefix, encoded = encoded.split(",", 1)
                if not prefix.endswith(";base64"):
                    raise ValueError("Unsupported image encoding")
            raw = base64.b64decode(encoded, validate=True)
        if not raw or len(raw) > 36 * 1024 * 1024:
            raise ValueError("Invalid image size")
        with Image.open(io.BytesIO(raw)) as result:
            if result.width * result.height > 25_000_000:
                raise ValueError("Image too large")
            output = io.BytesIO()
            result.convert("RGB").save(output, "PNG")
        return output.getvalue()
    except requests.Timeout:
        # No retries: a timed-out generation may still consume quota or be billed.
        raise TryOnError("Cloudflare phản hồi quá lâu. Yêu cầu có thể vẫn xử lý và dùng hạn mức; kiểm tra Usage trước khi gửi lại.", "timeout", 504) from None
    except requests.RequestException:
        raise TryOnError("Không kết nối được Cloudflare. Kiểm tra Internet của máy tính.", "connection_error", 502) from None
    except (ValueError, binascii.Error, OSError, Image.DecompressionBombError):
        raise TryOnError("Cloudflare chưa trả về ảnh hợp lệ. Vui lòng thử lại sau.", "invalid_response", 502) from None
