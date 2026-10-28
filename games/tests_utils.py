"""
Unit test：games/utils.py 的 get_current_user。

執行：
    python manage.py test games.tests_utils
"""

from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory, TestCase

from users.models import User

from .utils import get_current_user


class GetCurrentUserTests(TestCase):
    def setUp(self):
        self.request = RequestFactory().get("/")

    def test_returns_logged_in_user(self):
        User.objects.create_user(username="first", password="testpass123")
        logged_in = User.objects.create_user(username="second", password="testpass123")
        self.request.user = logged_in

        self.assertEqual(get_current_user(self.request), logged_in)

    def test_falls_back_to_first_user_when_not_logged_in(self):
        first = User.objects.create_user(username="first", password="testpass123")
        User.objects.create_user(username="second", password="testpass123")
        self.request.user = AnonymousUser()

        self.assertEqual(get_current_user(self.request), first)

    def test_returns_none_when_no_user_exists(self):
        self.request.user = AnonymousUser()

        self.assertIsNone(get_current_user(self.request))
