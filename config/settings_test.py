"""
測試專用設定。

用途：讓 `manage.py test` 不必依賴 PostgreSQL 的 CREATEDB 權限。
Django 跑測試時會建立 test_<DB_NAME> 資料庫，若 .env 裡的 DB_USER
沒有 CREATEDB 權限就會失敗（permission denied to create database）。
這份設定把測試資料庫換成 SQLite in-memory，不需要任何 DB 權限，速度也快。

用法：
    python manage.py test --settings=config.settings_test

取捨：SQLite 測不到 PostgreSQL 特有行為（例如 JSONField 查詢細節、
並發鎖定、資料庫層級的 constraint 差異）。正式環境是 PostgreSQL，
所以若要完整驗證，請改用有 CREATEDB 權限的帳號跑預設 settings：
    ALTER USER <你的使用者> CREATEDB;
    python manage.py test
"""

import os

# 測試不依賴 .env 裡有沒有金鑰：settings 在 DEBUG 關閉時一定要有 DJANGO_SECRET_KEY，
# 這裡先補一把測試專用的（沒有 "django-insecure-" 開頭，不會被正式環境檢查擋掉）。
os.environ.setdefault("DJANGO_SECRET_KEY", "test-only-secret-key-not-for-real-use")

from .settings import *  # noqa: E402,F401,F403

# 測試資料庫改用 SQLite in-memory，免 CREATEDB 權限
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': ':memory:',
    }
}

# 請求次數限制：測試之間共用同一份記憶體快取，把上限調得很高，免得別的測試
# 不小心累積到上限。要測限速行為的測試自己用 patch 套上真正的次數
# （見 users/tests/test_auth_throttle.py）。
REST_FRAMEWORK = {
    **REST_FRAMEWORK,  # noqa: F405
    "DEFAULT_THROTTLE_RATES": {
        scope: "100000/hour"
        for scope in REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]  # noqa: F405
    },
}

# 專案的 ALLOWED_HOSTS 是空的，測試客戶端會用 testserver 這個 host
ALLOWED_HOSTS = ['testserver', 'localhost', '127.0.0.1']

# 測試不需要看 debug 頁面，關掉才會拿到 DRF 的 JSON 錯誤回應
DEBUG = False

# 密碼雜湊改用最快的演算法，加快建立測試使用者的速度
PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']
