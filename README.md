# 憶智防線（LightMemory）


## 目錄

- [專案介紹](#專案介紹)
- [技術清單](#技術清單)
- [專案架構](#專案架構)
- [模組說明](#模組說明)
- [環境需求](#環境需求)
- [快速開始](#快速開始)
- [目前開發進度](#目前開發進度)
- [後續開發規劃](#後續開發規劃)

---

## 專案介紹

憶智防線是一套以 AI 為核心的認知健康管理平台。

本系統整合聲影日記、認知遊戲、健康儀表板、資訊加油站、社群互動及 AI 分析等功能，希望協助長者建立日常記錄習慣，並提供家屬長期追蹤認知健康狀態的工具。

---

## 技術清單

| 類別 | 技術 |
|------|------|
| 後端框架 | Django |
| API | Django REST Framework |
| 資料庫 | SQLite（開發階段） |
| CORS | django-cors-headers |
| 語言 | Python |
| 版本控制 | Git / GitHub |

> 後續預計加入 Flutter、PostgreSQL、Firebase Storage、OpenAI API、Whisper。

---

## 專案架構

```text
LightMemory/
│
├── manage.py
├── requirements.txt
├── README.md
├── .gitignore
├── db.sqlite3
│
├── config/
├── users/
├── diary/
├── games/
├── dashboard/
├── activities/
├── social/
├── assessments/
└── ai_service/
```

---

## 模組說明

| 模組 | 說明 |
|------|------|
| config | Django 專案設定（settings、urls 等） |
| users | 使用者管理（長者、家屬、登入、註冊） |
| diary | 聲影日記、照片、語音與 AI 分析 |
| games | 認知遊戲與遊戲紀錄 |
| dashboard | 健康儀表板與認知趨勢 |
| activities | 資訊加油站與活動推薦 |
| social | 社群分享、留言與互動 |
| assessments | AD-8 及其他認知評估 |
| ai_service | OpenAI、Whisper、AI 分析服務 |

---

## 環境需求

開始前請確認已安裝：

- Python 3.x
- Git

---

## 快速開始

### 1. Clone Repository

```bash
git clone https://github.com/shiiyyh/LightMemory.git
```

### 2. 進入專案

```bash
cd LightMemory
```

### 3. 建立虛擬環境

```bash
python -m venv venv
```

### 4. 啟動虛擬環境

Windows：

```powershell
venv\Scripts\activate
```

### 5. 安裝套件

```bash
pip install -r requirements.txt
```

### 6. 建立資料庫

```bash
python manage.py migrate
```

### 7. 啟動 Django

```bash
python manage.py runserver
```

---

## 目前開發進度

### 已完成

- [x] 建立 GitHub Repository
- [x] 建立 Django Project
- [x] 建立 Python Virtual Environment
- [x] 安裝 Django
- [x] 安裝 Django REST Framework
- [x] 安裝 django-cors-headers
- [x] 建立各功能 App
- [x] 設定 Django 基本環境
- [x] 建立 requirements.txt
- [x] 建立 .gitignore

---

## 後續開發規劃

- 建立 Database Models
- 設計 RESTful API
- 使用者登入與 JWT 驗證
- 聲影日記 API
- AI 分析服務
- 認知遊戲 API
- 健康儀表板 API
- Flutter 前後端串接
- PostgreSQL
- Firebase Storage