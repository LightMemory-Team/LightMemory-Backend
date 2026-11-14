"""建立（或重設）demo 用的 admin_demo 帳號。demo 前跑一次就好：

    python manage.py setup_admin_demo

帳號：admin_demo／密碼：admin，superuser，暱稱 demo。
已經存在的話會把密碼重設回 admin，資料不會動。
之後到後台 /admin/demo/（維護任務）按按鈕產生展示資料。
"""

from django.core.management.base import BaseCommand

from demo_tools.constants import DEMO_PASSWORD, DEMO_USERNAME
from demo_tools.services import ensure_demo_user


class Command(BaseCommand):
    help = "建立或重設 demo 用的 admin_demo 帳號"

    def handle(self, *args, **options):
        _, created = ensure_demo_user(reset_password=True)
        action = "已建立" if created else "已重設"
        self.stdout.write(
            self.style.SUCCESS(
                f"{action}帳號 {DEMO_USERNAME}（密碼 {DEMO_PASSWORD}），"
                "登入後台後到 /admin/demo/ 產生展示資料"
            )
        )
        self.stdout.write(
            self.style.WARNING("提醒：密碼很簡單，demo 結束後記得改密碼或停用帳號")
        )
