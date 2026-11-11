import base64
import io
import json
import unittest
from datetime import date
from unittest.mock import Mock, patch

import requests
from fastapi.testclient import TestClient
from PIL import Image

from test_search_api import backend
from feng_shui import birth_palette, lunar_year_for_date
from style_advice import get_style_advice, prepare_profile, STYLE_MODEL
from tryon_cloudflare import TryOnError, TryOnSettings


def photo():
    out = io.BytesIO()
    Image.new('RGB',(32,48),'blue').save(out,'PNG')
    return out.getvalue()


SETTINGS = TryOnSettings('private-test-token','a'*32)


class CalendarTests(unittest.TestCase):
    def test_tet_boundary_including_vietnam_specific_dates(self):
        # 2007-02-17 in Vietnam versus 2007-02-18 in the Chinese calendar.
        for text, year in [('1985-01-21',1985),('2000-02-05',2000),('2007-02-17',2007),
                           ('2020-01-25',2020),('2021-02-12',2021),('2022-02-01',2022),
                           ('2023-01-22',2023),('2024-02-10',2024),('2025-01-29',2025),('2026-02-17',2026)]:
            day = date.fromisoformat(text)
            self.assertEqual(lunar_year_for_date(day),year,text)
            self.assertEqual(lunar_year_for_date(date.fromordinal(day.toordinal()-1)),year-1,text)

    def test_traditional_nap_am_and_colors(self):
        for text, can_chi, name, element in [('1984-06-01','Giáp Tý','Hải Trung Kim','Kim'),
                                           ('2000-06-01','Canh Thìn','Bạch Lạp Kim','Kim'),
                                           ('2007-02-16','Bính Tuất','Ốc Thượng Thổ','Thổ'),
                                           ('2007-02-17','Đinh Hợi','Ốc Thượng Thổ','Thổ'),
                                           ('2024-02-10','Giáp Thìn','Phú Đăng Hỏa','Hỏa')]:
            result = birth_palette(text)
            self.assertEqual((result['can_chi'],result['nap_am'],result['element']),(can_chi,name,element))
            self.assertTrue(result['colors'])
            self.assertIn('không có bằng chứng khoa học',result['note'])
        self.assertIn('Xanh lá',[c['label'] for c in birth_palette('2024-02-10')['colors']])

    def test_invalid_and_future_dates_and_measurements(self):
        for value in ['','2001-02-29','29/02/2000','1899-12-31','2999-01-01','2025-13-01']:
            with self.assertRaises(ValueError): birth_palette(value)
        for h,w in [('NaN','65'),('170','inf'),('1.7','65'),('170','0'),('','65')]:
            with self.assertRaises(ValueError): prepare_profile(h,w,'','daily','minimal')
        h,w,palette = prepare_profile('170,5','65,2','','daily','minimal')
        self.assertEqual((h,w,palette),(170.5,65.2,None))

    def test_birth_year_never_changes_again_after_tet(self):
        for year in range(1900,2027):
            values = [lunar_year_for_date(date(year,month,15)) for month in range(3,13)]
            self.assertEqual(values,[year]*10,year)


