from django.test import TestCase

from social.utils import get_display_name
from users.models import User


class UserProfileFieldsTests(TestCase):
    def test_new_fields_default_to_empty(self):
        user = User.objects.create_user(username="0912345678", password="Str0ng!Pass")

        self.assertEqual(user.nickname, "")
        self.assertIsNone(user.region)
        self.assertIsNone(user.emergency_contact_name)
        self.assertIsNone(user.emergency_contact_phone)

    def test_region_can_be_saved_as_null(self):
        user = User.objects.create_user(
            username="0912345678", password="Str0ng!Pass", region=None
        )
        user.refresh_from_db()

        self.assertIsNone(user.region)

    def test_str_prefers_nickname(self):
        user = User(username="u1", nickname="玉蘭", last_name="王")

        self.assertEqual(str(user), "玉蘭")

    def test_display_name_priority(self):
        nickname = User(username="u1", nickname="玉蘭", last_name="王", first_name="蘭")
        legacy = User(username="u2", last_name="林", first_name="奶奶")
        bare = User(username="u3")

        self.assertEqual(get_display_name(nickname), "玉蘭")
        self.assertEqual(get_display_name(legacy), "林奶奶")
        self.assertEqual(get_display_name(bare), "u3")
