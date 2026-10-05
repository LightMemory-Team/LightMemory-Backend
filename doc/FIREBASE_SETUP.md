# Firebase Storage 建置說明

> 本次更新內容：將 Firebase Storage 串接至 Django 後端，用於儲存聲影日記的圖片、音訊與影片檔案。

---

## 這次更新了什麼

1. 建立 Firebase Storage
2. 建立聲影日記媒體檔案資料夾
3. Django 串接 Firebase Admin SDK
4. 新增 Firebase Storage Bucket 設定
5. Firebase 私密金鑰統一存放於 `secrets/`
6. 將私密憑證加入 `.gitignore`
7. `.env.example` 新增 Firebase Storage 環境變數
8. 完成 Django 上傳圖片至 Firebase Storage 測試

---

## Firebase Storage 結構

```text
voice-diary/
├── images/
├── audio/
└── videos/
```

- `images/`：聲影日記圖片
- `audio/`：聲影日記錄音
- `videos/`：影片檔案

---

## 組員需要做的事

### 1. Pull 最新程式碼

```bash
git pull
```

### 2. 安裝套件

```bash
pip install -r requirements.txt
```

### 3. 建立 Firebase Service Account

進入 Firebase Console：

專案設定 → 服務帳戶 → Firebase Admin SDK → 產生新的私密金鑰

下載 JSON 金鑰後放到：

```text
secrets/firebase-key.json
```

> Firebase Service Account JSON 為私密憑證，不可上傳至 GitHub。

---

## 設定 `.env`

複製專案中的：

```text
.env.example
```

建立：

```text
.env
```

Firebase 相關設定：

```env
FIREBASE_PROJECT_ID=你的Firebase專案ID
FIREBASE_CREDENTIALS_PATH=secrets/firebase-key.json
FIREBASE_STORAGE_BUCKET=lightmemory-sqlf.firebasestorage.app
```

> `.env` 不可上傳至 GitHub。

---

## 驗證是否成功

進入 Django shell：

```bash
python manage.py shell
```

輸入：

```python
from config.firebase import firebase_app
from firebase_admin import storage

bucket = storage.bucket(app=firebase_app)
print(bucket.name)
```

正常情況應顯示：

```text
lightmemory-sqlf.firebasestorage.app
```

代表 Django 已成功連線 Firebase Storage。

---

## 注意事項

- `.env` 不可上傳至 GitHub
- Firebase Service Account JSON 不可上傳至 GitHub
- 私密憑證統一放置於 `secrets/`
- `.env.example` 可以上傳 GitHub
- Firebase Storage 用於儲存圖片、音訊與影片
- PostgreSQL 仍負責一般資料與檔案路徑