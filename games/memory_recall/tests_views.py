"""
System test：煮菜過程（memory_recall）API 端到端流程。

用 APITestCase 打真實 URL，走完整場流程（start → round → round/answer →
finish → result），驗證規格書「三、前測設計」「四、正式賽計時與升階規則」
「七、API 規格」的實際行為，不只是欄位型別。

執行：
    python manage.py test games.memory_recall
"""

import shutil
from pathlib import Path

from django.test import SimpleTestCase
from rest_framework.test import APITestCase

from games import session_service
from users.models import User

from .views import GAME_TYPE, _pick_distractor, _pick_new_item

CONFIG_URL = "/api/games/memory-recall/config/"
START_URL = "/api/games/memory-recall/start/"
ROUND_URL = "/api/games/memory-recall/round/"
ROUND_ANSWER_URL = "/api/games/memory-recall/round/answer/"
FINISH_URL = "/api/games/memory-recall/finish/"

INTERMEDIATE_ITEMS = {"辣椒粉", "鮮奶油", "咖哩塊"}
ADVANCED_ITEMS = {"馬鈴薯泥", "馬鈴薯塊", "紅蘿蔔片", "紅蘿蔔塊", "洋蔥圈", "洋蔥絲"}
ADVANCED_GROUPS = [
    {"馬鈴薯泥", "馬鈴薯塊"},
    {"紅蘿蔔片", "紅蘿蔔塊"},
    {"洋蔥圈", "洋蔥絲"},
]


def result_url(session_id):
    return f"/api/games/memory-recall/result/{session_id}/"


class MemoryRecallTestCase(APITestCase):
    """清空 memory_recall 的 session 檔案，讓每個測試互不干擾。

    這是目前 session_service 用 JSON 檔案儲存（見 session_service.py 開頭
    說明）的已知限制：list_sessions() 會掃描磁碟上全部檔案，測試之間若不
    清空會互相污染（尤其是 _has_finished_before 這種依賴歷史紀錄的邏輯）。
    """

    def setUp(self):
        session_dir = Path(session_service.SESSION_ROOT_DIR) / "memory_recall"
        shutil.rmtree(session_dir, ignore_errors=True)
        # views.py 的 _current_user 在未登入時 fallback 抓第一位使用者
        # （跟 market_shopping 同一套開發階段慣例），測試資料庫是空的，
        # 所以需要先建一個使用者才能讓 start/ 正常運作。
        User.objects.create_user(username="tester", password="testpass123")

    def tearDown(self):
        session_dir = Path(session_service.SESSION_ROOT_DIR) / "memory_recall"
        shutil.rmtree(session_dir, ignore_errors=True)

    def _start(self):
        return self.client.post(START_URL).data["data"]

    def _get_round(self, session_id):
        return self.client.get(ROUND_URL, {"session_id": session_id}).data["data"]

    def _answer(self, session_id, round_number, selected_item, response_time_ms=1000):
        return self.client.post(
            ROUND_ANSWER_URL,
            {
                "session_id": session_id,
                "round_number": round_number,
                "selected_item": selected_item,
                "response_time_ms": response_time_ms,
            },
            format="json",
        )

    def _current_answer(self, session_id):
        """round/ 不回傳答案，測試直接讀後端 state 裡的正解。"""
        return session_service.get_session(GAME_TYPE, session_id)["state"][
            "current_item"
        ]

    def _answer_correctly(self, session_id):
        """取得目前題目並選正確答案，回傳 answer 的回應 data。"""
        question = self._get_round(session_id)
        response = self._answer(
            session_id, question["round_number"], self._current_answer(session_id)
        )
        return response.data["data"]

    def _start_official_session(self):
        """跑完一場前測讓下一場變成正式賽，回傳新的 session_id。"""
        pretest_id = self._start()["session_id"]
        for _ in range(4):
            self._answer_correctly(pretest_id)
        self.client.post(FINISH_URL, {"session_id": pretest_id}, format="json")
        return self._start()["session_id"]


class ConfigApiTests(MemoryRecallTestCase):
    """GET /api/games/memory-recall/config/"""

    def test_returns_expected_fields(self):
        response = self.client.get(CONFIG_URL)

        self.assertTrue(response.data["success"])
        data = response.data["data"]
        self.assertEqual(data["pretest_total_rounds"], 4)
        self.assertEqual(data["base_time_limit_seconds"], 60)
        self.assertEqual(data["promote_streak"], 3)
        self.assertEqual(data["promote_bonus_seconds"], 15)

    def test_has_item_pools_and_no_removed_timing_fields(self):
        data = self.client.get(CONFIG_URL).data["data"]

        self.assertEqual(
            set(data["stage_item_pools"]), {"basic", "intermediate", "advanced"}
        )
        self.assertNotIn("memorize_time_ms", data)
        self.assertNotIn("delay_ms", data)


