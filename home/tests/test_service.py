from datetime import date, datetime

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from home import service

from .helpers import make_session

User = get_user_model()


def taipei(*args):
    return timezone.make_aware(datetime(*args))


class WeekStartTests(SimpleTestCase):
    def test_monday_is_its_own_week_start(self):
        self.assertEqual(service.week_start(date(2026, 11, 2)), date(2026, 11, 2))

    def test_sunday_belongs_to_the_week_that_started_on_monday(self):
        self.assertEqual(service.week_start(date(2026, 11, 8)), date(2026, 11, 2))

    def test_midweek(self):
        self.assertEqual(service.week_start(date(2026, 10, 28)), date(2026, 10, 26))


class PlayedGameIdsTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="u", password="x")
        self.monday = date(2026, 11, 2)

    def test_counts_finished_sessions_in_range(self):
        make_session(self.user, "market_sort", created_at=taipei(2026, 11, 3, 9))

        result = service.played_game_ids(self.user, self.monday, date(2026, 11, 4))

        self.assertEqual(result, {"market_sort"})

    def test_ignores_unfinished_sessions(self):
        make_session(
            self.user,
            "market_sort",
            status="in_progress",
            created_at=taipei(2026, 11, 3, 9),
        )

        self.assertEqual(
            service.played_game_ids(self.user, self.monday, date(2026, 11, 4)), set()
        )

    def test_last_sunday_night_is_not_this_week(self):
        make_session(self.user, "market_sort", created_at=taipei(2026, 11, 1, 23, 59))

        self.assertEqual(
            service.played_game_ids(self.user, self.monday, date(2026, 11, 4)), set()
        )

    def test_monday_midnight_is_this_week(self):
        make_session(self.user, "market_sort", created_at=taipei(2026, 11, 2, 0, 0))

        self.assertEqual(
            service.played_game_ids(self.user, self.monday, date(2026, 11, 4)),
            {"market_sort"},
        )

    def test_end_date_is_inclusive_but_next_day_is_not(self):
        make_session(self.user, "market_sort", created_at=taipei(2026, 11, 4, 23, 59))
        make_session(self.user, "fridge_check", created_at=taipei(2026, 11, 5, 0, 0))

        self.assertEqual(
            service.played_game_ids(self.user, self.monday, date(2026, 11, 4)),
            {"market_sort"},
        )

    def test_only_counts_the_given_user(self):
        other = User.objects.create_user(username="other", password="x")
        make_session(other, "market_sort", created_at=taipei(2026, 11, 3, 9))

        self.assertEqual(
            service.played_game_ids(self.user, self.monday, date(2026, 11, 4)), set()
        )
