"""遊戲 Demo 模式（games/demo_mode.py）的測試。

admin_demo 每款遊戲答 3 題就結束、分數固定 80；其他帳號完全照舊。

執行：
    python manage.py test games.tests.test_demo_mode --settings=config.settings_test
"""

from rest_framework.test import APITestCase

from demo_tools.constants import DEMO_USERNAME
from games import demo_mode, session_service
from games.fridge_check import services as fridge_services
from games.fridge_check.constants import TOTAL_QUESTIONS as FRIDGE_TOTAL
from games.management.commands.recompute_scores import recompute_results
from games.market_route.views import TOTAL_QUESTIONS as ROUTE_TOTAL
from games.market_shopping.services import TOTAL_QUESTIONS as SHOPPING_TOTAL
from games.market_sort.views import TOTAL_QUESTIONS as SORT_TOTAL
from games.models import GameSession
from users.models import User

DEMO_COUNT = demo_mode.DEMO_QUESTION_COUNT


def submit_three_market_sort_questions(client, session_id="demo-sort-1"):
    """market_sort 交 3 題（全對、每題 2 秒）。"""
    questions = [
        {
            "question_index": i,
            "is_correct": True,
            "reaction_time_ms": 2000,
            "trial_type": "repeat",
            "error_type": None,
        }
        for i in range(1, 4)
    ]
    return client.post(
        "/api/games/market-sort/submit/",
        {"session_id": session_id, "is_complete": True, "questions": questions},
        format="json",
    )


class DemoModeTestCase(APITestCase):
    """預設用 admin_demo 登入；use_normal_user() 換成一般帳號。"""

    def setUp(self):
        self.user = User.objects.create_user(username=DEMO_USERNAME, password="admin")
        self.client.force_authenticate(user=self.user)

    def use_normal_user(self):
        self.user = User.objects.create_user(username="elder", password="pw")
        self.client.force_authenticate(user=self.user)

    def assert_demo_session_saved(self, game_type):
        session = GameSession.objects.get(user=self.user, game__code=game_type)
        self.assertEqual(session.status, "finished")
        self.assertFalse(session.is_pretest)
        self.assertEqual(session.result["z_score"], demo_mode.DEMO_Z)
        return session


class HelperTests(DemoModeTestCase):
    def test_question_limit_only_changes_for_demo_user(self):
        self.assertEqual(demo_mode.question_limit(self.user, 10), DEMO_COUNT)
        self.assertEqual(demo_mode.question_limit(self.user.id, 10), DEMO_COUNT)

        normal = User.objects.create_user(username="elder", password="pw")
        self.assertEqual(demo_mode.question_limit(normal, 10), 10)
        self.assertEqual(demo_mode.question_limit(normal.id, 10), 10)
        self.assertEqual(demo_mode.question_limit(None, 10), 10)

    def test_demo_user_never_gets_familiarization_session(self):
        self.assertFalse(session_service.is_first_session("fridge_check", self.user))

        normal = User.objects.create_user(username="elder", password="pw")
        self.assertTrue(session_service.is_first_session("fridge_check", normal))


class FridgeCheckDemoTests(DemoModeTestCase):
    URL = "/api/games/fridge-check/sessions/"

    def play(self):
        data = self.client.post(self.URL).data["data"]
        session_id = data["session_id"]
        answers = []
        for _ in range(FRIDGE_TOTAL):
            session = fridge_services.get_session(session_id)
            response = self.client.post(
                f"{self.URL}{session_id}/answers/",
                {
                    "answer": session["current_question"]["correct_answer"],
                    "reaction_time_ms": 1500,
                },
                format="json",
            )
            answers.append(response.data["data"])
            if answers[-1]["is_completed"]:
                break
        return data, answers

    def test_demo_user_finishes_after_three_questions_with_score_80(self):
        created, answers = self.play()

        self.assertEqual(created["total_questions"], DEMO_COUNT)
        self.assertEqual(len(answers), DEMO_COUNT)
        last = answers[-1]
        self.assertTrue(last["is_completed"])
        self.assertEqual(last["total_questions"], DEMO_COUNT)
        self.assertEqual(last["final_score"], demo_mode.DEMO_SCORE)
        self.assertEqual(last["standard_score"], demo_mode.DEMO_SCORE)
        self.assertIn("rewards", last)
        self.assert_demo_session_saved("fridge_check")

    def test_normal_user_still_gets_ten_questions(self):
        self.use_normal_user()

        created, answers = self.play()

        self.assertEqual(created["total_questions"], FRIDGE_TOTAL)
        self.assertEqual(len(answers), FRIDGE_TOTAL)


