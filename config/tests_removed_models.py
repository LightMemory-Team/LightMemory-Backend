"""已移除的診斷性模型（F12）。

Ad8Record（AD-8 失智篩檢量表）與 HealthDashboardRecord（腦年齡、警示等級）
沒有任何 API 使用，且屬於診斷性質，已移除。

確認：模型不存在、資料表被刪除、migration 可以倒退再重新套用、沒有遺漏的 migration。

執行：
    python manage.py test config.tests_removed_models --settings=config.settings_test
"""

from django.apps import apps
from django.core.management import call_command
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import SimpleTestCase, TestCase, TransactionTestCase

REMOVED_TABLES = ["assessments_ad8record", "dashboard_healthdashboardrecord"]


class RemovedModelsTests(SimpleTestCase):
    def test_models_no_longer_exist(self):
        for app_label, model_name in [
            ("assessments", "Ad8Record"),
            ("dashboard", "HealthDashboardRecord"),
        ]:
            with self.subTest(model=model_name):
                with self.assertRaises(LookupError):
                    apps.get_model(app_label, model_name)

    def test_weekly_report_model_is_still_there(self):
        self.assertIsNotNone(apps.get_model("dashboard", "WeeklyReport"))


class MigrationsInSyncTests(TestCase):
    def test_no_missing_migrations(self):
        # 模型與 migration 同步：有遺漏會以 SystemExit(1) 結束
        call_command("makemigrations", check=True, dry_run=True, verbosity=0)


class RemovedTablesMigrationTests(TransactionTestCase):
    def table_names(self):
        return set(connection.introspection.table_names())

    def migrate_to(self, targets):
        executor = MigrationExecutor(connection)
        executor.migrate(targets)
        executor.loader.build_graph()

    def latest(self):
        return list(MigrationExecutor(connection).loader.graph.leaf_nodes())

    def tearDown(self):
        # 不管測試結果如何，都把資料庫恢復到最新
        self.migrate_to(self.latest())

    def test_tables_are_dropped_by_the_latest_migrations(self):
        self.migrate_to(self.latest())

        self.assertFalse(set(REMOVED_TABLES) & self.table_names())

    def test_migrations_can_be_reversed_and_applied_again(self):
        before = [("assessments", "0001_initial"), ("dashboard", "0002_weeklyreport")]

        self.migrate_to(before)
        self.assertTrue(set(REMOVED_TABLES) <= self.table_names())

        self.migrate_to(self.latest())
        self.assertFalse(set(REMOVED_TABLES) & self.table_names())

    def test_weekly_report_table_is_untouched(self):
        self.migrate_to(self.latest())

        self.assertIn("dashboard_weeklyreport", self.table_names())
