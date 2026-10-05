"""
System test：Django admin 後台。

確認每個註冊的 model 在後台的列表頁、新增頁都能正常打開（沒有欄位名稱
打錯之類的設定錯誤），以及在後台建立使用者時密碼會以雜湊儲存。

執行：
    python manage.py test config.tests_admin
"""

from django.contrib import admin
from django.test import TestCase
from django.urls import reverse

from games import session_service
from users.models import User


class AdminPagesTests(TestCase):
    def setUp(self):
        self.admin_user = User.objects.create_superuser(
            username="admin", password="testpass123"
        )
        self.client.force_login(self.admin_user)

    def test_every_registered_model_has_working_changelist_and_add_page(self):
        for model in admin.site._registry:
            opts = model._meta
            with self.subTest(model=opts.label):
                changelist = reverse(
                    f"admin:{opts.app_label}_{opts.model_name}_changelist"
                )
                add = reverse(f"admin:{opts.app_label}_{opts.model_name}_add")

                self.assertEqual(self.client.get(changelist).status_code, 200)
                self.assertEqual(self.client.get(add).status_code, 200)

    def test_game_session_page_shows_step_logs(self):
        session = session_service.create_session(
            "market_route", initial_state={}, user=self.admin_user
        )
        session_service.save_step(
            "market_route",
            session["session_id"],
            {"is_correct": True, "response_time_ms": 400, "stage": "basic"},
        )
        url = reverse("admin:games_gamesession_change", args=[session["session_id"]])

        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "basic")

    def test_add_user_in_admin_stores_hashed_password(self):
        self.client.post(
            reverse("admin:users_user_add"),
            {
                "username": "elder",
                "password1": "Str0ng!Pass2026",
                "password2": "Str0ng!Pass2026",
                "usable_password": "true",
                # 頁面上「家屬聯絡人」inline 的管理欄位（瀏覽器會自動送出）
                "family_contacts-TOTAL_FORMS": "0",
                "family_contacts-INITIAL_FORMS": "0",
            },
        )

        user = User.objects.get(username="elder")
        self.assertNotEqual(user.password, "Str0ng!Pass2026")
        self.assertTrue(user.check_password("Str0ng!Pass2026"))
