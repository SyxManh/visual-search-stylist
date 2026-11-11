"""Read-only Workers AI credential check. Never sends photos or generates images."""
import sys

import requests

from tryon_cloudflare import get_settings, validate_settings, provider_error, TryOnError


def main():
    settings = get_settings()
    try:
        validate_settings(settings)
        response = requests.get(
            f"https://api.cloudflare.com/client/v4/accounts/{settings.account_id}/ai/models/search",
            headers={"Authorization": f"Bearer {settings.api_token}"},
            params={"search": "flux-2-klein-4b"}, timeout=(10, 30), allow_redirects=False,
        )
        print("Cloudflare HTTP:", response.status_code)
        try:
            payload = response.json()
        except ValueError:
            payload = {}
        payload = payload if isinstance(payload, dict) else {}
        provider_error(response, payload)
        if payload.get("success") is not True or not isinstance(payload.get("result"), list):
            raise TryOnError("Cloudflare chưa trả về danh sách mô hình hợp lệ.", "invalid_response", 502)
        available = any(isinstance(model, dict) and model.get("name") == settings.model for model in payload["result"])
        print("AUTH_OK: Token va Account ID doc duoc Workers AI.")
        print("FLUX.2 Klein 4B listed:", available)
        print("Chua kiem tra quyen tao anh/han muc con lai. Khong gui anh, khong goi tao anh.")
        return 0
    except TryOnError as error:
        print(error.code + ": " + str(error))
        return 1
    except requests.RequestException:
        print("connection_error: Khong ket noi duoc Cloudflare. Khong hien thi token hoac loi tho.")
        return 2


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