class MarketShoppingDemoTests(DemoModeTestCase):
    URL = "/api/games/market-shopping/sessions/"

    def play(self):
        question = self.client.post(self.URL).data["data"]
        session_id = question["session_id"]
        first = question
        answers = []
        for _ in range(SHOPPING_TOTAL):
            codes = [item["food_code"] for item in question["shopping_list"]]
            self.client.post(
                f"{self.URL}{session_id}/item-answers/",
                {"selected_food_codes": codes},
                format="json",
            )
            change = session_service.get_session("market_shopping", session_id)[
                "state"
            ]["correct_change"]
            data = self.client.post(
                f"{self.URL}{session_id}/change-answers/",
                {"selected_amount": change},
                format="json",
            ).data["data"]
            answers.append(data)
            if data["is_completed"]:
                break
            question = data["next_question"]
        return first, answers

    def test_demo_user_finishes_after_three_questions_with_score_80(self):
        first, answers = self.play()

        self.assertEqual(first["total_questions"], DEMO_COUNT)
        self.assertEqual(len(answers), DEMO_COUNT)
        last = answers[-1]
        self.assertTrue(last["is_completed"])
        self.assertEqual(last["total_questions"], DEMO_COUNT)
        self.assertEqual(last["standard_score"], demo_mode.DEMO_SCORE)
        # 前端結束畫面顯示的是 raw_score
        self.assertEqual(last["raw_score"], demo_mode.DEMO_SCORE)
        self.assert_demo_session_saved("market_shopping")
        # 歷史成績也是 80
        history = self.client.get("/api/games/market-shopping/history/").data["data"]
        self.assertEqual(history[-1]["score"], demo_mode.DEMO_SCORE)

    def test_normal_user_still_gets_ten_questions(self):
        self.use_normal_user()

        first, answers = self.play()

        self.assertEqual(first["total_questions"], SHOPPING_TOTAL)
        self.assertEqual(len(answers), SHOPPING_TOTAL)


class MemoryRecallDemoTests(DemoModeTestCase):
    def answer_correctly(self, session_id):
        question = self.client.get(
            "/api/games/memory-recall/round/", {"session_id": session_id}
        ).data["data"]
        answer = session_service.get_session("memory_recall", session_id)["state"][
            "current_item"
        ]
        return self.client.post(
            "/api/games/memory-recall/round/answer/",
            {
                "session_id": session_id,
                "round_number": question["round_number"],
                "selected_item": answer,
                "response_time_ms": 1000,
            },
            format="json",
        ).data["data"]

    def test_demo_user_gets_finished_on_third_round_and_score_80(self):
        start = self.client.post("/api/games/memory-recall/start/").data["data"]
        session_id = start["session_id"]
        self.assertFalse(start["is_pretest"])

        actions = [self.answer_correctly(session_id)["action"] for _ in range(3)]
        finish = self.client.post(
            "/api/games/memory-recall/finish/",
            {"session_id": session_id},
            format="json",
        ).data["data"]

        self.assertEqual(actions[:2], ["next_question", "next_question"])
        self.assertEqual(actions[2], "finished")
        self.assertEqual(finish["total_score"], demo_mode.DEMO_SCORE)
        self.assert_demo_session_saved("memory_recall")

    def test_normal_official_game_does_not_stop_at_three_rounds(self):
        self.use_normal_user()
        # 一般帳號第一場是前測，先完成一場，下一場才是正式賽
        GameSession.objects.create(
            game=session_service._get_game("memory_recall"),
            user=self.user,
            status="finished",
            result={},
        )
        session_id = self.client.post("/api/games/memory-recall/start/").data["data"][
            "session_id"
        ]

        actions = [self.answer_correctly(session_id)["action"] for _ in range(3)]

        self.assertNotIn("finished", actions)


