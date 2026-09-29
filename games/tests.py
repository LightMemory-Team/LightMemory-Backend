from django.test import TestCase

from games import session_service
from games.models import Game, GameCategory, GameSession, GameStepLog


class SessionServiceTests(TestCase):
    def setUp(self):
        self.category, _ = GameCategory.objects.get_or_create(
            category_name="工作記憶", defaults={"category_description": "工作記憶訓練"}
        )
        self.game, _ = Game.objects.get_or_create(
            code="market_shopping",
            defaults={
                "game_category": self.category,
                "game_name": "市場買菜",
            },
        )

    def test_create_session(self):
        initial_state = {"difficulty": "easy", "budget": 100}
        session = session_service.create_session(
            "market_shopping", initial_state=initial_state, is_pretest=True
        )

        self.assertIsNotNone(session["session_id"])
        self.assertEqual(session["game_type"], "market_shopping")
        self.assertEqual(session["status"], "in_progress")
        self.assertEqual(session["question_number"], 0)
        self.assertIsNone(session["current_question"])
        self.assertEqual(session["step_records"], [])
        self.assertIsNone(session["result"])
        self.assertEqual(session["state"], initial_state)
        self.assertTrue(session["is_pretest"])
        self.assertIsNone(session["avg_response_time_ms"])

        # Check DB model
        db_session = GameSession.objects.get(id=session["session_id"])
        self.assertEqual(db_session.game, self.game)
        self.assertTrue(db_session.is_pretest)

    def test_get_or_create_session(self):
        client_id = "client_uuid_12345"
        session, created = session_service.get_or_create_session(
            "market_shopping", client_id, initial_state={"user_id": 1}
        )
        self.assertTrue(created)
        self.assertEqual(session["session_id"], client_id)
        self.assertEqual(session["state"]["user_id"], 1)

        # Calling again returns existing
        session2, created2 = session_service.get_or_create_session(
            "market_shopping", client_id, initial_state={"user_id": 2}
        )
        self.assertFalse(created2)
        self.assertEqual(session2["session_id"], client_id)
        self.assertEqual(session2["state"]["user_id"], 1)

    def test_get_session(self):
        session = session_service.create_session("market_shopping")
        fetched = session_service.get_session("market_shopping", session["session_id"])
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched["session_id"], session["session_id"])

        not_found = session_service.get_session("market_shopping", "non_existent_id")
        self.assertIsNone(not_found)

    def test_update_session_and_set_current_question(self):
        session = session_service.create_session(
            "market_shopping", initial_state={"stage": 1}
        )
        session_id = session["session_id"]

        question = {"target": "apple", "options": ["apple", "banana"]}
        session_service.set_current_question("market_shopping", session_id, question)

        updated = session_service.update_session(
            "market_shopping",
            session_id,
            state={"score": 10},
            question_number=1,
        )
        self.assertEqual(updated["question_number"], 1)
        self.assertEqual(updated["current_question"], question)
        self.assertEqual(updated["state"]["stage"], 1)
        self.assertEqual(updated["state"]["score"], 10)

    def test_save_step(self):
        session = session_service.create_session("market_shopping")
        session_id = session["session_id"]

        step_record = {
            "is_correct": True,
            "response_time_ms": 1500,
            "chosen": "apple",
        }
        res = session_service.save_step("market_shopping", session_id, step_record)
        self.assertEqual(len(res["step_records"]), 1)
        self.assertEqual(res["step_records"][0]["step_number"], 1)
        self.assertTrue(res["step_records"][0]["is_correct"])
        self.assertEqual(res["step_records"][0]["detail"], step_record)

        # Verify in DB
        self.assertEqual(GameStepLog.objects.filter(session_id=session_id).count(), 1)

    def test_finish_session(self):
        session = session_service.create_session("market_shopping")
        session_id = session["session_id"]

        result = {"score": 95, "total": 100}
        finished = session_service.finish_session(
            "market_shopping",
            session_id,
            result=result,
            avg_response_time_ms=1200,
        )
        self.assertEqual(finished["status"], "finished")
        self.assertEqual(finished["result"], result)
        self.assertEqual(finished["avg_response_time_ms"], 1200)

        db_session = GameSession.objects.get(id=session_id)
        self.assertEqual(db_session.status, "finished")
        self.assertIsNotNone(db_session.finished_at)

    def test_list_sessions(self):
        session_service.create_session("market_shopping")
        session_service.create_session("market_shopping")

        sessions = session_service.list_sessions("market_shopping")
        self.assertEqual(len(sessions), 2)

    def test_session_not_found(self):
        with self.assertRaises(session_service.SessionNotFound):
            session_service.update_session("market_shopping", "non_existent", state={})

        with self.assertRaises(session_service.SessionNotFound):
            session_service.save_step("market_shopping", "non_existent", {})

        with self.assertRaises(session_service.SessionNotFound):
            session_service.finish_session("market_shopping", "non_existent", {})
