"""
System test：端到端流程。

用 APIClient 打真實 URL，完整經過 URL routing、middleware、
認證與序列化，驗證前端實際會拿到的行為。

對應 Notion「使用者（Users）API 需求」的三支端點：
    POST /api/users/register/
    POST /api/users/login/
    POST /api/users/login/refresh/

執行：
    python manage.py test users.tests.test_api_system --settings=config.settings_test
"""

from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.settings import api_settings

User = get_user_model()

REGISTER_URL = '/api/users/register/'
LOGIN_URL = '/api/users/login/'
REFRESH_URL = '/api/users/login/refresh/'

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


class RegisterEndpointTests(APITestCase):
    """POST /api/users/register/"""

    def test_register_success_returns_201_with_profile(self):
        response = self.client.post(REGISTER_URL, VALID_PAYLOAD, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['username'], 'wang_yulan')
        self.assertEqual(response.data['last_name'], '王')
        self.assertEqual(response.data['region'], 'north')

    def test_register_response_never_contains_password(self):
        response = self.client.post(REGISTER_URL, VALID_PAYLOAD, format='json')

        self.assertNotIn('password', response.data)

    def test_register_stores_all_profile_fields(self):
        self.client.post(REGISTER_URL, VALID_PAYLOAD, format='json')

        user = User.objects.get(username='wang_yulan')
        self.assertEqual(user.first_name, '玉蘭')
        self.assertEqual(user.phone, '0912345678')
        self.assertEqual(user.address, '台北市中正區測試路1號')
        self.assertEqual(user.gender, 'female')
        self.assertTrue(user.check_password('Str0ng!Pass2026'))

    def test_register_with_weak_password_returns_400(self):
        response = self.client.post(
            REGISTER_URL, {**VALID_PAYLOAD, 'password': '123'}, format='json'
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('password', response.data)

    def test_register_with_duplicate_username_returns_400(self):
        self.client.post(REGISTER_URL, VALID_PAYLOAD, format='json')

        response = self.client.post(REGISTER_URL, VALID_PAYLOAD, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('username', response.data)
        self.assertEqual(User.objects.filter(username='wang_yulan').count(), 1)

    def test_register_with_invalid_region_returns_400(self):
        response = self.client.post(
            REGISTER_URL, {**VALID_PAYLOAD, 'region': 'northwest'}, format='json'
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('region', response.data)

    def test_register_requires_no_authentication(self):
        """未帶任何憑證也能註冊"""
        self.client.credentials()  # 確保沒有殘留的 Authorization header

        response = self.client.post(REGISTER_URL, VALID_PAYLOAD, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_register_url_name_resolves(self):
        self.assertEqual(reverse('register'), REGISTER_URL)


class LoginEndpointTests(APITestCase):
    """POST /api/users/login/"""

    def setUp(self):
        self.client.post(REGISTER_URL, VALID_PAYLOAD, format='json')
        self.credentials = {
            'username': VALID_PAYLOAD['username'],
            'password': VALID_PAYLOAD['password'],
        }

    def test_login_success_returns_access_and_refresh(self):
        response = self.client.post(LOGIN_URL, self.credentials, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('access', response.data)
        self.assertIn('refresh', response.data)

    def test_tokens_are_jwt_shaped(self):
        """JWT 由三段以 . 分隔的 base64 組成"""
        response = self.client.post(LOGIN_URL, self.credentials, format='json')

        for key in ('access', 'refresh'):
            with self.subTest(token=key):
                self.assertEqual(len(response.data[key].split('.')), 3)

    def test_login_with_wrong_password_returns_401(self):
        response = self.client.post(
            LOGIN_URL, {**self.credentials, 'password': 'WrongPass!2026'}, format='json'
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertNotIn('access', response.data)

    def test_login_with_unknown_username_returns_401(self):
        response = self.client.post(
            LOGIN_URL, {'username': 'nobody', 'password': 'Str0ng!Pass2026'}, format='json'
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_login_without_credentials_returns_400(self):
        response = self.client.post(LOGIN_URL, {}, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_inactive_user_cannot_login(self):
        user = User.objects.get(username='wang_yulan')
        user.is_active = False
        user.save()

        response = self.client.post(LOGIN_URL, self.credentials, format='json')

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_token_lifetimes_match_documented_values(self):
        """Notion 記載 access 短效期（5 分鐘）、refresh 長效期（1 天）。

        專案未設定 SIMPLE_JWT，目前沿用 simplejwt 預設值。
        日後若在 settings 覆寫效期，這個測試會提醒文件需同步更新。
        """
        self.assertEqual(api_settings.ACCESS_TOKEN_LIFETIME.total_seconds(), 5 * 60)
        self.assertEqual(api_settings.REFRESH_TOKEN_LIFETIME.total_seconds(), 24 * 60 * 60)


class TokenRefreshEndpointTests(APITestCase):
    """POST /api/users/login/refresh/"""

    def setUp(self):
        self.client.post(REGISTER_URL, VALID_PAYLOAD, format='json')
        login = self.client.post(
            LOGIN_URL,
            {'username': VALID_PAYLOAD['username'], 'password': VALID_PAYLOAD['password']},
            format='json',
        )
        self.refresh_token = login.data['refresh']

    def test_refresh_returns_new_access_token(self):
        response = self.client.post(
            REFRESH_URL, {'refresh': self.refresh_token}, format='json'
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('access', response.data)
        self.assertEqual(len(response.data['access'].split('.')), 3)

    def test_refresh_with_invalid_token_returns_401(self):
        response = self.client.post(
            REFRESH_URL, {'refresh': 'not.a.token'}, format='json'
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_refresh_without_token_returns_400(self):
        response = self.client.post(REFRESH_URL, {}, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_access_token_cannot_be_used_as_refresh_token(self):
        login = self.client.post(
            LOGIN_URL,
            {'username': VALID_PAYLOAD['username'], 'password': VALID_PAYLOAD['password']},
            format='json',
        )

        response = self.client.post(
            REFRESH_URL, {'refresh': login.data['access']}, format='json'
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class RegistrationToAuthenticatedRequestFlowTests(APITestCase):
    """完整流程：註冊 → 登入 → 用 access token 存取 → refresh 換新 token"""

    def test_full_user_journey(self):
        # 1. 註冊
        register = self.client.post(REGISTER_URL, VALID_PAYLOAD, format='json')
        self.assertEqual(register.status_code, status.HTTP_201_CREATED)

        # 2. 登入取得雙 token
        login = self.client.post(
            LOGIN_URL,
            {'username': VALID_PAYLOAD['username'], 'password': VALID_PAYLOAD['password']},
            format='json',
        )
        self.assertEqual(login.status_code, status.HTTP_200_OK)
        access, refresh = login.data['access'], login.data['refresh']

        # 3. 帶 access token 存取 API
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {access}')
        protected = self.client.get('/api/home/user/')
        self.assertEqual(protected.status_code, status.HTTP_200_OK)

        # 4. 用 refresh token 換新的 access token，且能繼續存取
        renewed = self.client.post(REFRESH_URL, {'refresh': refresh}, format='json')
        self.assertEqual(renewed.status_code, status.HTTP_200_OK)

        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {renewed.data["access"]}')
        after_refresh = self.client.get('/api/home/user/')
        self.assertEqual(after_refresh.status_code, status.HTTP_200_OK)

    def test_registered_user_can_login_immediately(self):
        """註冊完不需額外啟用步驟即可登入"""
        self.client.post(REGISTER_URL, VALID_PAYLOAD, format='json')

        login = self.client.post(
            LOGIN_URL,
            {'username': VALID_PAYLOAD['username'], 'password': VALID_PAYLOAD['password']},
            format='json',
        )

        self.assertEqual(login.status_code, status.HTTP_200_OK)

    def test_garbage_bearer_token_is_rejected(self):
        self.client.credentials(HTTP_AUTHORIZATION='Bearer not.a.real.token')

        response = self.client.get('/api/home/user/')

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class HomeEndpointSystemTests(APITestCase):
    """home 系列端點的端到端行為。

    這些端點目前是 AllowAny（README 規劃中要改為 IsAuthenticated），
    所以此處驗證的是現況：未登入也能存取。改用 JWT 驗證後，
    test_home_endpoints_currently_allow_anonymous 會失敗，
    正好作為提醒。
    """

    def test_ping_is_reachable(self):
        response = self.client.get('/api/home/ping/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['message'], 'index api is connected')

    def test_home_endpoints_currently_allow_anonymous(self):
        for url in [
            '/api/home/ping/',
            '/api/home/greet/',
            '/api/home/daily_suggetion/',
            '/api/home/games/',
        ]:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_get_user_returns_404_before_any_user_registers(self):
        response = self.client.get('/api/home/user/')

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_get_user_returns_last_name_after_registration(self):
        self.client.post(REGISTER_URL, VALID_PAYLOAD, format='json')

        response = self.client.get('/api/home/user/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['user_name'], '王')

    def test_games_list_returns_empty_list_when_no_games(self):
        response = self.client.get('/api/home/games/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, {'games': []})
