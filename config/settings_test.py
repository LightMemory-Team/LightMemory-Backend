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

from .settings import *  # noqa: F401,F403

# 測試資料庫改用 SQLite in-memory，免 CREATEDB 權限
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': ':memory:',
    }
}

# 專案的 ALLOWED_HOSTS 是空的，測試客戶端會用 testserver 這個 host
ALLOWED_HOSTS = ['testserver', 'localhost', '127.0.0.1']

# 測試不需要看 debug 頁面，關掉才會拿到 DRF 的 JSON 錯誤回應
DEBUG = False

# 密碼雜湊改用最快的演算法，加快建立測試使用者的速度
PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']
