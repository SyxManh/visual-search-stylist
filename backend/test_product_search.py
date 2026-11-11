import unittest
from unittest.mock import patch, Mock
import requests
from product_search import normalize_matches, search_products_for_image

class SearchTests(unittest.TestCase):
    def test_missing_key_never_returns_keyword_links_or_calls_provider(self):
        with patch('requests.get') as get:
            data = search_products_for_image('https://test.example/crop.jpg', 'shirt', '')
        get.assert_not_called()
        self.assertEqual(data['status'], 'not_configured')
        self.assertEqual(data['total'], 0)
        self.assertTrue(all(not items for items in data['products'].values()))
        self.assertNotIn('lens_url', data)

    def test_normalization_deduplicates_and_preserves_currency(self):
        data = normalize_matches([
            {'link': 'javascript:alert(1)'},
            {'link': 'https://shopee.vn/product/1/2', 'price': {'value': 'US$20'}},
            {'link': 'https://shopee.vn/product/1/2'},
            {'link': 'https://other.example/shopee.vn/item', 'source': 'Shopee'},
            {'link': 'https://lazada.vn/products/item.html', 'image': 'https://images.example/item.jpg'},
        ])
        self.assertEqual(len(data['shopee']), 1)
        self.assertEqual(data['shopee'][0]['price'], 'US$20')
        self.assertEqual(len(data['others']), 1)
        self.assertEqual(data['lazada'][0]['price'], 'Chưa có giá')
        self.assertEqual(data['lazada'][0]['thumbnail'], 'https://images.example/item.jpg')

    def test_redirect_cards_are_excluded(self):
        data = normalize_matches([
            {'link': 'https://shopee.vn/search?keyword=shirt'},
            {'link': 'https://www.amazon.com/s?k=shirt'},
            {'link': 'https://www.lazada.vn/catalog/?q=shirt'},
            {'link': 'https://lens.google.com/uploadbyurl?url=x'},
            {'link': 'https://example.com/item', 'link_type': 'search'},
        ])
        self.assertTrue(all(not items for items in data.values()))

    @patch('requests.get')
    def test_provider_results_are_returned_as_in_app_cards(self, get):
        get.return_value = Mock(status_code=200, json=lambda: {'visual_matches': [
            {'title': 'Áo tương tự', 'link': 'https://lazada.vn/products/item.html',
             'price': {'value': '199.000 ₫'}, 'thumbnail': 'https://images.example/a.jpg'},
            {'title': 'Áo khác', 'link': 'https://shopee.vn/product/1/2'},
        ]})
        data = search_products_for_image('https://test.example/crop.jpg', 'shirt', 'test-key')
        self.assertEqual(data['status'], 'ready')
        self.assertEqual(data['total'], 2)
        self.assertEqual(data['products']['lazada'][0]['title'], 'Áo tương tự')
        self.assertEqual(get.call_args.kwargs['params']['type'], 'visual_matches')
        self.assertEqual(get.call_args.kwargs['params']['url'], 'https://test.example/crop.jpg')

    @patch('requests.get')
    def test_empty_timeout_auth_and_quota_are_distinct(self, get):
        get.return_value = Mock(status_code=200, json=lambda: {'visual_matches': []})
        self.assertEqual(search_products_for_image('https://x/a.jpg', '', 'key')['status'], 'empty')
        for code, status in [(401, 'auth_error'), (403, 'auth_error'), (429, 'rate_limited')]:
            get.return_value = Mock(status_code=code)
            data = search_products_for_image('https://x/a.jpg', '', 'key')
            self.assertEqual(data['status'], status)
            self.assertEqual(data['total'], 0)
        get.side_effect = requests.Timeout()
        self.assertEqual(search_products_for_image('https://x/a.jpg', '', 'key')['status'], 'timeout')

    @patch('requests.get')
    def test_malformed_or_error_response_does_not_leak_secrets(self, get):
        for body in [[], {'visual_matches': {}}, {'error': 'secret-api-key'}]:
            get.return_value = Mock(status_code=200, json=lambda: body)
            data = search_products_for_image('https://x/a.jpg', '', 'secret-api-key')
            self.assertEqual(data['status'], 'provider_error')
            self.assertNotIn('secret-api-key', str(data))

if __name__ == '__main__':
    unittest.main()
