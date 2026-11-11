"""Image search provider adapter. Only real API results become product cards."""
import logging
from urllib.parse import urlparse

import requests

PLATFORMS = ('shopee', 'lazada', 'amazon', 'others')


def safe_url(value):
    if not isinstance(value, str):
        return ''
    try:
        parsed = urlparse(value)
        return value if parsed.scheme in {'http', 'https'} and parsed.hostname and not parsed.username else ''
    except ValueError:
        return ''


def platform_for(link):
    host = (urlparse(link).hostname or '').lower()
    for platform, domains in {
        'shopee': ('shopee.vn', 'shopee.com', 'shopee.sg'),
        'lazada': ('lazada.vn', 'lazada.com', 'lazada.sg'),
        'amazon': ('amazon.com', 'amazon.co.uk', 'amazon.de', 'amazon.co.jp'),
    }.items():
        if any(host == d or host.endswith('.' + d) for d in domains):
            return platform
    return 'others'


def is_product_link(link):
    if not safe_url(link):
        return False
    parsed = urlparse(link)
    host = (parsed.hostname or '').lower()
    if host in {'lens.google.com', 'google.com', 'www.google.com'}:
        return False
    return parsed.path.rstrip('/').lower() not in {'', '/search', '/s', '/catalog'}


def normalize_matches(matches):
    products = {key: [] for key in PLATFORMS}
    seen = set()
    for item in matches:
        if not isinstance(item, dict):
            continue
        link = item.get('link', '')
        if not is_product_link(link) or link in seen:
            continue
        if item.get('link_type', 'product') != 'product':
            continue
        seen.add(link)
        price = item.get('price')
        if isinstance(price, dict):
            price = price.get('value')  # Preserve the provider's currency.
        products[platform_for(link)].append({
            'title': str(item.get('title') or 'Sản phẩm tương tự'),
            'link': link,
            'price': str(price) if price is not None and price != '' else 'Chưa có giá',
            'thumbnail': safe_url(item.get('thumbnail')) or safe_url(item.get('image')),
            'source': str(item.get('source') or urlparse(link).hostname),
            'link_type': 'product',
        })
    return products


def result(status, message, products=None, retryable=False):
    products = products if products is not None else {key: [] for key in PLATFORMS}
    return {
        'status': status, 'search_mode': 'visual_matches',
        'message': message, 'products': products,
        'total': sum(len(items) for items in products.values()),
        'retryable': retryable,
    }


def search_products_for_image(image_url, label, api_key):
    # label is kept for compatibility with existing mobile clients. Searching
    # uses the selected image, never a label-to-marketplace keyword redirect.
    if not api_key or not api_key.strip():
        return result('not_configured', 'Chưa cấu hình API tìm sản phẩm bằng ảnh. Danh sách sản phẩm tương tự sẽ xuất hiện tại đây sau khi thêm API ở máy chủ.')
    try:
        response = requests.get('https://serpapi.com/search', params={
            'engine': 'google_lens', 'type': 'visual_matches',
            'url': image_url, 'hl': 'vi', 'country': 'vn', 'api_key': api_key,
        }, timeout=(10, 45))
        if response.status_code in {401, 403}:
            return result('auth_error', 'API key chưa hợp lệ hoặc chưa được cấp quyền. Hãy kiểm tra cấu hình ở máy chủ.')
        if response.status_code == 429:
            return result('rate_limited', 'API đã hết hạn mức hoặc đang giới hạn yêu cầu. Hãy kiểm tra hạn mức trước khi thử lại.', retryable=True)
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            raise ValueError('Invalid provider response')
        if data.get('error'):
            # Provider messages may include credentials/URLs; never echo them.
            return result('provider_error', 'API không xử lý được ảnh. Hãy kiểm tra API key, hạn mức và URL ảnh công khai ở máy chủ.', retryable=True)
        matches = data.get('visual_matches', [])
        if not isinstance(matches, list):
            raise ValueError('Invalid visual_matches')
        products = normalize_matches(matches)
        if not any(products.values()):
            return result('empty', 'Chưa tìm thấy sản phẩm tương tự cho ảnh này. Hãy thử ảnh rõ hơn hoặc chọn món đồ khác.')
        return result('ready', 'Sản phẩm tương tự theo ảnh. Giá và tình trạng hàng có thể thay đổi tại cửa hàng.', products)
    except requests.Timeout:
        return result('timeout', 'API tìm kiếm phản hồi quá lâu. Hãy thử lại.', retryable=True)
    except (requests.RequestException, ValueError):
        logging.getLogger(__name__).warning('Image search provider failed')
        return result('provider_error', 'Không tải được kết quả từ API tìm kiếm. Hãy thử lại sau.', retryable=True)
