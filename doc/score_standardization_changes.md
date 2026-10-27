# 計分標準化改版 — 變更說明（10/27）

> 本文件說明分支 `feat/score_standardization` 做了什麼、為什麼、前後端各要配合什麼，並整理「儀表板」與「週報表」目前完成的全部內容。
>
> 演算法細節見 [`game_scoring_algorithms.md`](game_scoring_algorithms.md)；週報 API 規格見 [`weekly_report.md`](weekly_report.md)。
>
> 用語原則：本 App 定位為「輔助維持認知活躍度」，所有分數只跟**自己**比，不作任何診斷用途。

---

## 一、為什麼要改

| 問題 | 原因 | 結果 |
|---|---|---|
| 六個維度的分數波動不一致 | 各維度合成的指標數從 1 到 5 個不等，指標越多平均後波動越小 | 整理菜籃、日記幾乎拿不到 90 分，冰箱檢查約 5.7%；雷達圖形狀反映的是「指標數量」，不是能力 |
| 冷啟動基準不穩 | 3 場的標準差很不穩；借全體資料時用錯變異來源（個人**之間**，不是個人**內**）；第一場有練習效應 | 新使用者前幾場的分數失真 |
| 解鎖太嚴 | 6 個維度全部滿 3 筆才整包解鎖 | 只玩一款遊戲的人，雷達圖完全看不到 |

規格依據：《憶智防線 認知維度計分規格：標準化與冷啟動》（10/27）。

## 二、解法（三條規則）

1. **先 z 再加權，一律等權重**：每個指標先各自換成 z，再平均（Dawes 1979，等權重通常不輸調出來的權重）
2. **二階段標準化**：合成分數再除以「合成分數自己的標準差」，不管 1 個還是 5 個指標，最後的 z 標準差都接近 1
3. **收縮估計＋熟悉場**：
   - 基準 = 「自己」與「全體」依場次數加權，自己的場次越多越偏向自己（收縮強度 k = 3，`PRIOR_STRENGTH`）
   - 全體的變異用「個人內」變異（同一人多場之間的變化）
   - **每款遊戲的第一場是熟悉場**：不算分、不進任何歷史

驗證：測試用 200 場模擬，1 個指標與 5 個指標的最終 z 標準差差距 < 0.15（`games/tests_zscore.py`）。

---

## 三、後端變更

### 1. 共用計算（`games/zscore.py`）

新增：`shrunk_baseline`（收縮基準）、`pooled_population_baseline`（全體個人內基準）、`effective_weights`、`prior_composite_variance`、`restandardize`（二階段標準化）、`composite_z_details`、`calculate_dimension_z_score`。
移除：`choose_baseline`、`metric_z_scores`（被取代）。

### 2. 歷史資料查詢（`games/session_service.py`）

- 個人歷史：排除熟悉場
- 全體歷史：依使用者分組（才能算個人內變異），並排除：本人、熟悉場、`is_staff` 使用者、demo 種子資料（`client_session_id` 以 `seed-` 開頭、日記 `audio_path` 以 `seed/` 開頭）
- 新增 `is_first_session(game_type, user)`：判斷這是不是這位使用者在這款遊戲的第一場

### 3. 五款遊戲

| 遊戲 | 變更 |
|---|---|
| 菜市場找路 `market_route` | 第一場標記熟悉場；指標等權重；`z_score` 熟悉場為 `null` |
| 煮菜過程 `memory_recall` | 原本只寫在 state 的 `is_pretest` 改為同時寫入 `GameSession.is_pretest` 欄位；前測就是熟悉場 |
| 整理菜籃 `market_sort` | 同上；指標等權重；熟悉場不送歷史 |
| 冰箱檢查 `fridge_check` | 指標精簡為「正確率」「速度分」各 50%（原速度分 30%）；熟悉場 `null` |
| 市場買菜 `market_shopping` | 同上；沒有反應時間時速度分為 `None`，能力分只看正確率 |

**不改資料表**：熟悉場沿用既有的 `GameSession.is_pretest` 欄位（原本從沒被寫成 True）。

### 4. 聲影日記語言 z（`dashboard/diary_zscore.py`）

5 個小分數改為等權重（不再綁 `diary/analysis.py` 的 `communication_score` 權重），套用收縮基準與二階段標準化；日記沒有熟悉場。

### 5. 舊資料重算指令