class MarketRouteDemoTests(DemoModeTestCase):
    CONFIG_URL = "/api/games/market-route/config/"

    def test_config_total_questions_depends_on_user(self):
        data = self.client.get(self.CONFIG_URL).data["data"]
        self.assertEqual(data["total_questions"], DEMO_COUNT)

        self.use_normal_user()
        data = self.client.get(self.CONFIG_URL).data["data"]
        self.assertEqual(data["total_questions"], ROUTE_TOTAL)

    def test_demo_user_finish_after_three_questions_gives_score_80(self):
        session_id = self.client.post("/api/games/market-route/start/").data["data"][
            "session_id"
        ]
        for _ in range(DEMO_COUNT):
            question = self.client.get(
                "/api/games/market-route/round/", {"session_id": session_id}
            ).data["data"]
            self.client.post(
                "/api/games/market-route/round/answer/",
                {
                    "session_id": session_id,
                    "attempt_number": 1,
                    "answer_position": question["target_position"],
                    "is_timeout": False,
                    "response_time_ms": 400,
                    "paused_duration_ms": 0,
                },
                format="json",
            )

        data = self.client.post(
            "/api/games/market-route/finish/", {"session_id": session_id}, format="json"
        ).data["data"]

        self.assertEqual(data["total_questions"], DEMO_COUNT)
        self.assertEqual(data["answered_count"], DEMO_COUNT)
        self.assertEqual(data["total_score"], demo_mode.DEMO_SCORE)
        self.assertEqual(data["z_score"], demo_mode.DEMO_Z)
        self.assertIn("rewards", data)
        self.assert_demo_session_saved("market_route")


class MarketSortDemoTests(DemoModeTestCase):
    CONFIG_URL = "/api/games/market-sort/config/"

    def submit_three(self):
        return submit_three_market_sort_questions(self.client)

    def test_config_total_questions_depends_on_user(self):
        data = self.client.get(self.CONFIG_URL).data
        self.assertEqual(data["data"]["total_questions"], DEMO_COUNT)
        self.assertTrue(data["success"])

        self.use_normal_user()
        data = self.client.get(self.CONFIG_URL).data["data"]
        self.assertEqual(data["total_questions"], SORT_TOTAL)

    def test_config_requires_login(self):
        self.client.force_authenticate(user=None)

        self.assertEqual(self.client.get(self.CONFIG_URL).status_code, 401)

    def test_demo_user_can_submit_three_questions_and_gets_score_80(self):
        response = self.submit_three()

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["data"]["current_score"], demo_mode.DEMO_SCORE)
        self.assertFalse(response.data["data"]["is_pretest"])
        session = self.assert_demo_session_saved("market_sort")
        self.assertEqual(session.result["play_seconds"], 6)

    def test_normal_user_still_needs_full_question_count(self):
        self.use_normal_user()

        response = self.submit_three()

        # 一般帳號只交 3 題不夠正式計分：被擋下（400），也不會存成已結束
        self.assertEqual(response.status_code, 400)
        self.assertFalse(
            GameSession.objects.filter(user=self.user, status="finished").exists()
        )


class RecomputeScoresDemoTests(DemoModeTestCase):
    def test_recompute_keeps_demo_score(self):
        submit_three_market_sort_questions(self.client)
        session = GameSession.objects.get(user=self.user)
        before = dict(session.result)

        recompute_results()

        session.refresh_from_db()
        self.assertEqual(session.result, before)
