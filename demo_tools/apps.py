from django.apps import AppConfig


class DemoToolsConfig(AppConfig):
    """複賽 demo 用的後台工具：維護任務頁（/admin/demo/）與 admin_demo 帳號。"""

    name = "demo_tools"
    verbose_name = "Demo 展示工具"
