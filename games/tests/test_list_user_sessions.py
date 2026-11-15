"""歷史紀錄的場次查詢測試（list_user_sessions、list_sessions）。

重點：
- 只讀這位使用者自己的場次，在資料庫就篩選
- 查詢次數固定，不會隨場次數量增加（N+1）

執行：
    python manage.py test games.tests.test_list_user_sessions --settings=config.settings_test
"""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from games import session_service
from games.models import GameSession, GameStepLog

User = get_user_model()

FRIDGE = "fridge_check"
SHOPPING = "market_shopping"
SORT = "market_sort"

FRIDGE_RESULT = {
    "final_score": 80,
    "accuracy": 0.9,
    "average_reaction_time_ms": 1500,
    "final_difficulty": "easy",
    "completed_at": "2026-11-01T10:00:00+08:00",
    "total_correct": 9,
    "total_questions": 10,
    "speed_score": 10,
    "difficulty_bonus": 0,
    "error_penalty": 0,
}


def make_session(game_type, user, status="finished", result=None, steps=0, **extra):
    game = session_service._get_game(game_type)
    session = GameSession.objects.create(
        game=game,
        user=user,
        status=status,
        result=result,
        state={"user_id": user.id},
        **extra,
    )
    for i in range(1, steps + 1):
        GameStepLog.objects.create(
            session=session, step_number=i, is_correct=True, response_time_ms=100 * i
        )
    return session


class ListUserSessionsTests(TestCase):
    def setUp(self):
        self.me = User.objects.create_user(username="me", password="Str0ng!Pass2026")
        self.other = User.objects.create_user(
            username="other", password="Str0ng!Pass2026"
        )

    def test_returns_only_this_users_sessions(self):
        mine = make_session(FRIDGE, self.me)
        make_session(FRIDGE, self.other)

        result = session_service.list_user_sessions(FRIDGE, self.me.id)

        self.assertEqual([s["session_id"] for s in result], [str(mine.id)])

    def test_status_filter(self):
        finished = make_session(FRIDGE, self.me, status="finished")
        make_session(FRIDGE, self.me, status="in_progress")

        result = session_service.list_user_sessions(
            FRIDGE, self.me.id, status="finished"
        )

        self.assertEqual([s["session_id"] for s in result], [str(finished.id)])

    def test_only_the_requested_game(self):
        make_session(FRIDGE, self.me)
        shopping = make_session(SHOPPING, self.me)

        result = session_service.list_user_sessions(SHOPPING, self.me.id)

        self.assertEqual([s["session_id"] for s in result], [str(shopping.id)])

    def test_owner_is_decided_by_the_foreign_key_not_by_state(self):
        # state 裡沒有 user_id（或寫錯）也以資料庫外鍵為準
        session = make_session(FRIDGE, self.me)
        GameSession.objects.filter(pk=session.pk).update(state={})
        make_session(FRIDGE, self.other)
        GameSession.objects.filter(user=self.other).update(
            state={"user_id": self.me.id}
        )

        result = session_service.list_user_sessions(FRIDGE, self.me.id)

        self.assertEqual([s["session_id"] for s in result], [str(session.id)])

    def test_steps_are_not_loaded_by_default(self):
        make_session(FRIDGE, self.me, steps=3)

        result = session_service.list_user_sessions(FRIDGE, self.me.id)

        self.assertEqual(result[0]["step_records"], [])

    def test_steps_can_be_loaded_in_order(self):
        make_session(FRIDGE, self.me, steps=3)

        result = session_service.list_user_sessions(FRIDGE, self.me.id, with_steps=True)

        records = result[0]["step_records"]
        self.assertEqual([r["step_number"] for r in records], [1, 2, 3])
        self.assertEqual(
            set(records[0]), {"step_number", "is_correct", "response_time_ms", "detail"}
        )

    def test_dict_has_the_same_keys_as_before(self):
        make_session(FRIDGE, self.me)

        result = session_service.list_user_sessions(FRIDGE, self.me.id)[0]

        self.assertEqual(
            set(result),
            {
                "session_id", "game_type", "user_id", "status", "question_number",
                "current_question", "step_records", "result", "state", "is_pretest",
                "avg_response_time_ms",
            },
        )  # fmt: skip
        self.assertEqual(result["game_type"], FRIDGE)
        self.assertEqual(result["user_id"], self.me.id)

    def test_no_sessions_returns_empty_list(self):
        self.assertEqual(session_service.list_user_sessions(FRIDGE, self.me.id), [])


