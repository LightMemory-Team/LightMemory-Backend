"""
System test：market-sort API 端到端測試
寫法比照 users/tests/test_api_system.py
執行：python manage.py test games.market_sort.tests --settings=config.settings_test
"""

from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

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
