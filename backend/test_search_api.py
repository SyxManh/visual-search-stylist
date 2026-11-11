"""HTTP contract tests; stub detection weights and the external search provider."""
import importlib
import sys
import unittest
import uuid
from types import SimpleNamespace
from unittest.mock import Mock, patch
from fastapi.testclient import TestClient

_original_ultralytics = sys.modules.get('ultralytics')
sys.modules['ultralytics'] = SimpleNamespace(YOLOWorld=Mock(return_value=Mock()))
try:
    backend = importlib.import_module('main')
finally:
    # Restore only the detector module. Restoring all of sys.modules would
    # unload Pillow while the backend still referenced its first instance,
    # breaking image decoder registration when later tests import Pillow.
    if _original_ultralytics is None:
        sys.modules.pop('ultralytics', None)
    else:
        sys.modules['ultralytics'] = _original_ultralytics

class ApiContractTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(backend.app)
        self.crop = backend.CROP_DIR / f'test_{uuid.uuid4().hex}.jpg'
        self.crop.write_bytes(b'local test fixture')

    def tearDown(self):
        self.crop.unlink(missing_ok=True)
        self.client.close()

    def test_no_key_returns_empty_results_not_redirects(self):
        with patch.object(backend, 'SERPAPI_KEY', ''), patch('product_search.requests.get') as get:
            response = self.client.post('/search-products', data={'crop_path': str(self.crop)})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['status'], 'not_configured')
        self.assertEqual(response.json()['total'], 0)
        self.assertTrue(all(not items for items in response.json()['products'].values()))
        get.assert_not_called()

    def test_product_cards_flow_through_http_response(self):
        payload = {'status': 'ready', 'products': {'shopee': [
            {'title': 'API fixture', 'price': '200.000 ₫', 'source': 'Shopee',
             'thumbnail': 'https://img.example/item.jpg', 'link': 'https://shopee.vn/product/1/2', 'link_type': 'product'}
        ], 'lazada': [], 'amazon': [], 'others': []}, 'total': 1, 'message': 'Test', 'retryable': False}
        with patch.object(backend, 'search_products_for_image', return_value=payload) as search:
            response = self.client.post('/search-products', data={'crop_path': str(self.crop)})
        self.assertEqual(response.json(), payload)
        self.assertIn('/static/crops/' + self.crop.name, search.call_args.args[0])

    def test_invalid_path_is_rejected_before_provider_call(self):
        with patch.object(backend, 'search_products_for_image') as search:
            response = self.client.post('/search-products', data={'crop_path': str(backend.BASE_DIR / 'main.py')})
        self.assertEqual(response.status_code, 400)
        search.assert_not_called()

if __name__ == '__main__':
    unittest.main()