class VisionProviderTests(unittest.TestCase):
    @patch('style_advice.requests.post')
    def test_real_image_measurements_preferences_and_only_palette_go_to_ai(self, post):
        post.return_value = Mock(status_code=200,ok=True,json=lambda:{'success':True,'result':{'response':'Áo sơ mi và quần ống đứng.'}})
        palette = birth_palette('2000-06-01')
        result = get_style_advice(photo(),170,65,'work','minimal',palette,SETTINGS)
        self.assertIn('Áo sơ mi',result)
        args = post.call_args.kwargs
        self.assertIn(STYLE_MODEL,post.call_args.args[0])
        self.assertFalse(args['allow_redirects'])
        content = args['json']['messages'][1]['content']
        profile = json.loads(content[0]['text'].removeprefix('Hồ sơ: '))
        self.assertEqual((profile['height_cm'],profile['weight_kg']),(170,65))
        self.assertEqual(profile['occasion'],'Đi làm')
        self.assertEqual(profile['optional_traditional_palette']['element'],'Kim')
        self.assertNotIn('2000',json.dumps(args['json'],ensure_ascii=False))
        raw = base64.b64decode(content[1]['image_url']['url'].split(',',1)[1])
        with Image.open(io.BytesIO(raw)) as image:
            self.assertEqual(image.format,'JPEG')
            self.assertLessEqual(image.height,1024)
        post.assert_called_once()

    @patch('style_advice.requests.post')
    def test_failures_are_sanitized_no_retries_and_no_synthetic_ai_advice(self, post):
        for status,code,expected in [(401,10000,'auth_error'),(429,3036,'daily_quota_exceeded'),
                                    (429,3040,'provider_busy'),(403,5016,'model_agreement_required'),
                                    (404,5007,'style_model_unavailable'),(403,5035,'paid_plan_required')]:
            post.reset_mock()
            post.return_value = Mock(status_code=status,ok=False,json=lambda:{'success':False,'errors':[{'code':code,'message':'private-test-token'}]})
            with self.assertRaises(TryOnError) as error:
                get_style_advice(photo(),170,65,'daily','minimal',None,SETTINGS)
            self.assertEqual(error.exception.code,expected)
            self.assertNotIn('private-test-token',str(error.exception))
            post.assert_called_once()
        post.reset_mock(); post.side_effect=requests.Timeout('private-test-token')
        with self.assertRaises(TryOnError) as error:
            get_style_advice(photo(),170,65,'daily','minimal',None,SETTINGS)
        self.assertEqual(error.exception.code,'timeout')
        post.assert_called_once()

    @patch('style_advice.requests.post')
    def test_missing_key_bad_photo_or_missing_response_are_rejected(self, post):
        with self.assertRaises(TryOnError):
            get_style_advice(photo(),170,65,'daily','minimal',None,TryOnSettings('', 'a'*32))
        with self.assertRaises(TryOnError):
            get_style_advice(b'not an image',170,65,'daily','minimal',None,SETTINGS)
        post.assert_not_called()
        post.return_value = Mock(status_code=200,ok=True,json=lambda:{'success':True,'result':{}})
        with self.assertRaises(TryOnError) as error:
            get_style_advice(photo(),170,65,'daily','minimal',None,SETTINGS)
        self.assertEqual(error.exception.code,'invalid_response')


class AdviceApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(backend.app)
    def tearDown(self):
        self.client.close()
    def request(self, **fields):
        return self.client.post('/style-advice',data={'height_cm':'170','weight_kg':'65',
            'consent':'true','consent_provider':'cloudflare',**fields},files={'person':('photo.png',photo(),'image/png')})

    def test_feng_shui_works_without_any_api_or_photo(self):
        with patch.object(backend,'get_style_advice') as advice, patch('tryon_cloudflare.requests.post') as post:
            response = self.client.post('/feng-shui',data={'birth_date':'2000-06-01'})
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json()['feng_shui']['element'],'Kim')
        advice.assert_not_called();post.assert_not_called()
        self.assertEqual(self.client.post('/feng-shui',data={'birth_date':'2999-01-01'}).status_code,400)

    def test_consent_profile_and_file_required_before_provider(self):
        with patch.object(backend,'get_style_advice') as advice:
            self.assertEqual(self.request(consent='false').json()['code'],'consent_required')
            self.assertEqual(self.request(consent_provider='gemini').status_code,400)
            self.assertEqual(self.request(height_cm='NaN').status_code,400)
            self.assertEqual(self.request(birth_date='2001-02-29').status_code,400)
            self.assertEqual(self.request(occasion='invalid').status_code,400)
            self.assertEqual(self.client.post('/style-advice',data={'height_cm':'170','weight_kg':'65'}).status_code,422)
        advice.assert_not_called()

    def test_api_uses_photo_and_measurements_and_handles_opt_out(self):
        with patch.object(backend,'get_style_advice',return_value='Gợi ý theo ảnh') as advice:
            result = self.request().json()
        self.assertEqual(result['status'],'ready')
        self.assertIsNone(result['feng_shui'])
        self.assertEqual(advice.call_args.args[1:3],(170.,65.))
        self.assertIsNone(advice.call_args.args[5])

    def test_local_palette_remains_available_if_ai_quota_fails(self):
        with patch.object(backend,'get_style_advice',side_effect=TryOnError('Hết hạn mức','daily_quota_exceeded',429)):
            response = self.request(birth_date='2000-06-01')
        self.assertEqual(response.status_code,429)
        result = response.json()
        self.assertEqual(result['status'],'ai_unavailable')
        self.assertEqual(result['advice'],'')
        self.assertEqual(result['feng_shui']['element'],'Kim')

    def test_busy_request_does_not_queue_extra_provider_calls(self):
        with patch.object(backend.style_lock,'locked',return_value=True),patch.object(backend,'get_style_advice') as advice:
            self.assertEqual(self.request().json()['code'],'busy')
        advice.assert_not_called()

    def test_web_renders_new_card_and_script(self):
        response = self.client.get('/')
        self.assertEqual(response.status_code,200)
        self.assertIn('id="advisorCard"',response.text)
        self.assertIn('/static/js/style_advisor.js?v=160',response.text)


if __name__ == '__main__':
    unittest.main()
