"""週報表（weekly_report.py、GET /api/dashboard/weekly-report/）的測試。

計算函式的測試把「今天」固定成 2026-10-15（四），報告週就是
10/5（一）～10/11（日），比較週是 9/28～10/4。
"""

from datetime import date, datetime, time, timedelta
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase, TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from ai_service.weekly_summary import build_fallback_summary
from diary.models import Diary, DiaryReply
from games import session_service
from games.models import GameSession
from users.models import User

from .services import DIMENSIONS, GAME_SOURCES
from .weekly_report import (
    build_abilities,
    build_weekly_report,
    get_daily_activity,
    get_play_time,
    get_played_sources,
    get_report_week,
    get_trend,
    get_week_diaries,
    get_weekly_scores_history,
    longest_streak,
    suggest_untried_source,
)

WEEKLY_REPORT_URL = "/api/dashboard/weekly-report/"

TODAY = date(2026, 10, 15)
WEEK_START = date(2026, 10, 5)


def at(day, hour=10, minute=0, second=0):
    """台灣時間的某天某時（aware datetime）。"""
    return timezone.make_aware(datetime(2026, 10, day, hour, minute, second))


def make_session(user, game, *, created_at, finished_at=None, z_score=None):
    """建立一場遊戲；有給 finished_at 就是已結束的場次，結算結果帶 z_score。"""
    session_id = session_service.create_session(game, user=user)["session_id"]
    fields = {"created_at": created_at}
    if finished_at is not None:
        fields.update(
            status="finished", finished_at=finished_at, result={"z_score": z_score}
        )
    GameSession.objects.filter(pk=session_id).update(**fields)


def finished_on(user, game, day, z_score, *, hour=10, minute=0):
    """建立一場在 day（date）那天結束、帶 z_score 的場次。"""
    finished_at = timezone.make_aware(datetime.combine(day, time(hour, minute)))
    make_session(
        user,
        game,
        created_at=finished_at - timedelta(minutes=5),
        finished_at=finished_at,
        z_score=z_score,
    )


def make_diary(user, *, created_at, status="done", reply_times=(), **fields):
    """建立一篇日記，reply_times 是每則回答的時間。"""
    diary = Diary.objects.create(user=user, status=status, **fields)
    Diary.objects.filter(pk=diary.pk).update(created_at=created_at)
    for i, reply_at in enumerate(reply_times, start=1):
        reply = DiaryReply.objects.create(diary=diary, round_index=i)
        DiaryReply.objects.filter(pk=reply.pk).update(created_at=reply_at)
    return diary


def disable_ai(test_case):
    """週報直接用固定句型，不呼叫 AI；測試不會真的打 OpenAI、不花錢。

    AI 本身的行為（失敗改用備案、禁用詞檢查）在 ai_service/tests.py 測。
    """
    patcher = patch(
        "dashboard.weekly_report.generate_weekly_summary",
        side_effect=build_fallback_summary,
    )
    patcher.start()
    test_case.addCleanup(patcher.stop)


def activity(*flags):
    """組一週的 daily_activity，例如 activity(1, 0, 1, 0, 0, 0, 0)。"""
    return [{"is_active": bool(f)} for f in flags]


class GetReportWeekTests(SimpleTestCase):
    def test_thursday_looks_at_previous_week(self):
        self.assertEqual(
            get_report_week(TODAY), (date(2026, 10, 5), date(2026, 10, 11))
        )

    def test_monday_looks_at_week_just_ended(self):
        self.assertEqual(
            get_report_week(date(2026, 10, 12)),
            (date(2026, 10, 5), date(2026, 10, 11)),
        )

    def test_sunday_still_looks_at_previous_week(self):
        # 週日這週還沒結束，看的是上一週
        self.assertEqual(
            get_report_week(date(2026, 10, 11)),
            (date(2026, 9, 28), date(2026, 10, 4)),
        )

    def test_across_months(self):
        self.assertEqual(
            get_report_week(date(2026, 11, 2)),
            (date(2026, 10, 26), date(2026, 11, 1)),
        )


