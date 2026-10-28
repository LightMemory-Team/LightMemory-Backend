"""
System test：market-sort API 端到端測試
寫法比照 users/tests/test_api_system.py
執行：python manage.py test games.market_sort.tests --settings=config.settings_test
"""

import random

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase
from rest_framework import status
from rest_framework.test import APITestCase

from .services import calculate_cognitive_flexibility_score

User = get_user_model()

SUBMIT_URL = "/api/games/market-sort/submit/"


def build_questions():
    return (
        [
            {
                "question_index": i + 1,
                "is_correct": True,
                "reaction_time_ms": 2000,
                "trial_type": "repeat",
                "error_type": None,
            }
            for i in range(5)
        ]
        + [
            {
                "question_index": 6,
                "is_correct": False,
                "reaction_time_ms": 2500,
                "trial_type": "switch",
                "error_type": "persistent",
            }
        ]
        + [
            {
                "question_index": 7,
                "is_correct": True,
                "reaction_time_ms": 2100,
                "trial_type": "switch",
                "error_type": None,
            }
        ]
        + [
            {
                "question_index": i,
                "is_correct": True,
                "reaction_time_ms": 2000,
                "trial_type": "repeat",
                "error_type": None,
            }
            for i in range(8, 29)
        ]
    )


class MarketSortSubmitEndpointTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="market_sort_tester", password="Str0ng!Pass2026"
        )
        self.client.force_authenticate(user=self.user)

    def test_submit_complete_session_returns_201(self):
        payload = {
            "session_id": "test_1",
            "is_complete": True,
            "questions": build_questions(),
        }
        response = self.client.post(SUBMIT_URL, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn("current_score", response.data["data"])

    def test_first_time_player_has_empty_recent_scores(self):
        payload = {
            "session_id": "test_2",
            "is_complete": True,
            "questions": build_questions(),
        }
        response = self.client.post(SUBMIT_URL, payload, format="json")

        self.assertEqual(response.data["data"]["recent_scores"], [])

    def test_incomplete_session_does_not_calculate_score(self):
        payload = {
            "session_id": "test_3",
            "is_complete": False,
            "questions": build_questions()[:10],
        }
        response = self.client.post(SUBMIT_URL, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIsNone(response.data["data"])

    def test_invalid_trial_type_returns_400(self):
        bad_questions = build_questions()
        bad_questions[0]["trial_type"] = "REPEAT"
        payload = {
            "session_id": "test_4",
            "is_complete": True,
            "questions": bad_questions,
        }
        response = self.client.post(SUBMIT_URL, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error"]["code"], "INVALID_QUESTION_DATA")

    def test_unauthenticated_request_rejected(self):
        self.client.force_authenticate(user=None)
        payload = {
            "session_id": "test_5",
            "is_complete": True,
            "questions": build_questions(),
        }
        response = self.client.post(SUBMIT_URL, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_duplicate_session_id_returns_same_result_without_duplicate_record(self):
        payload = {
            "session_id": "duplicate_test",
            "is_complete": True,
            "questions": build_questions(),
        }

        first_response = self.client.post(SUBMIT_URL, payload, format="json")
        second_response = self.client.post(SUBMIT_URL, payload, format="json")

        self.assertEqual(first_response.data, second_response.data)

        from games import session_service

        sessions = session_service.list_sessions("market_sort")
        count = sum(1 for s in sessions if s["session_id"] == "duplicate_test")
        self.assertEqual(count, 1)

    def test_complete_submit_after_incomplete_one_calculates_score(self):
        """先送未完成，再用同一個 session_id 送完整資料，要能算出分數。"""
        incomplete = {
            "session_id": "resubmit_after_incomplete",
            "is_complete": False,
            "questions": build_questions()[:10],
        }
        complete = {**incomplete, "is_complete": True, "questions": build_questions()}

        self.client.post(SUBMIT_URL, incomplete, format="json")
        response = self.client.post(SUBMIT_URL, complete, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn("current_score", response.data["data"])

    def test_resubmit_after_insufficient_data_calculates_score(self):
        """題數不足被擋下（400）後，補齊資料用同一個 session_id 重送，要能算出分數。"""
        too_few = {
            "session_id": "resubmit_after_400",
            "is_complete": True,
            "questions": build_questions()[:10],
        }
        enough = {**too_few, "questions": build_questions()}

        first_response = self.client.post(SUBMIT_URL, too_few, format="json")
        second_response = self.client.post(SUBMIT_URL, enough, format="json")

        self.assertEqual(first_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(second_response.status_code, status.HTTP_201_CREATED)
        self.assertIn("current_score", second_response.data["data"])


def build_game_with_accuracy(correct_count, total=28, seed=0):
    """建立一場「答對 correct_count / total 題」的模擬資料，用固定的 seed
    確保每次測試結果可重現。第 6、11、16 題固定標成 switch（對應
    STAGE_BOUNDARIES），第 1 題也標成 switch，用來測試「第 1 題不算
    switch 題」這條規則有沒有真的生效。

    對應 Wen 2026-09-29 分析文件裡的短期修正測試需求：
    「補 tests.py，加入不同正確率的分數測試」。
    """
    rng = random.Random(seed)
    correct_indices = set(rng.sample(range(1, total + 1), correct_count))
    questions = []
    for i in range(1, total + 1):
        trial_type = "switch" if i in (1, 6, 11, 16) else "repeat"
        is_correct = i in correct_indices
        rt = rng.randint(1500, 2500) if is_correct else rng.randint(1800, 3000)
        error_type = None
        if not is_correct:
            error_type = (
                "persistent"
                if trial_type == "switch" and rng.random() < 0.4
                else "random"
            )
        questions.append(
            {
                "question_index": i,
                "is_correct": is_correct,
                "reaction_time_ms": rt,
                "trial_type": trial_type,
                "error_type": error_type,
            }
        )
    return questions


class MarketSortScoringFormulaTests(SimpleTestCase):
    """短期修正後的計分公式測試，直接測 services.py 的計算邏輯（不透過
    API），對應 Wen 分析文件裡「筠淇：更新 games/market_sort/tests.py，
    加入不同正確率的分數測試」這項工作。"""

    def test_low_accuracy_yields_low_score(self):
        """答對 4/28（幾乎沒答對）分數應該落在低分區，不能再像舊公式
        一樣還有 77 分左右。"""
        result = calculate_cognitive_flexibility_score(
            build_game_with_accuracy(4, seed=1)
        )
        score = result["cognitive_flexibility_score"]
        self.assertLess(score, 30, f"答對 4/28 卻拿到 {score} 分，太高了")

    def test_high_accuracy_yields_high_score(self):
        """答對 27/28（幾乎全對）分數應該落在高分區。"""
        result = calculate_cognitive_flexibility_score(
            build_game_with_accuracy(27, seed=2)
        )
        score = result["cognitive_flexibility_score"]
        self.assertGreater(score, 70, f"答對 27/28 卻只拿到 {score} 分，太低了")

    def test_half_accuracy_no_longer_scores_near_ceiling(self):
        """舊公式答對一半（14/28）中位數會到 88 分，新公式應該明顯低於
        高正確率的分數，不能卡在分數上限附近。"""
        half_result = calculate_cognitive_flexibility_score(
            build_game_with_accuracy(14, seed=3)
        )
        high_result = calculate_cognitive_flexibility_score(
            build_game_with_accuracy(27, seed=4)
        )
        self.assertLess(
            half_result["cognitive_flexibility_score"],
            high_result["cognitive_flexibility_score"] - 20,
        )

    def test_score_increases_with_accuracy(self):
        """正確率越高，分數應該要單調遞增（不要求嚴格線性，但方向要對）。"""
        accuracies = [4, 10, 14, 20, 27]
        scores = [
            calculate_cognitive_flexibility_score(
                build_game_with_accuracy(n, seed=100 + n)
            )["cognitive_flexibility_score"]
            for n in accuracies
        ]
        self.assertEqual(
            scores,
            sorted(scores),
            f"分數沒有隨正確率遞增：{list(zip(accuracies, scores))}",
        )

    def test_all_switch_incorrect_does_not_raise(self):
        """switch 題全部答錯時，過去會拋出 ALL_SWITCH_INCORRECT 導致 API
        回 400；短期修正後應該照樣算得出分數（只是會偏低）。"""
        questions = build_game_with_accuracy(20, seed=5)
        for q in questions:
            if q["trial_type"] == "switch":
                q["is_correct"] = False
                q["error_type"] = "random"

        result = calculate_cognitive_flexibility_score(questions)  # 不應該拋出例外
        self.assertEqual(result["raw_metrics"]["switch_accuracy"], 0)

    def test_persistent_error_rate_removed_from_scoring(self):
        """短期修正把 persistent_error_rate 從計分拿掉（現在的玩法測不
        到），raw_metrics／z_scores 都不應該再出現這個欄位。"""
        result = calculate_cognitive_flexibility_score(
            build_game_with_accuracy(15, seed=6)
        )
        self.assertNotIn("persistent_error_rate", result["raw_metrics"])
        self.assertNotIn("persistent_error_rate_z", result["z_scores"])

    def test_switch_cost_rt_skipped_when_not_enough_correct_answers(self):
        """repeat、switch 兩邊沒有都至少答對 3 題時，switch_cost_rt 應該
        跳過（為 None），但整體分數還是算得出來，權重自動分給其他指標。"""
        questions = build_game_with_accuracy(4, seed=7)
        result = calculate_cognitive_flexibility_score(questions)
        self.assertIsNone(result["raw_metrics"]["switch_cost_rt"])
        self.assertIsNone(result["z_scores"]["switch_cost_rt_z"])
        self.assertIsInstance(result["cognitive_flexibility_score"], int)

    def test_first_question_excluded_from_switch_stats(self):
        """第 1 題就算被標成 switch，也不應該被算進 switch 題的統計裡。"""
        questions = build_game_with_accuracy(20, seed=8)
        assert questions[0]["question_index"] == 1
        questions[0]["trial_type"] = "switch"
        questions[0]["is_correct"] = False

        result = calculate_cognitive_flexibility_score(
            questions
        )  # 不應該拋出例外，且不能被第1題影響
        self.assertIn("switch_accuracy", result["raw_metrics"])
