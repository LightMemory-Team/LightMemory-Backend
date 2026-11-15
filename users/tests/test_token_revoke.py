"""改密碼（或忘記密碼重設）後，舊的登入 token 全部作廢（G4 精簡版）。

以前換密碼之後，舊的 access／refresh token 還是能用，最久 30 天。
如果密碼是被盜用才換掉的，攻擊者手上的 token 仍然有效。

現在 token 裡記一份「簽發當時密碼的雜湊」，驗證時跟目前的密碼比對，
對不上就回 401。換 token 的端點也有同樣檢查（否則舊的 refresh token 還能換到
新的 access token，只是一用就被拒絕，前端會一直重試）。

不會誤殺的情況（也有測試）：
- 在另一台裝置登入（會更新 last_login，但密碼沒變）
- 修改暱稱等個人資料
- 別的使用者改密碼

執行：
    python manage.py test users.tests.test_token_revoke --settings=config.settings_test
"""

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import SimpleTestCase
from rest_framework import status
from rest_framework.test import APIClient, APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

User = get_user_model()

LOGIN_URL = "/api/users/login/"
REFRESH_URL = "/api/users/login/refresh/"
ME_URL = "/api/users/me/"
PASSWORD_URL = "/api/users/me/password/"
RESET_URL = "/api/users/password-reset/"

OLD_PASSWORD = "Old!Pass2026"
NEW_PASSWORD = "New!Pass2026x"


def bearer(token):
    return {"HTTP_AUTHORIZATION": f"Bearer {token}"}