```bash
python manage.py recompute_scores --dry-run   # 先看會改什麼（transaction 內算完 rollback）
python manage.py recompute_scores             # 正式重算
```

- 回填熟悉場：每人每款遊戲「最早結束」的場次標記為熟悉場
- 依新算法重算每場的 `z_score` 與 1～100 分數，寫回 `result`（JSON 欄位）
- demo 種子場次不重算；可重複執行，結果只跟資料有關

---

## 四、儀表板 `GET /api/dashboard/`（完成內容）

雷達圖：各維度近 7 天 z 平均；**各維度分開解鎖**。

```json
{
  "success": true,
  "data": {
    "period_days": 7,
    "required_sessions": 3,
    "dimensions": [
      { "dimension": "attention", "label": "注意力", "source": "market_route",
        "z_score": 0.375, "score": 59, "session_count": 4,
        "valid_count": 6, "unlocked": true, "sessions_to_unlock": 0, "personal_weight": 0.667 }
    ],
    "encouragement": null
  },
  "error": null
}
```

（`dimensions` 固定 6 筆：注意力、工作記憶、執行功能、視覺空間、數學、語言）

| 欄位 | 說明 |
|---|---|
| `z_score` | 近 7 天 z 平均（±2 內）；未解鎖或近 7 天沒資料為 `null` |
| `score` | `round(50 + 25z)` 限 1～100，雷達圖半徑用這個 |
| `session_count` | 近 7 天有 z 的場次（篇）數 |
| `valid_count` | 累計有 z 的場次（篇）數 |
| `unlocked` | `valid_count ≥ required_sessions`（3） |
| `sessions_to_unlock` | 還差幾次，已解鎖為 0 |
| `personal_weight` | n ÷ (n + 3)；小於 0.5 表示還在參考期，基準偏向其他使用者 |

**與舊版的差異（前端會壞的地方）**

- 不再回 `INSUFFICIENT_DATA`，也沒有 `progress`；永遠 `success: true` 加 6 個維度
- 新增 `score`、`valid_count`、`unlocked`、`sessions_to_unlock`、`personal_weight`、頂層 `required_sessions`

**機器人卡片 `encouragement`**：6 個維度都解鎖才有值，否則 `null`。

```json
"encouragement": { "trend": "up", "overall_score": 71, "previous_overall_score": 66 }
```

`trend`：`up`／`steady`／`practice`／`null`（只有一週資料）；前端自行對照文字。總體分數 = 每週整體分數以 0.8^週數 加權平均（越近越重）。

**前端顯示建議**

| 狀態 | 條件 | 雷達圖該軸 | 文字 |
|---|---|---|---|
| 未解鎖 | `unlocked: false` | 灰色，不畫點 | 「再玩 N 次就能看到」 |
| 參考期 | 已解鎖且 `personal_weight < 0.5` | 正常顯示 | 「前幾次會參考其他使用者的表現」 |
| 正式 | 已解鎖且 `personal_weight ≥ 0.5` | 正常顯示 | 無 |
| 近 7 天沒玩 | 已解鎖但 `score` 為 `null` | 灰色 | 「這週還沒玩」 |

---

## 五、週報表 `GET /api/dashboard/weekly-report/`（完成內容）

看「上一個完整的週」（週一～週日），比較對象是再前一週。完整欄位見 [`weekly_report.md`](weekly_report.md)。

| 區塊 | 內容 |
|---|---|
| `highlights`、`daily_activity` | 玩幾天、玩幾場、最長連續天數；週一到週日固定 7 筆打卡 |
| `abilities` | 整體表現＋6 個能力的 `this_week`／`last_week`／`best`／`trend` |
| `play_time` | 五款遊戲各自與總遊玩秒數 |
| `diary` | 本週完成的日記與對話時長（近似值） |
| `next_week_goal` | 挑第一個本週沒碰過的能力給小目標 |
| `summary` | AI 一句話（只給正向事實；失敗、過長、含禁用詞則改固定句型） |
| `disclaimer` | 「這不是醫療診斷，僅供自我了解」 |

**本次新增：能力分數只列已解鎖的維度**

- `abilities.dimensions` 仍固定 6 筆（版面不變），每筆多一個 `unlocked`
- `unlocked` 以「到**報告週結束為止**」的有效 z 筆數判斷，所以舊的報告不會因為之後多玩而改變
- `unlocked: false` → `this_week`、`last_week`、`best`、`trend` 都是 `null`；`played` 照常標示這週有沒有碰過（可能出現「玩了但還沒解鎖」）
- `abilities.overall` 只用已解鎖且有分數的能力平均；全部沒解鎖時為 `null`
- 活動、日記、遊玩時間不設門檻，沒玩也有內容

