import base64
import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import requests
from PIL import Image
from test_search_api import backend
from tryon_cloudflare import create_tryon, get_settings, normalize_image, TryOnError, TryOnSettings


def photo(color='red'):
    out = io.BytesIO()
    Image.new('RGB', (32, 48), color).save(out, 'PNG')
    return out.getvalue()


def response(status=200, body=None, raw=None):
    return Mock(status_code=status, ok=200 <= status < 300,
                headers={'Content-Type':'image/png' if raw is not None else 'application/json'},
                content=raw, json=lambda: body if body is not None else {
                    'success':True,'result':{'image':base64.b64encode(photo('green')).decode()}})


SETTINGS = TryOnSettings('test-secret', 'a'*32)


class TryOnProviderTests(unittest.TestCase):
    def test_credentials_can_be_added_and_rotated_without_restart(self):
        with tempfile.TemporaryDirectory(dir=backend.BASE_DIR) as folder:
            env = Path(folder) / '.env'
            with patch('tryon_cloudflare.BASE_DIR', Path(folder)), patch.dict(os.environ, {'CLOUDFLARE_API_TOKEN':'','CLOUDFLARE_ACCOUNT_ID':''}):
                env.write_text('GEMINI_API_KEY=old-key\n')
                self.assertFalse(get_settings().configured)
                env.write_text('CLOUDFLARE_API_TOKEN=key-one\nCLOUDFLARE_ACCOUNT_ID='+'a'*32+'\n')
                self.assertTrue(get_settings().configured)
                self.assertEqual(get_settings().api_token, 'key-one')
                env.write_text('CLOUDFLARE_API_TOKEN=key-two\nCLOUDFLARE_ACCOUNT_ID='+'b'*32+'\n')
                self.assertEqual(get_settings().api_token, 'key-two')
                self.assertEqual(get_settings().account_id, 'b'*32)

    @patch('tryon_cloudflare.requests.post')
    def test_two_images_are_binary_multipart_in_correct_order(self, post):
        post.return_value = response()
        output = create_tryon(photo('red'), photo('blue'), 'upper', SETTINGS)
        self.assertEqual(Image.open(io.BytesIO(output)).getpixel((0,0)), (0,128,0))
        args = post.call_args.kwargs
        self.assertEqual(post.call_args.args[0], 'https://api.cloudflare.com/client/v4/accounts/'+'a'*32+'/ai/run/@cf/black-forest-labs/flux-2-klein-4b')
        self.assertEqual(args['headers']['Authorization'], 'Bearer test-secret')
        self.assertNotIn('Content-Type',args['headers'])
        self.assertEqual(args['data']['width'], '768')
        self.assertEqual(args['data']['height'], '1024')
        self.assertNotIn('steps',args['data'])
        self.assertFalse(args['allow_redirects'])
        self.assertEqual([item[0] for item in args['files']], ['input_image_0','input_image_1'])
        for item,color in zip(args['files'], [(255,0,0),(0,0,255)]):
            self.assertEqual(Image.open(io.BytesIO(item[1][1])).getpixel((0,0)),color)
        post.assert_called_once()

    @patch('tryon_cloudflare.requests.post')
    def test_binary_image_and_data_uri_output(self, post):
        for value in [response(raw=photo()),response(body={'success':True,'result':{'image':'data:image/png;base64,'+base64.b64encode(photo()).decode()}})]:
            post.return_value=value
            self.assertEqual(Image.open(io.BytesIO(create_tryon(photo(),photo(),'overall',SETTINGS))).format,'PNG')

    @patch('tryon_cloudflare.requests.post')
    def test_invalid_credentials_settings_and_inputs_do_not_call_provider(self, post):
        for settings,person,kind in [
            (TryOnSettings('',SETTINGS.account_id),photo(),'upper'),
            (TryOnSettings('key',''),photo(),'upper'),
            (TryOnSettings('key','../wrong'),photo(),'upper'),
            (TryOnSettings('Bearer key',SETTINGS.account_id),photo(),'upper'),
            (TryOnSettings('key',SETTINGS.account_id,0),photo(),'upper'),
            (TryOnSettings('key',SETTINGS.account_id,model='different-model'),photo(),'upper'),
            (SETTINGS,b'not an image','upper'),(SETTINGS,photo(),'bad')]:
            with self.assertRaises(TryOnError):
                create_tryon(person,photo(),kind,settings)
        post.assert_not_called()

    @patch('tryon_cloudflare.requests.post')
    def test_provider_errors_distinguish_auth_daily_quota_busy_and_paid_plan(self, post):
        for status,code,expected in [
            (401,10000,'auth_error'),(403,10000,'auth_error'),(403,5018,'permission_denied'),
            (403,5035,'paid_plan_required'),(429,3036,'daily_quota_exceeded'),
            (429,3040,'provider_busy'),(429,0,'rate_limited'),(404,3042,'model_unavailable'),
            (400,5007,'model_unavailable'),(400,5004,'invalid_request'),(413,3006,'invalid_image'),
            (500,0,'provider_error'),(200,0,'provider_error')]:
            post.reset_mock()
            post.return_value=response(status,{'success':False,'errors':[{'code':code,'message':'test-secret'}]})
            with self.assertRaises(TryOnError) as error:
                create_tryon(photo(),photo(),'lower',SETTINGS)
            self.assertEqual(error.exception.code,expected)
            self.assertNotIn('test-secret',str(error.exception))
            post.assert_called_once()

    @patch('tryon_cloudflare.requests.post')
    def test_network_errors_never_retry_or_leak_raw_error(self, post):
        for failure,code in [(requests.Timeout('test-secret'),'timeout'),(requests.ConnectionError('test-secret'),'connection_error')]:
            post.reset_mock();post.side_effect=failure
            with self.assertRaises(TryOnError) as error:
                create_tryon(photo(),photo(),'upper',SETTINGS)
            self.assertEqual(error.exception.code,code)
            self.assertNotIn('test-secret',str(error.exception))
            post.assert_called_once()

    @patch('tryon_cloudflare.requests.post')
    def test_malformed_text_only_or_non_image_output_is_rejected(self, post):
        for body in [[],{}, {'result':None},{'result':{'response':'test-secret'}},
                     {'result':{'image':'invalid'}},{'result':{'image':base64.b64encode(b'not image').decode()}}]:
            post.return_value=response(body=body)
            with self.assertRaises(TryOnError) as error:
                create_tryon(photo(),photo(),'upper',SETTINGS)
            self.assertEqual(error.exception.code,'invalid_response')
            self.assertNotIn('test-secret',str(error.exception))


