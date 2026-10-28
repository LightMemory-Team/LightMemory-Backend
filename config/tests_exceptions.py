from django.http import Http404
from django.test import SimpleTestCase
from rest_framework import exceptions

from config.exceptions import ApiError, api_exception_handler


class ApiExceptionHandlerTests(SimpleTestCase):
    def call(self, exc):
        response = api_exception_handler(exc, {})
        return response.status_code, response.data

    def test_envelope_shape(self):
        status_code, body = self.call(exceptions.NotFound())
        self.assertEqual(status_code, 404)
        self.assertIs(body["success"], False)
        self.assertIsNone(body["data"])
        self.assertEqual(set(body["error"]), {"code", "message"})

    def test_validation_error_has_fields(self):
        exc = exceptions.ValidationError({"nickname": ["暱稱不能是空白"]})
        status_code, body = self.call(exc)
        self.assertEqual(status_code, 400)
        self.assertEqual(body["error"]["code"], "VALIDATION_ERROR")
        self.assertEqual(body["error"]["fields"], {"nickname": ["暱稱不能是空白"]})

    def test_non_field_validation_error_uses_message(self):
        status_code, body = self.call(exceptions.ValidationError(["兩次密碼不同"]))
        self.assertEqual(status_code, 400)
        self.assertEqual(body["error"]["message"], "兩次密碼不同")
        self.assertNotIn("fields", body["error"])

    def test_not_authenticated(self):
        status_code, body = self.call(exceptions.NotAuthenticated())
        self.assertEqual(status_code, 401)
        self.assertEqual(body["error"]["code"], "NOT_AUTHENTICATED")

    def test_login_failure_message(self):
        exc = exceptions.AuthenticationFailed(code="no_active_account")
        _, body = self.call(exc)
        self.assertEqual(body["error"]["message"], "帳號或密碼錯誤")

    def test_django_404_becomes_not_found(self):
        status_code, body = self.call(Http404())
        self.assertEqual(status_code, 404)
        self.assertEqual(body["error"]["code"], "NOT_FOUND")

    def test_permission_denied(self):
        status_code, body = self.call(exceptions.PermissionDenied())
        self.assertEqual(status_code, 403)
        self.assertEqual(body["error"]["code"], "FORBIDDEN")

    def test_api_error_custom_code(self):
        exc = ApiError("USERNAME_TAKEN", "這個帳號已經被註冊過")
        status_code, body = self.call(exc)
        self.assertEqual(status_code, 400)
        self.assertEqual(body["error"]["code"], "USERNAME_TAKEN")
        self.assertEqual(body["error"]["message"], "這個帳號已經被註冊過")

    def test_api_error_custom_status(self):
        exc = ApiError("ACCOUNT_NOT_FOUND", "找不到這個帳號", status_code=404)
        status_code, body = self.call(exc)
        self.assertEqual(status_code, 404)
        self.assertEqual(body["error"]["code"], "ACCOUNT_NOT_FOUND")

    def test_unexpected_exception_is_server_error(self):
        with self.assertLogs("config.exceptions", level="ERROR"):
            status_code, body = self.call(RuntimeError("boom"))
        self.assertEqual(status_code, 500)
        self.assertEqual(body["error"]["code"], "SERVER_ERROR")
        # 不能把內部錯誤訊息洩漏給使用者
        self.assertNotIn("boom", body["error"]["message"])
