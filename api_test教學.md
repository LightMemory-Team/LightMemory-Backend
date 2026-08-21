# API 測試教學（DRF Browsable API）

Django REST Framework 內建一個「可瀏覽的 API 介面」（Browsable API）,只要用瀏覽器打開 API 網址就能測試,不需要裝 Postman、也不需要裝任何擴充套件。

---

## 一、原理

專案的 `settings.py` 裡有這段設定:

```python
REST_FRAMEWORK = {
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.AllowAny',
    ],
}
```

因為 `AllowAny`,所有人都能直接呼叫這些 API,不需要登入驗證。DRF 只要偵測到請求是從**瀏覽器**發出的(而不是程式呼叫),就會自動回傳一個好看的 HTML 頁面,而不是純 JSON——這個頁面就是 Browsable API。

---

## 二、啟動伺服器

```bash
source venv/bin/activate
python manage.py runserver
```

---

## 三、直接用瀏覽器打開網址

因為目前 `home` app 的 API 都是 `GET` 方法,最簡單的測試方式就是把網址貼到瀏覽器網址列,直接按 Enter:

| API | 網址 |
|---|---|
| 測試首頁連線 | `http://127.0.0.1:8000/api/home/ping/` |
| 使用者姓名 | `http://127.0.0.1:8000/api/home/user/` |
| 問候副標 | `http://127.0.0.1:8000/api/home/greet/` |
| 每日建議 | `http://127.0.0.1:8000/api/home/daily_suggetion/` |
| 遊戲卡片列表 | `http://127.0.0.1:8000/api/home/games/` |

---

## 四、頁面長什麼樣子

打開後畫面上會有:

- **上方**:網址、HTTP 狀態碼(例如 `GET 200 OK`)
- **中間**:回傳的 JSON 內容(用縮排、上色顯示,比純文字好讀)
- **右上角 `GET` / `OPTIONS` 按鈕**:可以查看這支 API 支援哪些 HTTP 方法
- **下方(如果 API 支援 POST)**:會出現一個表單,可以直接在頁面上填欄位、送出 POST 請求,不用寫任何程式碼

目前 `home` app 的 API 都只做 `GET`,所以主要會用到「中間顯示 JSON」這部分。

---

## 五、預期結果對照

| API | 預期回應範例 |
|---|---|
| `ping/` | `{"message": "index api is connected"}` |
| `user/` | `{"user_name": "..."}`(資料庫第一筆使用者的 `name`,空字串代表該筆資料沒填名字） |
| `greet/` | `{"daily_tip": "..."}`(依當天日期固定挑一句） |
| `daily_suggetion/` | `{"daily_suggestion": {"text": "完成一場菜市場遊戲", "action_route": "game_market_sort"}}` |
| `games/` | `{"games": [...]}`(目前資料庫 `games_game` 是空的,會回傳 `{"games": []}`,需要先手動新增遊戲資料才有內容） |

---

## 六、常見狀況排查

| 現象 | 可能原因 |
|---|---|
| 瀏覽器顯示「無法連上這個網站」 | `runserver` 沒有啟動,或忘記先 `source venv/bin/activate` |
| `404 Not Found`(白底黑字的錯誤頁） | 網址路徑打錯,或 `home/urls.py` 忘記加這條路由 |
| `500 Internal Server Error` | 程式邏輯有錯,看終端機裡 `runserver` 印出的錯誤訊息(Traceback)最後一行 |
| 畫面是純 JSON 沒有 DRF 的美化介面 | 通常是用 `curl` 或其他工具打的,不是用瀏覽器直接開網址;用瀏覽器打開才會看到 Browsable API 介面 |
| 回傳的資料是空的 `""` 或 `[]` | 不是程式錯誤,是資料庫裡本來就沒有資料,去 `/admin` 或 psql 補資料 |

---

## 七、進度對照

目前完成度詳見 [checklist.md](checklist.md)。
