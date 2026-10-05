"""
System test：煮菜過程（memory_recall）API 端到端流程。

用 APITestCase 打真實 URL，走完整場流程（start → round → round/answer →
finish → result），驗證規格書「三、前測設計」「四、正式賽計時與升階規則」
「七、API 規格」的實際行為，不只是欄位型別。

執行：
    python manage.py test games.memory_recall
"""

from django.test import SimpleTestCase
from rest_framework.test import APITestCase

from games import session_service
from users.models import User

from .views import (
    GAME_TYPE,
    PROMOTE_STREAK,
    _item_stage,
    _pick_distractor,
    _pick_new_item,
)

CONFIG_URL = "/api/games/memory-recall/config/"
START_URL = "/api/games/memory-recall/start/"
ROUND_URL = "/api/games/memory-recall/round/"
ROUND_ANSWER_URL = "/api/games/memory-recall/round/answer/"
FINISH_URL = "/api/games/memory-recall/finish/"

BASIC_ITEMS = {"馬鈴薯", "胡蘿蔔", "洋蔥"}
INTERMEDIATE_ITEMS = {"辣椒粉", "鮮奶油", "咖哩塊"}
ADVANCED_ITEMS = {"馬鈴薯泥", "馬鈴薯塊", "紅蘿蔔片", "紅蘿蔔塊", "洋蔥圈", "洋蔥絲"}
ALL_ITEMS = BASIC_ITEMS | INTERMEDIATE_ITEMS | ADVANCED_ITEMS


def result_url(session_id):
    return f"/api/games/memory-recall/result/{session_id}/"


class MemoryRecallTestCase(APITestCase):
    """memory_recall 測試共用的準備動作。

    session 存在資料庫（GameSession），APITestCase 每個測試結束會自動
    rollback，不需要手動清資料，測試之間不會互相污染。
    """

    def setUp(self):
        self.user = User.objects.create_user(username="tester", password="testpass123")
        self.client.force_authenticate(user=self.user)

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

    def _reach_advanced_cards(self):
        """開一場正式賽並一路答對，直到下一輪卡片是高階物品，回傳 session_id。

        basic 連對 PROMOTE_STREAK 題升中階；過渡輪（卡片還是 basic）算進中階連對，
        再答對 PROMOTE_STREAK - 1 題升高階；最後還要過一輪過渡輪（卡片還是中階）。
        """
        session_id = self._start_official_session()
        for _ in range(2 * PROMOTE_STREAK + 1):
            self._answer_correctly(session_id)
        return session_id