class LongestStreakTests(SimpleTestCase):
    def test_longest_run_in_week(self):
        # 一、三、五、六 → 五六連續 2 天
        self.assertEqual(longest_streak(activity(1, 0, 1, 0, 1, 1, 0)), 2)

    def test_no_activity_is_zero(self):
        self.assertEqual(longest_streak(activity(0, 0, 0, 0, 0, 0, 0)), 0)

    def test_every_day_is_seven(self):
        self.assertEqual(longest_streak(activity(1, 1, 1, 1, 1, 1, 1)), 7)


class SuggestUntriedSourceTests(SimpleTestCase):
    def test_first_untried_in_radar_order(self):
        played = set(GAME_SOURCES)  # 五款遊戲都玩了，只差日記
        self.assertEqual(suggest_untried_source(played), "這週還沒玩語言，下週試試看")

    def test_nothing_played_suggests_first_dimension(self):
        first_label = DIMENSIONS[0]["label"]
        self.assertEqual(
            suggest_untried_source(set()), f"這週還沒玩{first_label}，下週試試看"
        )

    def test_everything_played(self):
        played = {d["source"] for d in DIMENSIONS}
        self.assertEqual(
            suggest_untried_source(played), "每一項都玩過了，下週繼續保持！"
        )


class WeeklyReportDataTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="tester", password="pw123456")
        disable_ai(self)

    def test_daily_activity_from_games_and_diaries(self):
        make_session(self.user, "market_route", created_at=at(5))  # 週一，沒玩完也算
        make_diary(self.user, created_at=at(7), status="pending")  # 週三寫日記
        make_session(self.user, "market_route", created_at=at(12))  # 下一週，不算

        days = get_daily_activity(self.user, WEEK_START)

        self.assertEqual(len(days), 7)
        self.assertEqual(
            days[0], {"date": "2026-10-05", "weekday": "一", "is_active": True}
        )
        self.assertEqual([d["is_active"] for d in days], [1, 0, 1, 0, 0, 0, 0])

    def test_late_night_counts_as_same_day_in_taiwan(self):
        # 台灣時間週一 23:30（UTC 是 15:30）還是算週一
        make_session(self.user, "market_route", created_at=at(5, hour=23, minute=30))

        days = get_daily_activity(self.user, WEEK_START)

        self.assertEqual([d["is_active"] for d in days], [1, 0, 0, 0, 0, 0, 0])

    def test_play_time_sums_finished_sessions_only(self):
        make_session(
            self.user,
            "market_route",
            created_at=at(5, minute=0),
            finished_at=at(5, minute=5),
        )
        make_session(
            self.user,
            "market_route",
            created_at=at(6, minute=0),
            finished_at=at(6, minute=2),
        )
        make_session(self.user, "memory_recall", created_at=at(6))  # 沒玩完，不算
        make_session(  # 上上週結束的，不算
            self.user,
            "memory_recall",
            created_at=at(1),
            finished_at=at(1, minute=10),
        )

        play_time = get_play_time(self.user, WEEK_START)

        games = {g["source"]: g for g in play_time["games"]}
        self.assertEqual([g["source"] for g in play_time["games"]], GAME_SOURCES)
        self.assertEqual(games["market_route"]["seconds"], 7 * 60)
        self.assertEqual(games["market_route"]["label"], "菜市場找路")
        self.assertEqual(games["memory_recall"]["seconds"], 0)
        self.assertEqual(play_time["total_seconds"], 7 * 60)

    def test_week_diaries_only_done_and_talk_seconds(self):
        make_diary(
            self.user,
            created_at=at(5, minute=0),
            title="早上的公園散步",
            image_path="https://example.com/a.jpg",
            post_text="今天去公園走了一圈。",
            reply_times=[at(5, minute=3), at(5, minute=10)],
        )
        make_diary(self.user, created_at=at(8))  # 沒有回答，對話時長 0
        make_diary(self.user, created_at=at(9), status="pending")  # 還沒完成，不列
        make_diary(self.user, created_at=at(13))  # 下一週，不列

        diary = get_week_diaries(self.user, WEEK_START)

        self.assertEqual(diary["talk_seconds"], 10 * 60)
        self.assertEqual(len(diary["entries"]), 2)
        first = diary["entries"][0]
        self.assertEqual(first["date"], "2026-10-05")
        self.assertEqual(first["title"], "早上的公園散步")
        self.assertEqual(first["photo_url"], "https://example.com/a.jpg")
        self.assertEqual(first["post_text"], "今天去公園走了一圈。")

    def test_played_sources(self):
        make_session(self.user, "market_sort", created_at=at(6))
        make_diary(self.user, created_at=at(7), status="pending")

        played = get_played_sources(self.user, WEEK_START)

        self.assertEqual(played, {"market_sort", "diary"})

    def test_build_weekly_report(self):
        # 報告週：週一、週三有玩；上週（比較週）只有 1 天
        make_session(
            self.user,
            "market_route",
            created_at=at(5),
            finished_at=at(5, minute=5),
        )
        make_session(
            self.user,
            "memory_recall",
            created_at=at(7),
            finished_at=at(7, minute=2),
        )
        make_session(self.user, "market_route", created_at=at(1))

        report = build_weekly_report(self.user, TODAY)

        self.assertEqual(report["week_start"], "2026-10-05")
        self.assertEqual(report["week_end"], "2026-10-11")
        self.assertEqual(report["summary"], "這週你玩了 2 天，比上週多 1 天！")
        self.assertEqual(
            report["highlights"],
            {"active_day_count": 2, "session_count": 2, "streak_days": 1},
        )
        self.assertEqual(report["play_time"]["total_seconds"], 7 * 60)
        self.assertEqual(report["next_week_goal"], "這週還沒玩執行功能，下週試試看")
        self.assertEqual(len(report["abilities"]["dimensions"]), 6)
        self.assertEqual(report["disclaimer"], "這不是醫療診斷，僅供自我了解")

    def test_other_users_data_not_counted(self):
        other = User.objects.create_user(username="other", password="pw123456")
        make_session(
            other, "market_route", created_at=at(5), finished_at=at(5, minute=1)
        )
        make_diary(other, created_at=at(6))

        report = build_weekly_report(self.user, TODAY)

        self.assertEqual(report["highlights"]["active_day_count"], 0)
        self.assertEqual(report["highlights"]["session_count"], 0)
        self.assertEqual(report["diary"]["entries"], [])