class StartApiTests(MemoryRecallTestCase):
    """POST /api/games/memory-recall/start/"""

    def test_first_time_player_gets_pretest(self):
        data = self._start()

        self.assertTrue(data["is_pretest"])
        self.assertEqual(data["current_stage"], "basic")
        self.assertIsNone(data["expires_at"])

    def test_returns_seed_item_that_is_first_round_answer(self):
        data = self._start()

        question = self._get_round(data["session_id"])

        self.assertIn(data["seed_item"], question["option_items"])
        self.assertEqual(self._current_answer(data["session_id"]), data["seed_item"])

    def test_returning_player_gets_official_round_with_expiry(self):
        # 先完整跑完一場前測
        session_id = self._start()["session_id"]
        for _ in range(4):
            self._answer_correctly(session_id)
        self.client.post(FINISH_URL, {"session_id": session_id}, format="json")

        # 第二場應該判定為正式賽
        data = self._start()

        self.assertFalse(data["is_pretest"])
        self.assertIsNotNone(data["expires_at"])


class RoundApiTests(MemoryRecallTestCase):
    """GET /api/games/memory-recall/round/：2 張選項 + 1 個新物品。"""

    def test_response_does_not_reveal_answer(self):
        session_id = self._start()["session_id"]

        question = self._get_round(session_id)

        self.assertEqual(
            set(question), {"round_number", "stage", "option_items", "new_item"}
        )

    def test_new_item_is_not_one_of_the_options(self):
        session_id = self._start()["session_id"]

        question = self._get_round(session_id)

        self.assertNotIn(question["new_item"], question["option_items"])

    def test_basic_stage_offers_two_distinct_options_including_answer(self):
        session_id = self._start()["session_id"]

        question = self._get_round(session_id)

        self.assertEqual(len(set(question["option_items"])), 2)
        self.assertIn(self._current_answer(session_id), question["option_items"])

    def test_advanced_stage_offers_two_distinct_options_including_answer(self):
        session_id = self._start_official_session()
        for _ in range(6):  # basic -> intermediate -> advanced
            self._answer_correctly(session_id)

        question = self._get_round(session_id)

        self.assertEqual(question["stage"], "advanced")
        self.assertEqual(len(set(question["option_items"])), 2)
        self.assertIn(self._current_answer(session_id), question["option_items"])

    def test_advanced_options_same_group_and_new_item_from_other_group(self):
        # 前端回報：高階每輪新物品一直卡在同一組
        session_id = self._start_official_session()
        for _ in range(6):  # basic -> intermediate -> advanced
            self._answer_correctly(session_id)

        for _ in range(5):
            question = self._get_round(session_id)
            options = set(question["option_items"])
            self.assertIn(options, ADVANCED_GROUPS)
            self.assertNotIn(question["new_item"], options)
            self._answer(
                session_id,
                question["round_number"],
                self._current_answer(session_id),
            )

    def test_new_item_becomes_next_answer_after_correct_answer(self):
        session_id = self._start()["session_id"]
        question = self._get_round(session_id)

        self._answer(
            session_id, question["round_number"], self._current_answer(session_id)
        )

        self.assertEqual(self._current_answer(session_id), question["new_item"])
        self.assertIn(question["new_item"], self._get_round(session_id)["option_items"])

    def test_new_item_becomes_next_answer_after_wrong_answer(self):
        session_id = self._start()["session_id"]
        question = self._get_round(session_id)
        answer = self._current_answer(session_id)
        wrong_item = next(i for i in question["option_items"] if i != answer)

        self._answer(session_id, question["round_number"], wrong_item)

        self.assertEqual(self._current_answer(session_id), question["new_item"])