class TryOnApiTests(unittest.TestCase):
    def setUp(self):
        from fastapi.testclient import TestClient
        import uuid
        self.client = TestClient(backend.app)
        self.crop = backend.CROP_DIR / f'test_tryon_{uuid.uuid4().hex}.png'
        self.crop.write_bytes(photo())

    def tearDown(self):
        self.crop.unlink(missing_ok=True)
        self.client.close()

    def request(self, **fields):
        data = {'crop_path':str(self.crop), 'cloth_type':'upper', 'consent':'true', 'consent_provider':'cloudflare', **fields}
        return self.client.post('/virtual-try-on', data=data, files={'person':('person.png', photo(), 'image/png')})

    def test_consent_is_required_before_any_provider_call(self):
        with patch.object(backend, 'create_tryon') as create:
            response = self.request(consent='false')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['code'], 'consent_required')
        create.assert_not_called()

    def test_old_provider_consent_cannot_authorize_cloudflare(self):
        with patch.object(backend, 'create_tryon') as create:
            self.assertEqual(self.request(consent_provider='').json()['code'], 'consent_required')
            self.assertEqual(self.request(consent_provider='openai').json()['code'], 'consent_required')
            self.assertEqual(self.request(consent_provider='gemini').json()['code'], 'consent_required')
        create.assert_not_called()

    def test_health_reports_cloudflare_without_exposing_key(self):
        with patch.object(backend, 'get_settings', return_value=SETTINGS):
            response = self.client.get('/health')
        self.assertEqual(response.json()['tryon_provider'], 'cloudflare')
        self.assertTrue(response.json()['tryon_configured'])
        self.assertNotIn('test-secret', response.text)

    def test_no_key_and_bad_path_do_not_send_images(self):
        with patch.object(backend, 'get_settings', return_value=TryOnSettings('', SETTINGS.account_id)), patch.object(backend, 'create_tryon') as create:
            self.assertEqual(self.request().json()['code'], 'not_configured')
            self.assertEqual(self.request(crop_path=str(backend.BASE_DIR/'main.py')).status_code, 400)
        create.assert_not_called()

    def test_success_saves_local_png_and_retains_mobile_contract(self):
        with tempfile.TemporaryDirectory(dir=backend.BASE_DIR) as folder:
            with patch.object(backend, 'BASE_DIR', Path(folder)), patch.object(backend, 'get_settings', return_value=SETTINGS), patch.object(backend, 'create_tryon', return_value=photo('green')) as create:
                response = self.request()
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()['provider'], 'cloudflare')
            self.assertTrue((Path(folder) / response.json()['result_url'].lstrip('/')).is_file())
            self.assertEqual(create.call_args.args[2], 'upper')

    def test_busy_rejects_extra_paid_request(self):
        with patch.object(backend, 'get_settings', return_value=SETTINGS), patch.object(backend.tryon_lock, 'locked', return_value=True), patch.object(backend, 'create_tryon') as create:
            self.assertEqual(self.request().status_code, 429)
        create.assert_not_called()

    def test_direct_garment_upload_does_not_require_detection_or_api(self):
        with patch.object(backend.model, 'predict') as predict, patch('tryon_cloudflare.requests.post') as post:
            response = self.client.post('/upload-garment', files={'file':('clothing.png', photo(), 'image/png')})
        self.assertEqual(response.status_code, 200, response.text)
        path = Path(response.json()['crop_path'])
        try:
            self.assertEqual(path.parent, backend.CROP_DIR)
            with Image.open(path) as image:
                self.assertEqual(image.format, 'PNG')
            self.assertIn('/static/crops/', response.json()['crop_url'])
            predict.assert_not_called()
            post.assert_not_called()
        finally:
            path.unlink(missing_ok=True)

    def test_direct_garment_upload_rejects_non_images(self):
        response = self.client.post('/upload-garment', files={'file':('fake.jpg', b'not an image', 'image/jpeg')})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['code'], 'invalid_image')


if __name__ == '__main__':
    unittest.main()