```json
{ "dimension": "attention", "label": "注意力", "played": true, "unlocked": false,
  "this_week": null, "last_week": null, "best": null, "trend": null }
```

前端建議：未解鎖顯示「還在認識你，再玩幾次就能看到」，不放 0 分、不用紅色。

---

## 六、前端要配合的事

### 1. 熟悉場（五款遊戲）

第一場所有分數欄位為 `null`，結算畫面要顯示「熟悉場，這場不計分」，不能顯示 0 或空白。

| 遊戲 | 在哪拿 `is_pretest` | 熟悉場為 `null` 的欄位 |
|---|---|---|
| 菜市場找路 | `POST .../start` 回應（新增） | `z_score`（`total_score` 照常有值） |
| 煮菜過程 | `start` 回應（原本就有） | `total_score`、`z_score` |
| 整理菜籃 | `POST submit/` 回應（新增） | `current_score`、`encouragement_tier`；`highest_score`、`recent_scores` 不含 `null` 場次 |
| 冰箱檢查 | 建立場次回應（新增） | 最後一題回應的 `z_score`、`standard_score` |
| 市場買菜 | 建立場次回應（新增） | 最後一題回應的 `z_score`、`standard_score` |

非熟悉場但資料還不夠算的場次，分數也可能是 `null`：一律「有值才顯示」，不要只靠 `is_pretest`。

### 2. 儀表板與週報表

見第四、五節：改成讀 `unlocked`／`sessions_to_unlock`、處理 `score`／`encouragement`／週報分數為 `null`。

### 3. 分數數值會變

欄位名稱不變、範圍仍是 1～100，但同一個人的分數會跟以前不同；前端寫死的測試資料與截圖需重新取得。

### 4. 驗收順序

1. 全新帳號玩任一款第一場：結算畫面不壞，有熟悉場提示
2. 同一款再玩 2 場：`valid_count` 到 3，該軸變彩色
3. 只玩一款的帳號：其他 5 軸灰色、`encouragement` 為 `null`
4. 6 個維度都滿 3 次：機器人卡片出現
5. 週報：未解鎖的能力顯示解鎖提示，已解鎖的正常顯示

---

## 七、上線步驟

1. 部署程式（沒有 migration）
2. `python manage.py recompute_scores --dry-run`：看每款遊戲會改幾場、數字是否合理
3. 確認後 `python manage.py recompute_scores` 正式重算
4. 用 `GET /api/dashboard/`、`GET /api/dashboard/weekly-report/` 確認 6 個維度都有新欄位、分數在 1～100

> 尚未在真實資料庫執行過 `recompute_scores`。

## 八、測試

```bash
python manage.py test --settings=config.settings_test
```

全專案 568 個測試通過（1 個既有的 expected failure）。預期值多為手算或以獨立腳本算出再對照，不是把程式輸出抄進測試。

主要新增／改寫的測試：

| 檔案 | 驗證內容 |
|---|---|
| `games/tests_zscore.py` | 收縮基準、二階段標準化、等權重；1 vs 5 個指標模擬 SD 一致 |
| `games/tests_session_service.py` | 歷史查詢排除熟悉場、`is_staff`、種子資料；依使用者分組 |
| `games/tests_recompute_scores.py` | 回填熟悉場、重算、`--dry-run`、可重複執行 |
| 各遊戲 `tests_*` | 熟悉場 `null`、`is_pretest` 回應、冷啟動借全體、手算 z 值 |
| `dashboard/tests*.py` | 各維度解鎖、`encouragement` 需 6 維度解鎖、週報 `unlocked` 與 `overall`、日記 z |

## 九、已知問題與備註

| 項目 | 說明 |
|---|---|
| k = 3 是保守設定 | 全體基準目前來自少數測試者；資料累積夠了再用真實資料估計 k |
| 冰箱檢查速度分權重 | 30% → 50%（等權重的結果） |
| 日記解鎖較慢 | 日記要算得出語言 z 才算數；全新系統第一位使用者要寫 6 篇才解鎖，已有其他使用者資料時 3 篇 |
| 重算尚未執行 | 見第七節 |
| 整理菜籃遊玩時間 | 用反應時間加總，比實際短 |
