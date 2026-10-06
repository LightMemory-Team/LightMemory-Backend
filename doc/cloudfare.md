# Cloudflare 使用說明

本專案會用到兩個 Cloudflare 的免費工具,解決的是相反方向的問題:

| 工具 | 解決什麼 | 誰會用到 |
|---|---|---|
| **WARP** | 自己**連出去**慢(clone GitHub 卡住) | 每個人 |
| **Tunnel** | 讓別人**連進來**(前端連後端本機 server) | 後端開 server 時 |

兩者互相獨立,只需要下載加速就裝 WARP,只需要給前端網址就用 Tunnel。

---

# Cloudflare WARP（加速 GitHub 連線）

台灣連 GitHub(尤其是 `git clone` 大型 repo,像 `fvm` 第一次使用會 clone 整個 `flutter/flutter`)有時會變得很慢或卡住不動,常見原因是網路路由問題,不是 Homebrew／fvm 本身壞掉。Cloudflare WARP 是免費的網路加速工具,能改善這個狀況。

---

## 安裝

```bash
brew install --cask cloudflare-warp
```

## 設定與啟用

1. 打開 WARP App(Spotlight 搜尋 `Cloudflare WARP`,或從 `/Applications` 開)
2. 第一次開啟會要求登入 / 建立帳號,用 Apple ID 或 Email 皆可,免費版就夠用
3. 面板裡把開關打開,狀態顯示 **Connected** 即代表啟用中

也可以用指令行控制(裝完 App 後會一併裝 CLI):

```bash
# 查看連線狀態
warp-cli status

# 連線
warp-cli connect

# 中斷連線
warp-cli disconnect
```

## 什麼時候該開 WARP

- `git clone`、`git pull`、`git push` 到 GitHub 速度異常慢或卡住
- `fvm install` 卡在 `Creating local git cache...` 很久沒動靜
- `pip install` / `flutter pub get` 抓套件很慢(這些通常走 PyPI／pub.dev,不一定是 GitHub,但連線不穩定時也可以先開 WARP 排除變因)

開啟後再重新執行卡住的指令即可,不需要重開機或重啟終端機。

## 常見狀況

| 現象 | 處理方式 |
|---|---|
| 開了 WARP 還是很慢 | 面板裡切換一下 WARP 模式(有 `WARP` 和 `DNS only` 兩種),或先 disconnect 再 connect 重新建立連線 |
| WARP 跟公司/學校 VPN 衝突 | 兩個 VPN 類工具不建議同時開,先關掉其中一個再測試 |
| 不確定有沒有生效 | `warp-cli status` 顯示 `Status update: Connected` 才是真的連上 |

---

# Cloudflare Tunnel（讓前端連到本機 server）

以下為 **Windows 環境**的說明。

前端無法直接連 `127.0.0.1:8000`,因為那是 loopback 位址,只有跑著 server 的那台電腦自己連得到。Cloudflare Tunnel 可以把本機的 server 開出一個對外的 https 網址,前端就能從自己的機器連進來,不需要部署到雲端,也不需要 ngrok 帳號。

---

## 安裝 cloudflared

用 winget(Windows 10/11 內建):

```powershell
winget install --id Cloudflare.cloudflared
```

或用 Chocolatey:

```powershell
choco install cloudflared
```

裝完**要開新的 PowerShell 視窗**,舊視窗讀不到剛加進 PATH 的指令。確認安裝成功:

```powershell
cloudflared --version
```

> 若顯示「無法辨識 'cloudflared' 詞彙」,代表 PATH 還沒生效,關掉重開 PowerShell 即可。

---

## 使用步驟

### 1. 先把 Django server 跑起來

```powershell
python manage.py runserver
```

保持這個視窗開著,不要關。

### 2. 另開一個 PowerShell 視窗,開 tunnel

```powershell
cloudflared tunnel --url http://localhost:8000
```

跑起來後畫面中間會出現一個網址,長這樣:

```
+--------------------------------------------------------------------------------------------+
|  Your quick Tunnel has been created! Visit it at (it may take some time to be reachable):   |
|  https://xxxx-xxxx-xxxx-xxxx.trycloudflare.com                                             |
+--------------------------------------------------------------------------------------------+
```

### 3. 把網址給前端

把那串 `https://xxxx.trycloudflare.com` 貼給前端,他們把 base URL 換成這個就能打 API:

```
https://xxxx-xxxx-xxxx-xxxx.trycloudflare.com/api/users/login/
https://xxxx-xxxx-xxxx-xxxx.trycloudflare.com/api/home/ping/
```

可以先自己用瀏覽器打開 `https://xxxx.trycloudflare.com/api/home/ping/` 確認,看到 `{"message": "index api is connected"}` 就代表通了。

### 4. 結束

在 tunnel 那個視窗按 `Ctrl + C` 即可關閉,網址隨即失效。

---

## 重要注意事項

**網址每次重開都會變。** 這是免費版 quick tunnel 的特性,每次執行 `cloudflared tunnel --url` 都會拿到一組全新的隨機網址。所以:

- 前端**不要把網址寫死**在程式裡,建議放在設定檔或環境變數,方便隨時替換
- 每次要跟前端測試前,重新開 tunnel 並把新網址貼給對方
- 你的電腦關機、休眠,或關掉那個 PowerShell 視窗,網址就失效了

**server 要一直開著。** tunnel 只是把外部請求轉發到你本機的 `localhost:8000`,Django server 停掉的話,前端會收到 502。

**`ALLOWED_HOSTS` 已經設定好。** `config/settings.py` 裡已經加入 `.trycloudflare.com`,所以任何 trycloudflare 的隨機網址都能通過 Django 的 host 檢查,不用每次改設定:

```python
ALLOWED_HOSTS = ['localhost', '127.0.0.1', '.trycloudflare.com']
```

若沒有這行,Django 會直接擋下並回 `DisallowedHost` 錯誤。

---

## 常見狀況

| 現象 | 處理方式 |
|---|---|
| 前端打 API 收到 502 | Django server 沒開,或已經停掉。回到跑 `runserver` 的視窗確認還在跑 |
| 回應 `DisallowedHost` | `ALLOWED_HOSTS` 沒有 `.trycloudflare.com`,確認 `config/settings.py` 有這行且已存檔重啟 server |
| 網址打不開 / 一直轉圈 | 剛開的 tunnel 需要幾秒鐘生效,等一下再試;或 `Ctrl + C` 關掉重開拿新網址 |
| `cloudflared` 指令找不到 | PATH 未生效,關掉 PowerShell 重開 |
| 前端說昨天的網址不能用了 | 正常,網址每次重開都會變,重新開 tunnel 給新網址 |
| 擔心跨網域被擋(CORS) | 開發階段 `config/settings.py` 已設 `CORS_ALLOW_ALL_ORIGINS = True`,允許所有來源,正常情況不會遇到 |