class GetTrendTests(SimpleTestCase):
    def test_up(self):
        self.assertEqual(get_trend(78, 66), "up")

    def test_steady(self):
        self.assertEqual(get_trend(70, 69), "steady")

    def test_practice_instead_of_negative_word(self):
        self.assertEqual(get_trend(60, 66), "practice")

    def test_threshold_is_three(self):
        self.assertEqual(get_trend(53, 50), "up")
        self.assertEqual(get_trend(47, 50), "practice")
        self.assertEqual(get_trend(52, 50), "steady")

    def test_missing_week_is_none(self):
        self.assertIsNone(get_trend(None, 66))
        self.assertIsNone(get_trend(70, None))


class AbilitiesTests(TestCase):
    """報告週 10/5～10/11、上週 9/28～10/4。"""

    def setUp(self):
        self.user = User.objects.create_user(username="tester", password="pw123456")

    def _ability(self, abilities, dimension):
        return next(d for d in abilities["dimensions"] if d["dimension"] == dimension)

    def test_weekly_score_is_average_z_converted(self):
        finished_on(self.user, "market_route", date(2026, 10, 5), 0.4)
        finished_on(self.user, "market_route", date(2026, 10, 8), 0.8)
        finished_on(self.user, "market_route", date(2026, 10, 9), None)  # 不算

        history = get_weekly_scores_history(self.user, WEEK_START)

        # 平均 z 0.6 → 50 + 25 * 0.6 = 65
        self.assertEqual(history, {WEEK_START: {"market_route": 65}})

    def test_sunday_late_night_counts_in_that_week(self):
        # 台灣時間週日 23:30 結束，還算報告週
        finished_on(
            self.user, "market_route", date(2026, 10, 11), 0.0, hour=23, minute=30
        )

        history = get_weekly_scores_history(self.user, WEEK_START)

        self.assertEqual(list(history), [WEEK_START])

    def test_this_week_last_week_best_and_trend(self):
        finished_on(self.user, "market_route", date(2026, 9, 21), 1.2)  # 80 分
        finished_on(self.user, "market_route", date(2026, 9, 30), 0.0)  # 上週 50
        finished_on(self.user, "market_route", date(2026, 10, 6), 0.6)  # 本週 65
        finished_on(self.user, "market_route", date(2026, 10, 13), 2.0)  # 報告週之後

        abilities = build_abilities(self.user, WEEK_START, {"market_route"})

        attention = self._ability(abilities, "attention")
        self.assertEqual(
            attention,
            {
                "dimension": "attention",
                "label": "注意力",
                "played": True,
                "this_week": 65,
                "last_week": 50,
                # 報告週之後那週的 100 分不算
                "best": 80,
                "trend": "up",
            },
        )

    def test_not_played_dimension_is_all_null(self):
        abilities = build_abilities(self.user, WEEK_START, set())

        math = self._ability(abilities, "math")
        self.assertFalse(math["played"])
        self.assertIsNone(math["this_week"])
        self.assertIsNone(math["best"])
        self.assertIsNone(math["trend"])

    def test_language_has_no_score_but_played_from_diary(self):
        abilities = build_abilities(self.user, WEEK_START, {"diary"})

        language = self._ability(abilities, "language")
        self.assertTrue(language["played"])
        self.assertIsNone(language["this_week"])
        self.assertIsNone(language["trend"])

    def test_six_dimensions_in_radar_order(self):
        abilities = build_abilities(self.user, WEEK_START, set())

        self.assertEqual(
            [d["dimension"] for d in abilities["dimensions"]],
            [d["dimension"] for d in DIMENSIONS],
        )

    def test_overall_is_average_of_scored_games(self):
        finished_on(self.user, "market_route", date(2026, 9, 21), 1.2)  # 80
        finished_on(self.user, "market_route", date(2026, 9, 30), 0.0)  # 50
        finished_on(self.user, "market_route", date(2026, 10, 6), 0.6)  # 65
        finished_on(self.user, "memory_recall", date(2026, 10, 7), -0.36)  # 41

        overall = build_abilities(self.user, WEEK_START, set())["overall"]

        # 本週 (65 + 41) / 2 = 53；上週只有 50；最佳是 9/21 那週的 80
        self.assertEqual(
            overall, {"this_week": 53, "last_week": 50, "best": 80, "trend": "up"}
        )


