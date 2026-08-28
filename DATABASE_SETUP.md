# 資料庫建置說明（PostgreSQL）

> 本次更新內容：將專案資料庫從 SQLite 切換為 PostgreSQL，並依組員提供的資料表設計，建立完整的 11 張資料表（Django Models）。

---

## 目錄

- [這次更新了什麼](#這次更新了什麼)
- [重要觀念：GitHub 上看不到資料庫本身](#重要觀念github-上看不到資料庫本身)
- [資料表結構總覽](#資料表結構總覽)
- [你需要做的事（在自己電腦上設定 PostgreSQL）](#你需要做的事在自己電腦上設定-postgresql)
- [驗證是否成功](#驗證是否成功)
- [migration 有改動時，怎麼乾淨地重建](#migration-有改動時怎麼乾淨地重建)

---

## 這次更新了什麼

1. 資料庫從開發階段的 **SQLite** 換成 **PostgreSQL**
2. 新增 `psycopg2-binary` 套件（Django 用來跟 PostgreSQL 溝通的套件），已寫入 `requirements.txt`
3. 修改 `config/settings.py` 的 `DATABASES` 設定，改為連線 PostgreSQL
4. 新增自訂 User 模型（`users/models.py`），取代 Django 內建的 User，並補上 `name`、`gender`、`birth_date`、`phone`、`address`、`region` 等欄位
5. 依組員提供的資料表設計（共 11 張表），分別寫入對應的 app：

   | App | 新增的 Model | 說明 |
   |---|---|---|
   | `users` | `User`, `FamilyContact` | 使用者、家屬聯絡人 |
   | `diary` | `Diary`, `DiaryAnalysis` | 聲影日記、日記 AI 分析（可重複分析） |
   | `games` | `GameCategory`, `Game`, `GameRecord` | 遊戲類別、遊戲、遊戲紀錄 |
   | `assessments` | `Ad8Record` | AD-8 認知評估量表 |
   | `dashboard` | `HealthDashboardRecord` | 健康儀表板（各項認知分數） |
   | `activities` | `HealthInformation`, `ActivityRecord` | 資訊加油站活動、活動報名紀錄 |

6. 產生對應的 migration 檔案（`各app/migrations/0001_initial.py` 等），這些檔案記錄了「怎麼把 models 轉換成資料表」，**必須一起同步**，不然無法在你的電腦上建出一樣的資料表
7. 新增 `python-decouple` 套件，把資料庫連線資訊改成從 `.env` 讀取，`settings.py` 裡不再寫死任何密碼，並新增 `.env.example` 作為格式範例

---

## 重要觀念：GitHub 上看不到資料庫本身

這點很重要，先說明清楚，避免大家誤會：

- GitHub 上同步的是 **`models.py`**（資料表設計圖）和 **migration 檔案**（建表的操作紀錄），都只是純文字的 Python 程式碼
- **PostgreSQL 資料庫本身是裝在每個人自己的電腦裡**，`git pull` 不會把資料庫或裡面的資料一起抓下來
- 每個人 `pull` 下來後，**都需要在自己的電腦上重新安裝 PostgreSQL、建立資料庫，並執行 `migrate`**，才能在自己的電腦上生出一模一樣結構的資料表
- 大家的資料表**結構會長得一樣**（因為用同一份 migration），但**裡面存的實際資料是各自獨立的**，不會互通，除非之後把資料庫架到雲端伺服器上共用

---

## 資料表結構總覽

### users app

**User**（繼承 Django 內建 AbstractUser，新增以下欄位）

| 欄位 | 型態 | 說明 |
|---|---|---|
| name | 文字 | 姓名 |
| gender | 選項（男/女/其他） | 性別 |
| birth_date | 日期 | 生日 |
| phone | 文字 | 電話 |
| address | 文字 | 地址 |
| region | 選項（北/中/南/東） | 地區（⚠️ 分類方式待與組員確認） |
| registered_at | 時間 | 註冊時間（自動填入） |

**FamilyContact**（家屬聯絡人）

| 欄位 | 型態 | 說明 |
|---|---|---|
| user | 關聯 User | 屬於哪位使用者 |
| family_name | 文字 | 家屬姓名 |
| relationship | 選項（配偶/子女/手足/其他） | 關係 |
| phone / email | 文字 | 聯絡方式 |

### diary app

**Diary**（聲影日記）：`user`、`image_path`（Firebase 圖片路徑）、`audio_path`（Firebase 語音路徑）、`transcription`（語音轉文字）、`diary_text`、`created_at`

**DiaryAnalysis**（日記 AI 分析，一篇日記可對應多筆分析紀錄）：`diary`、`language_fluency`、`logic_completeness`、`emotion_description_completeness`、`emotion_analysis_result`、`ai_feedback`、`analysis_time`

### games app

**GameCategory**：`category_name`、`category_description`

**Game**：`game_category`、`game_name`、`game_description`、`default_difficulty`（簡單/中等/困難）、`is_enabled`

**GameRecord**：`user`、`game`、`score`、`accuracy`、`reaction_time`、`difficulty`、`played_at`、`played_date`

### assessments app

**Ad8Record**：`user`、`total_score`、`result_description`、`completed_at`

### dashboard app

**HealthDashboardRecord**：`user`、六項認知分數（注意力/執行功能/語言/工作記憶/數學/視覺空間）、`brain_age`、`trend_alert_level`（低/中/高）、`report_type`（週報/月報/手動）、`generated_at`

### activities app

**HealthInformation**（活動資訊）：`activity_name`、`activity_type`（運動/講座/社交活動/健康檢查）、`activity_location`、`activity_region`、`start_time`、`end_time`、`fee`、`activity_description`、`source_url`、`created_at`

**ActivityRecord**（活動報名紀錄）：`user`、`activity`、`status`（已報名/已完成/已取消）、`recorded_at`、`is_enabled`

---

## 你需要做的事（在自己電腦上設定 PostgreSQL）

### 1. Pull 最新的程式碼

```bash
git pull
```

### 2. 安裝 PostgreSQL

前往 [postgresql.org/download](https://www.postgresql.org/download/) 下載安裝（安裝過程會要求設定超級使用者 `postgres` 的密碼，記得記住）。

Stack Builder 跳出的附加工具選單可以直接取消，不需要安裝。

### 3. 開啟 SQL Shell (psql)，建立自己的帳號和資料庫

從 Windows 開始選單打開「SQL Shell (psql)」，一路 Enter 到輸入 postgres 密碼那步，登入成功後執行：

```sql
CREATE USER 你的帳號名稱 WITH PASSWORD '你的密碼';
CREATE DATABASE 你的資料庫名稱 OWNER 你的帳號名稱;
GRANT ALL PRIVILEGES ON DATABASE 你的資料庫名稱 TO 你的帳號名稱;
```

> 帳號、資料庫名稱、密碼可以自己取，跟其他人不用一樣，只要記得填進下一步的設定檔就好。
> 命名注意：只能用英文小寫、數字、底線，不能有連字號 `-`。

### 4. 更新虛擬環境與套件

```bash
python -m venv venv          # 如果還沒建立過虛擬環境
venv\Scripts\activate        # Windows 啟動虛擬環境
pip install -r requirements.txt
```

### 5. 建立自己的 `.env` 檔案

專案已經改成用 `.env` 管理資料庫密碼（不會寫死在程式碼裡，也不會上傳到 GitHub）。

在專案根目錄（跟 `manage.py` 同一層）複製一份 `.env.example`，重新命名為 `.env`，把裡面的值換成你自己剛剛建立的帳密：

```
DB_NAME=你的資料庫名稱
DB_USER=你的帳號名稱
DB_PASSWORD=你的密碼
DB_HOST=localhost
DB_PORT=5432
```

> `.env` 已經被 `.gitignore` 排除，**不會**被 git 追蹤，也**不會**被 push 上去，每個人的 `.env` 內容都可以不一樣，安心填自己的帳密就好。
> 千萬不要把 `.env.example` 的檔名直接刪掉 `.example`，改完記得存檔並確認檔名正確是 `.env`。

### 6. 建立資料表

```bash
py manage.py migrate
```

順利跑完會看到一連串 `Applying ... OK`，代表 11 張資料表已經成功建到你自己電腦的 PostgreSQL 裡。

### 7.（選擇性）建立管理員帳號，用後台檢視資料

```bash
py manage.py createsuperuser
py manage.py runserver
```

啟動後瀏覽器打開 `http://127.0.0.1:8000/admin/` 登入。

> 目前後台還沒有註冊 model，所以登入後暫時只會看到「群組」，之後補上 `admin.py` 的註冊後，就能在後台直接看到各張資料表的資料。

---

## 驗證是否成功

打開 **pgAdmin 4**，連進你自己建立的資料庫 → Schemas → public → Tables，應該會看到類似：

```
users_user
users_familycontact
diary_diary
diary_diaryanalysis
games_gamecategory
games_game
games_gamerecord
assessments_ad8record
dashboard_healthdashboardrecord
activities_healthinformation
activities_activityrecord
```

看到這些表就代表設定成功。

---

## migration 有改動時，怎麼乾淨地重建

有時候 migration 檔案本身會被重新產生（例如把某個 app 的 migration 全部刪掉重建）。這種情況下 `git pull` 之後直接 `migrate` **不會有用**，需要多做一步。

### 為什麼「刪掉專案資料夾重新 clone」沒有用

這是最容易誤會的地方：

- PostgreSQL 資料庫**不在專案資料夾裡**，它裝在系統層（跟著 PostgreSQL 本身安裝的位置）
- 所以刪掉專案資料夾再重新 clone，拿到的是乾淨的**程式碼**，但**資料庫完全沒動**
- 資料庫裡有一張 Django 自己維護的表叫 `django_migrations`，記錄「哪些 migration 已經套用過」
- 舊的 migration 紀錄還留在那裡 → 再跑 `migrate` 時 Django 會判斷「這個已經做過了」而**跳過建表**
- 結果就是 **migration 顯示已完成，但資料表根本不存在** 的不一致狀態

順便一個實務上的麻煩：`.env` 沒有被 git 追蹤，刪掉專案資料夾就一起沒了，重新 clone 後要照 [步驟 5](#5-建立自己的-env-檔案) 再建一次。

**結論：要重來的是資料庫，不是專案資料夾。**

### 做法：重建資料庫（環境建置階段推薦）

還在建環境、資料庫裡沒有要保留的資料時，這是最乾淨也最不容易出錯的做法：

```bash
git pull
```

打開 SQL Shell (psql)，用 `postgres` 超級使用者登入後執行：

```sql
DROP DATABASE 你的資料庫名稱;
CREATE DATABASE 你的資料庫名稱 OWNER 你的帳號名稱;
GRANT ALL PRIVILEGES ON DATABASE 你的資料庫名稱 TO 你的帳號名稱;
```

> 資料庫名稱就是你 `.env` 裡 `DB_NAME` 填的那個，每個人可能不一樣。
> `DROP DATABASE` 會失敗的話，通常是還有連線佔用著 —— 先關掉 pgAdmin、`runserver`、以及其他開著的 psql 視窗再試。

回到專案資料夾：

```bash
venv\Scripts\activate
py manage.py migrate
py manage.py createsuperuser
```

這樣 `django_migrations` 會跟著新資料庫從零開始，不會有任何殘留紀錄，也不用擔心漏砍哪張表。`.env` 不用改、專案資料夾不用刪。

### 如果資料庫裡有想保留的資料

那就不要整個 DROP，只重建有改動的那個 app（以下用 `social` 當例子）。在 psql 裡：

```sql
DROP TABLE IF EXISTS social_like, social_comment, social_notification, social_post CASCADE;
DELETE FROM django_migrations WHERE app = 'social';
```

```bash
py manage.py migrate social
```

> ⚠️ `CASCADE` 會連帶刪掉其他表指向這些表的關聯資料。真的有重要資料的話，先備份再動手。

### 驗證重建成功

```bash
py manage.py showmigrations social       # 應該只看到 [X] 0001_initial
py manage.py makemigrations --check --dry-run   # 要顯示「No changes detected」
py manage.py check                       # 要顯示 no issues
```

三個都通過，代表 models、migration 檔案、資料庫三邊的狀態一致了。

---

## 已知的一次 migration 重建：social app

2026/08/28 把 `social` 的 migration 重新產生過一次：

- 原本是 `0001_initial`（建立 Post、Comment、Like、Notification 四張表）+ `0002_delete_post`（又把 Post 刪掉）
- 但 `social/models.py` 裡 Post 一直都還定義著，所以 `0002` 跟 models 是對不上的
- 現在整理成**只有一個 `0001_initial`**，四張表一次建好，不再有 `0002`

**只要你之前 pull 過 main 並跑過 `migrate`，你的資料庫裡就有舊的 social `0001` + `0002` 紀錄**，需要照上面「重建資料庫」的步驟處理一次，否則 social 的四張表不會出現。

用這個指令可以確認自己是哪種狀況：

```bash
py manage.py showmigrations social
```

- 看到 `[X] 0001_initial` + `[X] 0002_delete_post` → 要重建
- 只看到 `[X] 0001_initial` → 已經是新的，不用動
- 什麼都沒套用（全是 `[ ]`）→ 直接 `py manage.py migrate` 就好

---

如果照著步驟做還是卡住，直接把錯誤訊息截圖丟到群組，一起排查～