class PretestFlowTests(MemoryRecallTestCase):
    """規格書「三、前測設計」：固定 4 輪、全程 basic、不升階、不計分。"""

    def test_pretest_never_promotes_even_on_streak(self):
        session_id = self._start()["session_id"]

        results = [self._answer_correctly(session_id) for _ in range(4)]

        for result in results:
            self.assertEqual(result["current_stage"], "basic")
            self.assertEqual(result["bonus_seconds_granted"], 0)
            self.assertIsNone(result["expires_at"])
            self.assertEqual(result["score_earned"], 0)

    def test_pretest_finishes_after_four_rounds(self):
        session_id = self._start()["session_id"]

        for _ in range(3):
            result = self._answer_correctly(session_id)
            self.assertEqual(result["action"], "next_question")

        last_result = self._answer_correctly(session_id)
        self.assertEqual(last_result["action"], "finished")

    def test_pretest_finish_score_is_null(self):
        session_id = self._start()["session_id"]
        for _ in range(4):
            self._answer_correctly(session_id)

        response = self.client.post(
            FINISH_URL, {"session_id": session_id}, format="json"
        )

        data = response.data["data"]
        self.assertEqual(data["total_rounds"], 4)
        self.assertEqual(data["final_stage"], "basic")
        self.assertIsNone(data["total_score"])
        self.assertIsNone(data["score"])

    def test_calling_finish_twice_returns_same_result_without_recalculating(self):
        session_id = self._start()["session_id"]
        for _ in range(4):
            self._answer_correctly(session_id)

        first = self.client.post(
            FINISH_URL, {"session_id": session_id}, format="json"
        ).data["data"]
        second = self.client.post(
            FINISH_URL, {"session_id": session_id}, format="json"
        ).data["data"]

        self.assertEqual(first, second)


class OfficialGameFlowTests(MemoryRecallTestCase):
    """規格書「四、正式賽計時與升階規則」「五、計分邏輯」。"""

    def test_three_correct_in_a_row_promotes_and_grants_bonus_time(self):
        session_id = self._start_official_session()

        first = self._answer_correctly(session_id)
        second = self._answer_correctly(session_id)
        third = self._answer_correctly(session_id)

        self.assertEqual(first["action"], "next_question")
        self.assertEqual(second["action"], "next_question")
        self.assertEqual(third["action"], "promoted")
        self.assertEqual(third["current_stage"], "intermediate")
        self.assertEqual(third["correct_streak"], 0)
        self.assertEqual(third["bonus_seconds_granted"], 15)
        # basic 答對 3 題：10 + 10 + 10
        self.assertEqual(first["score_earned"], 10)
        self.assertIn(third["seed_item"], INTERMEDIATE_ITEMS)
        self.assertEqual(self._current_answer(session_id), third["seed_item"])

    def test_seed_item_is_null_without_promotion(self):
        session_id = self._start_official_session()

        result = self._answer_correctly(session_id)

        self.assertEqual(result["action"], "next_question")
        self.assertIsNone(result["seed_item"])

    def test_round_after_promotion_has_only_new_stage_items(self):
        # 前端回報：升階進 intermediate 第一輪出現 ['洋蔥', '黑糖']
        session_id = self._start_official_session()
        for _ in range(3):
            self._answer_correctly(session_id)

        question = self._get_round(session_id)

        self.assertEqual(question["stage"], "intermediate")
        self.assertTrue(set(question["option_items"]) <= INTERMEDIATE_ITEMS)

    def test_promotion_to_advanced_gives_advanced_seed(self):
        session_id = self._start_official_session()
        results = [self._answer_correctly(session_id) for _ in range(6)]

        question = self._get_round(session_id)

        self.assertEqual(results[-1]["action"], "promoted")
        self.assertIn(results[-1]["seed_item"], ADVANCED_ITEMS)
        self.assertTrue(set(question["option_items"]) <= ADVANCED_ITEMS)

    def test_wrong_answer_scores_zero_and_resets_streak_without_demotion(self):
        session_id = self._start_official_session()
        self._answer_correctly(session_id)

        question = self._get_round(session_id)
        answer = self._current_answer(session_id)
        wrong_item = next(item for item in question["option_items"] if item != answer)
        result = self._answer(session_id, question["round_number"], wrong_item).data[
            "data"
        ]

        self.assertFalse(result["is_correct"])
        self.assertEqual(result["score_earned"], 0)
        self.assertEqual(result["correct_streak"], 0)
        self.assertEqual(result["current_stage"], "basic")

    def test_finish_totals_bonus_seconds_by_promotion_count(self):
        session_id = self._start_official_session()
        for _ in range(3):  # 升到 intermediate
            self._answer_correctly(session_id)

        response = self.client.post(
            FINISH_URL, {"session_id": session_id}, format="json"
        )
        data = response.data["data"]

        self.assertEqual(data["total_bonus_seconds"], 15)
        self.assertEqual(data["final_stage"], "intermediate")
        self.assertIsNotNone(data["total_score"])

    def test_finish_returns_x_score_converted_from_raw_score(self):
        session_id = self._start_official_session()
        for _ in range(3):  # basic 答對 3 題：原始分 30
            self._answer_correctly(session_id)

        data = self.client.post(
            FINISH_URL, {"session_id": session_id}, format="json"
        ).data["data"]

        self.assertEqual(data["total_score"], 30)
        # 30 / 693 * 100 = 4.33
        self.assertEqual(data["score"], 4)