class WeeklyReportAiSummaryTests(TestCase):
    """週報的 summary 真的用 AI 的回傳，而且只把正向事實交給 AI。"""

    def setUp(self):
        self.user = User.objects.create_user(username="tester", password="pw123456")

    def test_summary_from_ai_with_positive_facts(self):
        make_session(self.user, "market_route", created_at=at(5))
        reply = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content="這週有來動動腦，真棒！")
                )
            ]
        )

        with patch("ai_service.weekly_summary._client") as mock_client:
            create = mock_client.return_value.chat.completions.create
            create.return_value = reply
            report = build_weekly_report(self.user, TODAY)

        self.assertEqual(report["summary"], "這週有來動動腦，真棒！")
        user_message = create.call_args.kwargs["messages"][1]["content"]
        self.assertIn("1 天", user_message)


class WeeklyReportApiTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="tester", password="pw123456")
        self.client.force_authenticate(user=self.user)
        disable_ai(self)

    def test_unauthenticated_returns_401(self):
        self.client.force_authenticate(user=None)

        response = self.client.get(WEEKLY_REPORT_URL)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(response.data["error"]["code"], "NOT_AUTHENTICATED")

    def test_returns_report_of_last_complete_week(self):
        week_start, week_end = get_report_week(timezone.localdate())
        make_session(
            self.user,
            "market_route",
            created_at=timezone.make_aware(
                datetime.combine(week_start, datetime.min.time())
            )
            + timedelta(hours=10),
        )

        response = self.client.get(WEEKLY_REPORT_URL)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["success"])
        self.assertIsNone(response.data["error"])
        data = response.data["data"]
        self.assertEqual(data["week_start"], week_start.isoformat())
        self.assertEqual(data["week_end"], week_end.isoformat())
        self.assertEqual(data["highlights"]["active_day_count"], 1)
        self.assertEqual(len(data["daily_activity"]), 7)

    def test_no_activity_still_returns_report(self):
        # 週報不設解鎖門檻，沒玩也有內容
        response = self.client.get(WEEKLY_REPORT_URL)

        self.assertTrue(response.data["success"])
        self.assertEqual(
            response.data["data"]["summary"], "好久不見，下週一起來動動腦吧！"
        )