class QueryCountTests(TestCase):
    """場次變多，資料庫查詢次數不能跟著變多。"""

    def setUp(self):
        self.me = User.objects.create_user(username="me", password="Str0ng!Pass2026")
        self.other = User.objects.create_user(
            username="other", password="Str0ng!Pass2026"
        )
        # 先查一次，讓遊戲資料列已存在，之後的量測才不會把「第一次建立」算進去
        session_service._get_game(FRIDGE)

    def count_queries(self, func):
        with CaptureQueriesContext(connection) as ctx:
            func()
        return len(ctx)

    def test_list_user_sessions_query_count_does_not_grow(self):
        make_session(FRIDGE, self.me, steps=2)
        few = self.count_queries(
            lambda: session_service.list_user_sessions(FRIDGE, self.me.id)
        )

        for _ in range(10):
            make_session(FRIDGE, self.me, steps=2)
        many = self.count_queries(
            lambda: session_service.list_user_sessions(FRIDGE, self.me.id)
        )

        self.assertEqual(few, many)
        self.assertLessEqual(many, 2)

    def test_list_user_sessions_with_steps_query_count_does_not_grow(self):
        make_session(FRIDGE, self.me, steps=2)
        few = self.count_queries(
            lambda: session_service.list_user_sessions(
                FRIDGE, self.me.id, with_steps=True
            )
        )

        for _ in range(10):
            make_session(FRIDGE, self.me, steps=2)
        many = self.count_queries(
            lambda: session_service.list_user_sessions(
                FRIDGE, self.me.id, with_steps=True
            )
        )

        self.assertEqual(few, many)

    def test_list_sessions_query_count_does_not_grow(self):
        make_session(FRIDGE, self.me, steps=2)
        few = self.count_queries(lambda: session_service.list_sessions(FRIDGE))

        for _ in range(10):
            make_session(FRIDGE, self.me, steps=2)
            make_session(FRIDGE, self.other, steps=2)
        many = self.count_queries(lambda: session_service.list_sessions(FRIDGE))

        self.assertEqual(few, many)
        self.assertEqual(len(session_service.list_sessions(FRIDGE)), 21)

    def test_list_sessions_still_returns_ordered_steps(self):
        make_session(FRIDGE, self.me, steps=3)

        records = session_service.list_sessions(FRIDGE)[0]["step_records"]

        self.assertEqual([r["step_number"] for r in records], [1, 2, 3])


class HistoryEndpointTests(TestCase):
    """三個歷史端點：只回自己的、查詢次數不隨場次增加。"""

    def setUp(self):
        self.me = User.objects.create_user(username="me", password="Str0ng!Pass2026")
        self.other = User.objects.create_user(
            username="other", password="Str0ng!Pass2026"
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.me)

    def queries_for(self, url):
        with CaptureQueriesContext(connection) as ctx:
            response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        return response, len(ctx)

    def test_fridge_check_history_only_returns_my_finished_sessions(self):
        make_session(FRIDGE, self.me, result=FRIDGE_RESULT)
        make_session(FRIDGE, self.me, status="in_progress")
        make_session(FRIDGE, self.other, result=FRIDGE_RESULT)

        response, _ = self.queries_for("/api/games/fridge-check/history/")

        self.assertEqual(len(response.data["data"]["history"]), 1)

    def test_fridge_check_history_query_count_does_not_grow(self):
        make_session(FRIDGE, self.me, result=FRIDGE_RESULT, steps=3)
        _, few = self.queries_for("/api/games/fridge-check/history/")

        for _ in range(10):
            make_session(FRIDGE, self.me, result=FRIDGE_RESULT, steps=3)
            make_session(FRIDGE, self.other, result=FRIDGE_RESULT, steps=3)
        response, many = self.queries_for("/api/games/fridge-check/history/")

        self.assertEqual(few, many)
        self.assertEqual(len(response.data["data"]["history"]), 11)

    def test_market_shopping_history_returns_latest_ten_of_mine_oldest_first(self):
        for i in range(12):
            make_session(
                SHOPPING,
                self.me,
                result={"completed_at": f"2026-11-{i + 1:02d}T10:00:00"},
            )
        make_session(
            SHOPPING, self.other, result={"completed_at": "2026-12-01T10:00:00"}
        )

        response, _ = self.queries_for("/api/games/market-shopping/history/")

        played = [h["played_at"] for h in response.data["data"]]
        self.assertEqual(len(played), 10)
        self.assertEqual(played, sorted(played))
        self.assertEqual(played[-1], "2026-11-12T10:00:00")
        self.assertNotIn("2026-12-01T10:00:00", played)

    def test_market_shopping_history_query_count_does_not_grow(self):
        make_session(SHOPPING, self.me, result={"completed_at": "2026-11-01T10:00:00"})
        _, few = self.queries_for("/api/games/market-shopping/history/")

        for i in range(10):
            make_session(
                SHOPPING,
                self.me,
                result={"completed_at": f"2026-11-{i + 2:02d}T10:00:00"},
            )
            make_session(
                SHOPPING, self.other, result={"completed_at": "2026-12-01T10:00:00"}
            )
        _, many = self.queries_for("/api/games/market-shopping/history/")

        self.assertEqual(few, many)

    def test_history_does_not_load_other_users_sessions(self):
        """歷史端點只處理自己的場次：其他人的場次不會被轉成 dict 載入記憶體。"""
        for _ in range(3):
            make_session(FRIDGE, self.me, result=FRIDGE_RESULT)
            make_session(
                SHOPPING, self.me, result={"completed_at": "2026-11-01T10:00:00"}
            )
        for _ in range(7):
            make_session(FRIDGE, self.other, result=FRIDGE_RESULT)
            make_session(
                SHOPPING, self.other, result={"completed_at": "2026-11-01T10:00:00"}
            )

        for url in (
            "/api/games/fridge-check/history/",
            "/api/games/market-shopping/history/",
        ):
            with self.subTest(url=url):
                with patch.object(
                    session_service, "_to_dict", wraps=session_service._to_dict
                ) as spy:
                    self.client.get(url)

                self.assertEqual(spy.call_count, 3)