class ErrorHandlingTests(MemoryRecallTestCase):
    """規格書「七、API 規格 → 錯誤代碼一覽」。"""

    def test_round_with_unknown_session_returns_404(self):
        response = self.client.get(ROUND_URL, {"session_id": 999999})

        self.assertEqual(response.status_code, 404)
        self.assertFalse(response.data["success"])
        self.assertEqual(response.data["error"]["code"], "SESSION_NOT_FOUND")

    def test_answer_with_mismatched_round_number_returns_400(self):
        session_id = self._start()["session_id"]
        question = self._get_round(session_id)

        response = self._answer(
            session_id, question["round_number"] + 1, self._current_answer(session_id)
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["error"]["code"], "ROUND_MISMATCH")

    def test_answer_with_invalid_item_returns_400(self):
        session_id = self._start()["session_id"]
        question = self._get_round(session_id)

        response = self._answer(session_id, question["round_number"], "不存在的物品")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["error"]["code"], "INVALID_ITEM")

    def test_round_after_finished_returns_409(self):
        session_id = self._start()["session_id"]
        for _ in range(4):
            self._answer_correctly(session_id)
        self.client.post(FINISH_URL, {"session_id": session_id}, format="json")

        response = self.client.get(ROUND_URL, {"session_id": session_id})

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["error"]["code"], "SESSION_ALREADY_FINISHED")

    def test_result_before_finished_returns_400(self):
        session_id = self._start()["session_id"]

        response = self.client.get(result_url(session_id))

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["error"]["code"], "SESSION_NOT_FINISHED")

    def test_other_user_accessing_session_returns_403(self):
        session_id = self._start()["session_id"]
        other_user = User.objects.create_user(
            username="other_tester", password="testpass123"
        )
        self.client.force_authenticate(user=other_user)

        response = self.client.get(ROUND_URL, {"session_id": session_id})

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.data["error"]["code"], "FORBIDDEN")

    def test_official_round_timeout_ends_the_whole_game(self):
        session_id = self._start_official_session()
        question = self._get_round(session_id)

        # 模擬這一題已經超過單題逾時秒數仍未作答。
        session = session_service.get_session(GAME_TYPE, session_id)
        current_question = session["current_question"]
        current_question["round_expires_at"] = "2020-01-01T00:00:00+00:00"
        session_service.set_current_question(GAME_TYPE, session_id, current_question)

        response = self._answer(
            session_id, question["round_number"], self._current_answer(session_id)
        )

        self.assertEqual(response.status_code, 410)
        self.assertEqual(response.data["error"]["code"], "ROUND_TIME_UP")

        # 整場遊戲應該已經被標記結束，逾時的這一題不計入統計。
        result_response = self.client.get(result_url(session_id))
        self.assertTrue(result_response.data["success"])
        self.assertEqual(
            result_response.data["data"]["session_result"]["total_rounds"], 0
        )

    def test_pretest_round_has_no_timeout(self):
        session_id = self._start()["session_id"]
        self._get_round(session_id)

        session = session_service.get_session(GAME_TYPE, session_id)
        self.assertIsNone(session["current_question"]["round_expires_at"])


class ResultApiTests(MemoryRecallTestCase):
    """GET /api/games/memory-recall/result/<session_id>/"""

    def test_returns_same_data_as_finish(self):
        session_id = self._start()["session_id"]
        for _ in range(4):
            self._answer_correctly(session_id)
        finish_data = self.client.post(
            FINISH_URL, {"session_id": session_id}, format="json"
        ).data["data"]

        response = self.client.get(result_url(session_id))

        self.assertTrue(response.data["success"])
        self.assertEqual(response.data["data"]["session_result"], finish_data)


class PickItemTests(SimpleTestCase):
    """_pick_distractor 與 _pick_new_item 的抽題規則。"""

    def test_basic_distractor_is_other_basic_item(self):
        distractor = _pick_distractor("basic", "馬鈴薯")

        self.assertIn(distractor, {"胡蘿蔔", "洋蔥"})

    def test_advanced_distractor_is_always_same_group_other_form(self):
        self.assertEqual(_pick_distractor("advanced", "紅蘿蔔片"), "紅蘿蔔塊")

    def test_basic_new_item_is_the_item_not_in_options(self):
        self.assertEqual(_pick_new_item("basic", ["馬鈴薯", "洋蔥"]), "胡蘿蔔")

    def test_advanced_new_item_comes_from_other_group(self):
        new_item = _pick_new_item("advanced", ["馬鈴薯泥", "馬鈴薯塊"])

        self.assertIn(new_item, ADVANCED_ITEMS - {"馬鈴薯泥", "馬鈴薯塊"})
