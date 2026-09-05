"""
Unit test：view 與 serializer 層。

用 APIRequestFactory 直接把 request 餵給 view，不經過 URL routing、
不經過 middleware，所以測到的是 view 與 serializer 自己的邏輯。
路徑字串（'/'）只是佔位，不影響結果。

執行：
    python manage.py test users.tests.test_views_unit --settings=config.settings_test
"""

from datetime import date
from unittest import expectedFailure

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIRequestFactory, force_authenticate

from home import views as home_views
from users.serializers import RegisterSerializer
from users.views import RegisterView

User = get_user_model()

# 一組通過所有驗證的註冊資料，各測試以此為基礎再改動需要的欄位
VALID_PAYLOAD = {
    'username': 'wang_yulan',
    'password': 'Str0ng!Pass2026',
    'first_name': '玉蘭',
    'last_name': '王',
    'gender': 'female',
    'birth_date': '1950-01-01',
    'phone': '0912345678',
    'address': '台北市中正區測試路1號',
    'region': 'north',
}


class RegisterSerializerTests(TestCase):
    """RegisterSerializer 的驗證與建立邏輯"""

    def test_valid_payload_creates_user_with_all_fields(self):
        serializer = RegisterSerializer(data=VALID_PAYLOAD)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        user = serializer.save()

        self.assertEqual(user.username, 'wang_yulan')
        self.assertEqual(user.first_name, '玉蘭')
        self.assertEqual(user.last_name, '王')
        self.assertEqual(user.gender, 'female')
        self.assertEqual(user.birth_date, date(1950, 1, 1))
        self.assertEqual(user.phone, '0912345678')
        self.assertEqual(user.address, '台北市中正區測試路1號')
        self.assertEqual(user.region, 'north')

    def test_password_is_hashed_not_stored_as_plaintext(self):
        """create_user 必須雜湊密碼，資料庫不能存明碼"""
        serializer = RegisterSerializer(data=VALID_PAYLOAD)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        user = serializer.save()

        self.assertNotEqual(user.password, VALID_PAYLOAD['password'])
        self.assertTrue(user.check_password(VALID_PAYLOAD['password']))

    def test_password_is_write_only(self):
        """序列化輸出不得包含密碼"""
        serializer = RegisterSerializer(data=VALID_PAYLOAD)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        serializer.save()

        self.assertNotIn('password', serializer.data)

    def test_weak_password_rejected(self):
        """套用 Django 密碼強度驗證：太短、太常見、純數字"""
        serializer = RegisterSerializer(data={**VALID_PAYLOAD, 'password': '123'})

        self.assertFalse(serializer.is_valid())
        self.assertIn('password', serializer.errors)

    @expectedFailure
    def test_password_too_similar_to_username_rejected(self):
        """密碼與帳號過於相似應被拒絕（Notion 對 password 欄位的備註）。

        目前為已知缺口，故標記 expectedFailure：
        settings 有啟用 UserAttributeSimilarityValidator，但 serializer 把
        validate_password 當作「欄位層級」validator（serializers.py 的
        validators=[validate_password]），呼叫時只收到密碼字串、拿不到 user
        物件，因此帳號相似度這條規則實際上不會生效——密碼設成與帳號完全
        相同也能通過註冊。

        修好之後（例如改在 serializer 的 validate() 內呼叫
        validate_password(password, user=User(username=...))），
        請移除這個 @expectedFailure，測試就會轉為正常通過。
        """
        serializer = RegisterSerializer(
            data={**VALID_PAYLOAD, 'username': 'yulan_wang_2026', 'password': 'yulan_wang_2026'}
        )

        self.assertFalse(serializer.is_valid())
        self.assertIn('password', serializer.errors)

    def test_username_and_password_are_required(self):
        serializer = RegisterSerializer(data={})

        self.assertFalse(serializer.is_valid())
        self.assertIn('username', serializer.errors)
        self.assertIn('password', serializer.errors)

    def test_optional_profile_fields_may_be_omitted(self):
        """目前 model 上這些欄位是 blank=True，故 serializer 視為選填。

        若日後前端註冊表單要求全部必填，這個測試會提醒行為已改變。
        """
        serializer = RegisterSerializer(
            data={'username': 'minimal_user', 'password': 'Str0ng!Pass2026'}
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)
        user = serializer.save()

        self.assertEqual(user.first_name, '')
        self.assertEqual(user.last_name, '')
        self.assertEqual(user.gender, '')
        self.assertEqual(user.region, '')
        self.assertIsNone(user.birth_date)

    def test_duplicate_username_rejected(self):
        User.objects.create_user(username='wang_yulan', password='Str0ng!Pass2026')

        serializer = RegisterSerializer(data=VALID_PAYLOAD)

        self.assertFalse(serializer.is_valid())
        self.assertIn('username', serializer.errors)

    def test_invalid_gender_choice_rejected(self):
        serializer = RegisterSerializer(data={**VALID_PAYLOAD, 'gender': 'unknown'})

        self.assertFalse(serializer.is_valid())
        self.assertIn('gender', serializer.errors)

    def test_invalid_region_choice_rejected(self):
        """region 僅接受 north / central / south / east"""
        serializer = RegisterSerializer(data={**VALID_PAYLOAD, 'region': 'northwest'})

        self.assertFalse(serializer.is_valid())
        self.assertIn('region', serializer.errors)

    def test_all_documented_region_choices_accepted(self):
        for index, region in enumerate(['north', 'central', 'south', 'east']):
            with self.subTest(region=region):
                serializer = RegisterSerializer(
                    data={**VALID_PAYLOAD, 'username': f'user_{index}', 'region': region}
                )
                self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_all_documented_gender_choices_accepted(self):
        for index, gender in enumerate(['male', 'female', 'other']):
            with self.subTest(gender=gender):
                serializer = RegisterSerializer(
                    data={**VALID_PAYLOAD, 'username': f'user_g{index}', 'gender': gender}
                )
                self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_malformed_birth_date_rejected(self):
        serializer = RegisterSerializer(data={**VALID_PAYLOAD, 'birth_date': '1950/01/01x'})

        self.assertFalse(serializer.is_valid())
        self.assertIn('birth_date', serializer.errors)

    def test_privileged_fields_cannot_be_set_via_registration(self):
        """is_staff / is_superuser 不在 Meta.fields，外部傳入應被忽略"""
        serializer = RegisterSerializer(
            data={**VALID_PAYLOAD, 'is_staff': True, 'is_superuser': True}
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)
        user = serializer.save()

        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)