class ConfigApiTests(MemoryRecallTestCase):
    """GET /api/games/memory-recall/config/"""

    def test_returns_expected_fields(self):
        response = self.client.get(CONFIG_URL)

        self.assertTrue(response.data["success"])
        data = response.data["data"]
        self.assertEqual(data["pretest_total_rounds"], 4)
        self.assertEqual(data["base_time_limit_seconds"], 60)
        self.assertEqual(data["promote_streak"], 6)
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
        session_id = self._reach_advanced_cards()

        question = self._get_round(session_id)

        self.assertEqual(question["stage"], "advanced")
        self.assertEqual(len(set(question["option_items"])), 2)
        self.assertIn(self._current_answer(session_id), question["option_items"])

    def test_advanced_distractor_any_stage_and_new_item_advanced(self):
        # 高階干擾物不限階段，new_item 仍是高階物品且不能跟卡片重複
        session_id = self._reach_advanced_cards()

        for _ in range(5):
            question = self._get_round(session_id)
            answer = self._current_answer(session_id)
            options = question["option_items"]
            self.assertIn(answer, ADVANCED_ITEMS)
            self.assertIn(answer, options)
            self.assertTrue(set(options) <= ALL_ITEMS)
            self.assertIn(question["new_item"], ADVANCED_ITEMS)
            self.assertNotIn(question["new_item"], options)
            self._answer(session_id, question["round_number"], answer)

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

    def test_streak_of_promote_streak_promotes_and_grants_bonus_time(self):
        session_id = self._start_official_session()

        results = [self._answer_correctly(session_id) for _ in range(PROMOTE_STREAK)]

        for result in results[:-1]:
            self.assertEqual(result["action"], "next_question")
            self.assertEqual(result["current_stage"], "basic")
        last = results[-1]
        self.assertEqual(last["action"], "promoted")
        self.assertEqual(last["current_stage"], "intermediate")
        self.assertEqual(last["correct_streak"], 0)
        self.assertEqual(last["bonus_seconds_granted"], 15)
        self.assertEqual(results[0]["score_earned"], 10)

    def test_five_correct_in_a_row_does_not_promote(self):
        session_id = self._start_official_session()

        results = [self._answer_correctly(session_id) for _ in range(5)]

        self.assertEqual(results[-1]["action"], "next_question")
        self.assertEqual(results[-1]["current_stage"], "basic")
        self.assertEqual(results[-1]["correct_streak"], 5)

    def test_answer_response_has_no_seed_item(self):
        session_id = self._start_official_session()

        results = [self._answer_correctly(session_id) for _ in range(PROMOTE_STREAK)]

        for result in results:
            self.assertNotIn("seed_item", result)

    def test_promotion_keeps_memory_chain(self):
        # 升階不換種子：升階那一輪的 new_item 仍是下一輪的正解
        session_id = self._start_official_session()
        for _ in range(PROMOTE_STREAK - 1):
            self._answer_correctly(session_id)
        question = self._get_round(session_id)
        self._answer(
            session_id, question["round_number"], self._current_answer(session_id)
        )

        self.assertEqual(self._current_answer(session_id), question["new_item"])
        self.assertIn(question["new_item"], BASIC_ITEMS)

    def test_transition_round_keeps_previous_stage_cards(self):
        # 升到 intermediate 後第一輪：卡片還是 basic，new_item 換成 intermediate
        session_id = self._start_official_session()
        for _ in range(PROMOTE_STREAK):
            self._answer_correctly(session_id)

        transition = self._get_round(session_id)

        self.assertEqual(transition["stage"], "basic")
        self.assertTrue(set(transition["option_items"]) <= BASIC_ITEMS)
        self.assertIn(transition["new_item"], INTERMEDIATE_ITEMS)

        self._answer(
            session_id, transition["round_number"], self._current_answer(session_id)
        )
        question = self._get_round(session_id)

        self.assertEqual(question["stage"], "intermediate")
        self.assertTrue(set(question["option_items"]) <= INTERMEDIATE_ITEMS)
        self.assertIn(transition["new_item"], question["option_items"])

    def test_transition_round_scored_by_card_stage(self):
        session_id = self._start_official_session()
        for _ in range(PROMOTE_STREAK):
            self._answer_correctly(session_id)

        result = self._answer_correctly(session_id)

        # 卡片是 basic：10 x 1.0，不是 intermediate 的 13
        self.assertEqual(result["score_earned"], 10)
        self.assertEqual(result["current_stage"], "intermediate")
        self.assertEqual(result["correct_streak"], 1)

    def test_transition_to_advanced_keeps_intermediate_cards(self):
        session_id = self._start_official_session()
        results = [
            self._answer_correctly(session_id) for _ in range(2 * PROMOTE_STREAK)
        ]

        transition = self._get_round(session_id)

        self.assertEqual(results[-1]["action"], "promoted")
        self.assertEqual(results[-1]["current_stage"], "advanced")
        self.assertEqual(transition["stage"], "intermediate")
        self.assertTrue(set(transition["option_items"]) <= INTERMEDIATE_ITEMS)
        self.assertIn(transition["new_item"], ADVANCED_ITEMS)

        self._answer(
            session_id, transition["round_number"], self._current_answer(session_id)
        )
        question = self._get_round(session_id)

        self.assertEqual(question["stage"], "advanced")
        self.assertIn(transition["new_item"], question["option_items"])

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
        for _ in range(PROMOTE_STREAK):  # 升到 intermediate
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
    """_pick_distractor、_pick_new_item、_item_stage 的抽題規則。"""

    def test_basic_distractor_is_other_basic_item(self):
        distractor = _pick_distractor("basic", "馬鈴薯")

        self.assertIn(distractor, {"胡蘿蔔", "洋蔥"})

    def test_intermediate_distractor_stays_in_intermediate(self):
        for _ in range(20):
            distractor = _pick_distractor("intermediate", "辣椒粉")
            self.assertIn(distractor, INTERMEDIATE_ITEMS - {"辣椒粉"})

    def test_advanced_distractor_can_be_any_other_item(self):
        picked = {_pick_distractor("advanced", "紅蘿蔔片") for _ in range(200)}

        self.assertTrue(picked <= ALL_ITEMS - {"紅蘿蔔片"})
        # 抽 200 次，應該會抽到非高階的物品（不限階段）
        self.assertTrue(picked - ADVANCED_ITEMS)

    def test_item_stage(self):
        self.assertEqual(_item_stage("洋蔥"), "basic")
        self.assertEqual(_item_stage("咖哩塊"), "intermediate")
        self.assertEqual(_item_stage("洋蔥絲"), "advanced")

    def test_basic_new_item_is_the_item_not_in_options(self):
        self.assertEqual(_pick_new_item("basic", ["馬鈴薯", "洋蔥"]), "胡蘿蔔")

    def test_advanced_new_item_comes_from_other_group(self):
        new_item = _pick_new_item("advanced", ["馬鈴薯泥", "馬鈴薯塊"])

        self.assertIn(new_item, ADVANCED_ITEMS - {"馬鈴薯泥", "馬鈴薯塊"})
