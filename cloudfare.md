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