class RegisterViewTests(TestCase):
    """RegisterView 本身：不走 URL routing，直接呼叫 view"""

    def setUp(self):
        self.factory = APIRequestFactory()
        self.view = RegisterView.as_view()

    def test_register_returns_201_and_omits_password(self):
        request = self.factory.post('/', VALID_PAYLOAD, format='json')

        response = self.view(request)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertNotIn('password', response.data)
        self.assertEqual(response.data['username'], 'wang_yulan')

    def test_register_persists_user(self):
        request = self.factory.post('/', VALID_PAYLOAD, format='json')

        self.view(request)

        self.assertTrue(User.objects.filter(username='wang_yulan').exists())

    def test_invalid_payload_returns_400_and_creates_nothing(self):
        request = self.factory.post('/', {**VALID_PAYLOAD, 'password': '123'}, format='json')

        response = self.view(request)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('password', response.data)
        self.assertFalse(User.objects.filter(username='wang_yulan').exists())

    def test_register_allows_anonymous_access(self):
        """註冊必須開放未登入者使用（permission_classes = AllowAny）"""
        request = self.factory.post('/', VALID_PAYLOAD, format='json')

        response = self.view(request)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_get_not_allowed(self):
        """CreateAPIView 只接受 POST"""
        request = self.factory.get('/')

        response = self.view(request)

        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)


class HomeViewUnitTests(TestCase):
    """home 系列 view 的單元測試。

    這些 view 目前是 AllowAny，且 get_user 取資料庫第一筆而非登入者
    （見 home/views.py 註解）。此處測的是「現況」，等 README 規劃的
    JWT 驗證導入後，這些測試會失敗並提醒你更新預期行為。
    """

    def setUp(self):
        self.factory = APIRequestFactory()

    def test_ping_returns_connection_message(self):
        response = home_views.ping(self.factory.get('/'))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, {'message': 'index api is connected'})

    def test_get_user_returns_404_when_no_user_exists(self):
        response = home_views.get_user(self.factory.get('/'))

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertIn('user_name_error', response.data)

    def test_get_user_returns_last_name(self):
        User.objects.create_user(
            username='wang_yulan', password='Str0ng!Pass2026', last_name='王'
        )

        response = home_views.get_user(self.factory.get('/'))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, {'user_name': '王'})

    def test_greet_returns_a_tip_from_the_fixed_list(self):
        response = home_views.greet(self.factory.get('/'))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn(
            response.data['daily_tip'],
            [
                '今天也要保持大腦活力喔。',
                '早安,今天心情如何呢？',
                '陽光正好,適合散散步。',
            ],
        )

    def test_greet_is_stable_within_the_same_day(self):
        """問候語由日期決定，同一天內重複呼叫應一致"""
        first = home_views.greet(self.factory.get('/'))
        second = home_views.greet(self.factory.get('/'))

        self.assertEqual(first.data, second.data)

    def test_daily_suggestion_returns_text_and_route(self):
        response = home_views.daily_suggetion(self.factory.get('/'))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('text', response.data['daily_suggestion'])
        self.assertIn('action_route', response.data['daily_suggestion'])

    def test_force_authenticate_does_not_break_allowany_view(self):
        """示範 force_authenticate 用法：待 home API 套上 JWT 後，
        這是免打 login 就能測受保護 view 的方式。
        """
        user = User.objects.create_user(
            username='wang_yulan', password='Str0ng!Pass2026', last_name='王'
        )
        request = self.factory.get('/')
        force_authenticate(request, user=user)

        response = home_views.get_user(request)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