class TokenRevokeTestCase(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="alice", password=OLD_PASSWORD)
        self.client = APIClient()
        tokens = self.login()
        self.access, self.refresh = tokens["access"], tokens["refresh"]

    def login(self, username="alice", password=OLD_PASSWORD):
        response = APIClient().post(
            LOGIN_URL, {"username": username, "password": password}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        return response.data

    def me(self, access):
        return self.client.get(ME_URL, **bearer(access))

    def refresh_with(self, refresh):
        return self.client.post(REFRESH_URL, {"refresh": refresh}, format="json")

    def assert_rejected(self, response):
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertFalse(response.data["success"])
        self.assertEqual(response.data["error"]["code"], "NOT_AUTHENTICATED")


class NormalUseTests(TokenRevokeTestCase):
    def test_the_setting_is_on(self):
        self.assertTrue(settings.SIMPLE_JWT["CHECK_REVOKE_TOKEN"])

    def test_a_fresh_login_works(self):
        self.assertEqual(self.me(self.access).status_code, status.HTTP_200_OK)

    def test_refreshing_returns_an_access_token_that_works(self):
        response = self.refresh_with(self.refresh)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(self.me(response.data["access"]).status_code, 200)

    def test_refreshing_can_be_repeated(self):
        for _ in range(3):
            self.assertEqual(self.refresh_with(self.refresh).status_code, 200)

    def test_garbage_refresh_tokens_are_rejected(self):
        for token in ("not.a.token", "", "abc"):
            with self.subTest(token=token):
                response = self.refresh_with(token)
                self.assertIn(response.status_code, (400, 401))


class DoesNotRevokeByMistakeTests(TokenRevokeTestCase):
    def test_logging_in_again_does_not_kill_the_other_devices_token(self):
        self.login()  # 另一台裝置登入，會更新 last_login

        self.assertEqual(self.me(self.access).status_code, 200)
        self.assertEqual(self.refresh_with(self.refresh).status_code, 200)

    def test_editing_the_profile_does_not_revoke_tokens(self):
        response = self.client.patch(
            ME_URL, {"nickname": "新暱稱"}, format="json", **bearer(self.access)
        )
        self.assertEqual(response.status_code, 200)

        self.assertEqual(self.me(self.access).status_code, 200)
        self.assertEqual(self.refresh_with(self.refresh).status_code, 200)

    def test_another_users_password_change_does_not_affect_me(self):
        bob = User.objects.create_user(username="bob", password=OLD_PASSWORD)
        bob_tokens = self.login("bob")
        self.client.post(
            PASSWORD_URL,
            {"old_password": OLD_PASSWORD, "new_password": NEW_PASSWORD},
            format="json",
            **bearer(bob_tokens["access"]),
        )
        bob.refresh_from_db()

        self.assertEqual(self.me(self.access).status_code, 200)
        self.assertEqual(self.refresh_with(self.refresh).status_code, 200)

    def test_a_failed_password_change_does_not_revoke_tokens(self):
        response = self.client.post(
            PASSWORD_URL,
            {"old_password": "wrong", "new_password": NEW_PASSWORD},
            format="json",
            **bearer(self.access),
        )
        self.assertEqual(response.status_code, 400)

        self.assertEqual(self.me(self.access).status_code, 200)


class PasswordChangeTests(TokenRevokeTestCase):
    def change_password(self):
        return self.client.post(
            PASSWORD_URL,
            {"old_password": OLD_PASSWORD, "new_password": NEW_PASSWORD},
            format="json",
            **bearer(self.access),
        )

    def test_the_old_access_token_stops_working(self):
        self.change_password()

        self.assert_rejected(self.me(self.access))

    def test_the_old_refresh_token_can_no_longer_get_a_new_access_token(self):
        self.change_password()

        self.assert_rejected(self.refresh_with(self.refresh))

    def test_the_tokens_in_the_response_work(self):
        response = self.change_password()
        tokens = response.data["data"]

        self.assertEqual(self.me(tokens["access"]).status_code, 200)
        refreshed = self.refresh_with(tokens["refresh"])
        self.assertEqual(refreshed.status_code, 200)
        self.assertEqual(self.me(refreshed.data["access"]).status_code, 200)

    def test_logging_in_with_the_new_password_works(self):
        self.change_password()

        tokens = self.login(password=NEW_PASSWORD)

        self.assertEqual(self.me(tokens["access"]).status_code, 200)

    def test_every_old_session_is_revoked_not_just_the_one_that_changed_it(self):
        other_device = self.login()  # 另一台裝置也登入過
        self.change_password()

        self.assert_rejected(self.me(other_device["access"]))
        self.assert_rejected(self.refresh_with(other_device["refresh"]))


class PasswordResetTests(TokenRevokeTestCase):
    """忘記密碼重設：攻擊者手上的舊 token 要一起作廢。"""

    def reset_password(self):
        response = APIClient().post(
            RESET_URL,
            {
                "username": "alice",
                "new_password": NEW_PASSWORD,
                "new_password_confirm": NEW_PASSWORD,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200)

    def test_old_tokens_stop_working_after_a_reset(self):
        self.reset_password()

        self.assert_rejected(self.me(self.access))
        self.assert_rejected(self.refresh_with(self.refresh))

    def test_the_user_can_log_in_again_with_the_new_password(self):
        self.reset_password()

        tokens = self.login(password=NEW_PASSWORD)

        self.assertEqual(self.me(tokens["access"]).status_code, 200)


class OldTokensTests(TokenRevokeTestCase):
    def test_tokens_issued_before_the_check_existed_are_rejected(self):
        # 還沒開啟這個功能時簽發的 token 沒有「密碼雜湊」，開啟後要重新登入一次
        refresh = RefreshToken.for_user(self.user)
        del refresh["hash_password"]
        access = refresh.access_token
        self.assertNotIn("hash_password", access.payload)

        self.assert_rejected(self.me(str(access)))
        self.assert_rejected(self.refresh_with(str(refresh)))


class AccountStateTests(TokenRevokeTestCase):
    def test_a_deleted_accounts_refresh_token_gets_401_not_500(self):
        User.objects.filter(pk=self.user.pk).delete()

        self.assert_rejected(self.refresh_with(self.refresh))

    def test_a_deleted_accounts_access_token_is_rejected(self):
        User.objects.filter(pk=self.user.pk).delete()

        self.assert_rejected(self.me(self.access))

    def test_a_deactivated_accounts_refresh_token_is_rejected(self):
        User.objects.filter(pk=self.user.pk).update(is_active=False)

        self.assertEqual(
            self.refresh_with(self.refresh).status_code, status.HTTP_401_UNAUTHORIZED
        )


class TokenContentTests(SimpleTestCase):
    def test_tokens_carry_a_password_fingerprint_but_not_the_password(self):
        user = User(username="x", password="pbkdf2_sha256$1$salt$hash")
        user.pk = 1

        token = RefreshToken.for_user(user)

        fingerprint = token["hash_password"]
        self.assertEqual(len(fingerprint), 32)  # MD5 十六進位
        self.assertNotIn("pbkdf2", str(token.payload))
        self.assertNotIn("salt", str(token.payload))
