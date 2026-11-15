"""遊戲名稱一致性測試。

遊戲名稱出現在三個地方，各自寫死：
- games/catalog.py：首頁遊戲卡片（GET /api/home/games/）
- home/daily_tasks.py：首頁今日任務的標題
- rewards/catalog.py：成就的說明文字

使用者在 App 裡看到的名稱必須處處一致（例如首頁卡片叫「料理準備」，
任務和成就也都要叫「料理準備」）。任何一處改了名稱而忘了其他處，這裡會失敗。

執行：
    python manage.py test home.tests.test_game_names --settings=config.settings_test
"""

from django.test import SimpleTestCase

from games.catalog import GAMES
from home.daily_tasks import GAME_TASK_NAMES
from rewards.catalog import ACHIEVEMENTS, GAME_NAMES

# App 內顯示的正式名稱（前端遊戲內的標題、教學、結算文案也是這些）
OFFICIAL_NAMES = {
    "market_route": "來去菜市場",
    "market_shopping": "市場買菜",
    "market_sort": "整理菜籃",
    "memory_recall": "料理準備",
    "fridge_check": "冰箱清點",
}


class GameNameConsistencyTests(SimpleTestCase):
    def test_the_catalog_uses_the_official_names(self):
        for game in GAMES:
            with self.subTest(game=game["id"]):
                self.assertEqual(game["name"], OFFICIAL_NAMES[game["id"]])
                self.assertEqual(game["title"], OFFICIAL_NAMES[game["id"]])

    def test_daily_tasks_use_the_official_names(self):
        self.assertEqual(GAME_TASK_NAMES, OFFICIAL_NAMES)

    def test_rewards_use_the_official_names(self):
        self.assertEqual(GAME_NAMES, OFFICIAL_NAMES)

    def test_every_game_is_covered(self):
        self.assertEqual({g["id"] for g in GAMES}, set(OFFICIAL_NAMES))

    def test_the_old_name_is_gone_from_user_facing_text(self):
        texts = [str(a) for a in ACHIEVEMENTS]
        texts += [g["name"] + g["title"] for g in GAMES]
        texts += list(GAME_TASK_NAMES.values())
        for text in texts:
            self.assertNotIn("記憶配對", text)

    def test_the_memory_recall_achievements_mention_the_new_name(self):
        text = " ".join(str(a) for a in ACHIEVEMENTS if "memory_recall" in str(a))
        self.assertIn("料理準備", text)
