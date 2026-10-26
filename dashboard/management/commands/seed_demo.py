"""建立 demo 帳號的展示資料：五款遊戲各 9 場、聲影日記 9 篇。

    python manage.py seed_demo
    python manage.py seed_demo --username demo --password demo1234

分三批，每批每款遊戲 3 場、日記 3 篇，讓儀表板和週報都有東西看：
- 前週：週報「跟上週比」的比較基準（2 天有活動）
- 上週：週報的報告週，分數比前週高（3 天有活動 →「比上週多 1 天」）
- 這週：現在往前 1～3 小時，儀表板雷達圖（近 7 天）用

每場都有 z_score，所以儀表板「五款遊戲各滿 3 場」的解鎖條件一定會達成。
result 欄位照各遊戲結束時真正存的格式，各遊戲的歷史紀錄 API 才不會出錯。

重跑會先刪掉這個帳號之前 seed 的資料再重建：遊戲場次看 client_session_id、
日記看 audio_path 是不是 "seed" 開頭，不會動到真的遊玩紀錄。只寫資料，不改資料表。
"""

from datetime import datetime, time, timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from dashboard.services import DIMENSIONS, GAME_SOURCES, GAME_TITLES
from diary.analysis import get_risk_result
from diary.models import Diary, DiaryAnalysis, DiaryReply
from games.models import Game, GameCategory, GameSession
from games.zscore import z_score_to_display_score
from users.models import User

SEED_PREFIX = "seed"

# 每批的 z 基準：前週低一點、上週進步，週報的趨勢才會顯示「進步」
BATCH_Z = {"previous": -0.3, "report": 0.3, "recent": 0.5}
# 同一批 3 筆在基準上下變化一點，看起來比較像真的
Z_SPREAD = [-0.1, 0.1, 0.0]

DIARY_THEMES = [
    {
        "title": "🍜 跟孫子吃牛肉麵",
        "first_question": "照片裡的牛肉麵是在哪裡吃的呢？",
        "transcription": "今天中午帶孫子去巷口吃牛肉麵，他吃得好開心，湯都喝光了。",
        "ai_response": "跟孫子一起吃飯真溫馨，他一定很喜歡跟您出門！",
        "post_text": "今天帶孫子去吃牛肉麵，他吃得好開心。",
        "hashtags": ["#家人", "#美食", "#午餐"],
        "category": "food",
        "replies": ["是巷口那家老店，開了二十幾年了。", "下次想帶他去吃水餃。"],
    },
    {
        "title": "🌳 公園散步",
        "first_question": "這是哪一座公園呢？",
        "transcription": "早上跟老朋友去公園散步，看到很多人在跳舞，空氣很好。",
        "ai_response": "早上散步好舒服，跟老朋友聊天一定很愉快！",
        "post_text": "早上跟老朋友去公園散步，空氣好好。",
        "hashtags": ["#散步", "#朋友", "#早晨"],
        "category": "entertainment",
        "replies": ["是家附近的中正公園。", "我們約好每個禮拜都去。"],
    },
    {
        "title": "📚 書法課",
        "first_question": "今天寫了什麼字呢？",
        "transcription": "下午去社區大學上書法課，老師教我們寫春字，我寫了好幾張。",
        "ai_response": "寫書法要很專心，您寫了好幾張真認真！",
        "post_text": "下午去上書法課，寫了好幾張春字。",
        "hashtags": ["#書法", "#學習", "#社區大學"],
        "category": "education",
        "replies": ["老師說我的字越來越工整了。", "想寫一張送給女兒。"],
    },
]

DIARY_SCORE_OFFSETS = {
    "fluency_score": 0.2,
    "information_score": -0.1,
    "sentence_score": 0.1,
    "naming_score": -0.2,
    "semantic_score": 0.0,
}


def _clamp(value, low, high):
    return max(low, min(high, value))


def _at(day, hour):
    return timezone.make_aware(datetime.combine(day, time(hour)))


def batch_times(now):
    """三批各 3 個時間點（台灣時間）。"""
    today = timezone.localdate(now)
    this_monday = today - timedelta(days=today.weekday())
    previous = this_monday - timedelta(days=14)
    report = this_monday - timedelta(days=7)
    return {
        # 週二兩次、週五一次 → 2 天有活動
        "previous": [
            _at(previous + timedelta(days=1), 10),
            _at(previous + timedelta(days=1), 15),
            _at(previous + timedelta(days=4), 10),
        ],
        # 週一、週三、週五 → 3 天有活動
        "report": [_at(report + timedelta(days=d), 10) for d in (0, 2, 4)],
        "recent": [now - timedelta(hours=h) for h in (3, 2, 1)],
    }


# ---------- 各遊戲結束時的 result（格式照各遊戲 services／views） ----------


def _market_route_result(z, finished_at):
    correct = _clamp(round(16 + 2 * z), 0, 20)
    return {
        "total_questions": 20,
        "answered_count": 20,
        "correct_count": correct,
        "timeout_count": 1,
        "accuracy": round(correct / 20, 2),
        "avg_response_time_ms": round(1500 - 200 * z),
        "final_stage": "intermediate",
        "total_score": round(correct / 20 * 100),
        "z_score": round(z, 3),
    }


def _memory_recall_result(z, finished_at):
    correct = _clamp(round(6 + z), 0, 8)
    return {
        "total_rounds": 8,
        "total_correct": correct,
        "total_wrong": 8 - correct,
        "accuracy": round(correct / 8, 2),
        "avg_response_time_ms": round(2500 - 300 * z),
        "final_stage": "intermediate",
        "total_bonus_seconds": 15,
        "total_score": z_score_to_display_score(z),
        "z_score": round(z, 3),
    }


def _market_sort_result(z, finished_at):
    return {
        "raw_metrics": {
            "overall_accuracy": round(0.8 + 0.05 * z, 3),
            "switch_accuracy": round(0.7 + 0.05 * z, 3),
            "switch_cost_rt": round(400 - 50 * z, 1),
            "switch_cost_accuracy": round(0.1 - 0.02 * z, 3),
            "rt_cv": round(0.3 - 0.03 * z, 3),
            "learning_speed": round(1 + 0.2 * z, 2),
        },
        "z_scores": {
            "overall_accuracy_z": round(z, 3),
            "switch_accuracy_z": round(z, 3),
            "switch_cost_rt_z": round(z, 3),
            "learning_speed_z": round(z, 3),
        },
        "z_score": round(z, 3),
        "cognitive_flexibility_score": round(50 + 20 * z),
        "play_seconds": 240,
        "generated_at": finished_at.isoformat(),
    }


def _ten_question_scores(z):
    """冰箱檢查、市場買菜共用：答對題數、正確率、速度分、原始分數、z。

    z 照遊戲本身的公式由原始分數算回來：(原始分數 - 70) / 10，限制在 ±2；
    答對題數用 7.4 + z，算回來的 z 才會接近傳進來的 z。
    """
    correct = _clamp(round(7.4 + z), 0, 10)
    accuracy = correct * 10.0
    speed_score = round(60 + 10 * z, 1)
    raw_score = round(accuracy * 0.7 + speed_score * 0.3, 1)
    real_z = round(_clamp((raw_score - 70) / 10, -2, 2), 3)
    return correct, accuracy, speed_score, raw_score, real_z


def _fridge_check_result(z, finished_at):
    correct, accuracy, speed_score, raw_score, real_z = _ten_question_scores(z)
    medium_correct, hard_correct = 2, 1
    difficulty_bonus = medium_correct * 0.5 + hard_correct * 1.0
    return {
        "total_correct": correct,
        "total_questions": 10,
        "accuracy": accuracy,
        "speed_score": speed_score,
        "raw_score": raw_score,
        "medium_correct": medium_correct,
        "hard_correct": hard_correct,
        "difficulty_bonus": difficulty_bonus,
        "skipped_question_count": 0,
        "error_penalty": 0,
        "final_score": round(raw_score + difficulty_bonus, 1),
        "z_score": real_z,
        "standard_score": round(50 + 20 * real_z),
        "final_difficulty": "medium",
        "average_reaction_time_ms": round(3000 - 300 * z),
        "completed_at": finished_at.isoformat(),
    }


def _market_shopping_result(z, finished_at):
    correct, accuracy, speed_score, raw_score, real_z = _ten_question_scores(z)
    return {
        "total_correct": correct,
        "first_try_correct_count": correct,
        "total_questions": 10,
        "accuracy": accuracy,
        "speed_score": speed_score,
        "raw_score": raw_score,
        "z_score": real_z,
        "standard_score": round(50 + 20 * real_z),
        "average_reaction_time_ms": round(4000 - 400 * z),
        "difficulty": "medium",
        "completed_at": finished_at.isoformat(),
    }


RESULT_BUILDERS = {
    "market_route": _market_route_result,
    "memory_recall": _memory_recall_result,
    "market_sort": _market_sort_result,
    "fridge_check": _fridge_check_result,
    "market_shopping": _market_shopping_result,
}

QUESTION_COUNTS = {
    "market_route": 20,
    "memory_recall": 8,
    "market_sort": 0,
    "fridge_check": 10,
    "market_shopping": 10,
}


def ensure_games():
    """五款遊戲沒有的就建立，分類用雷達圖的能力名稱；已經有的不動。"""
    labels = {item["source"]: item["label"] for item in DIMENSIONS}
    games = {}
    for code in GAME_SOURCES:
        category, _ = GameCategory.objects.get_or_create(category_name=labels[code])
        games[code], _ = Game.objects.get_or_create(
            code=code, defaults={"name": GAME_TITLES[code], "category": category}
        )
    return games


def clear_seed_data(user):
    GameSession.objects.filter(
        user=user, client_session_id__startswith=f"{SEED_PREFIX}-"
    ).delete()
    Diary.objects.filter(user=user, audio_path__startswith=f"{SEED_PREFIX}/").delete()


def create_game_sessions(user, games, times):
    for game_index, code in enumerate(GAME_SOURCES):
        for batch, slots in times.items():
            for i, slot in enumerate(slots):
                z = BATCH_Z[batch] + Z_SPREAD[i]
                # 同一個時段五款遊戲錯開 10 分鐘，每場玩 4 分鐘
                finished_at = slot + timedelta(minutes=10 * game_index)
                session = GameSession.objects.create(
                    game=games[code],
                    user=user,
                    client_session_id=f"{SEED_PREFIX}-{user.id}-{code}-{batch}-{i}",
                    status="finished",
                    question_number=QUESTION_COUNTS[code],
                    result=RESULT_BUILDERS[code](z, finished_at),
                    state={"user_id": user.id, "is_pretest": False},
                    finished_at=finished_at,
                )
                # created_at 是 auto_now_add，只能建立後再改
                GameSession.objects.filter(pk=session.pk).update(
                    created_at=finished_at - timedelta(minutes=4)
                )


def create_diaries(user, times):
    for batch, slots in times.items():
        for i, slot in enumerate(slots):
            theme = DIARY_THEMES[i]
            created_at = slot - timedelta(minutes=30)
            diary = Diary.objects.create(
                user=user,
                audio_path=f"{SEED_PREFIX}/{batch}-{i}.m4a",
                transcription=theme["transcription"],
                diary_text=theme["transcription"],
                title=theme["title"],
                first_question=theme["first_question"],
                ai_response=theme["ai_response"],
                status="done",
                post_text=theme["post_text"],
                hashtags=theme["hashtags"],
                category=theme["category"],
                suggested_replies=["好溫馨！", "看起來好棒！", "下次也帶我去！"],
                invite_text="一起來分享你的生活吧！",
            )
            Diary.objects.filter(pk=diary.pk).update(created_at=created_at)

            for round_index, transcript in enumerate(theme["replies"], start=1):
                reply = DiaryReply.objects.create(
                    diary=diary, round_index=round_index, transcript=transcript
                )
                # 週報的對話時長 = 最後一則回答時間 − 日記建立時間
                DiaryReply.objects.filter(pk=reply.pk).update(
                    created_at=created_at + timedelta(minutes=2 * round_index)
                )

            create_diary_analysis(diary, BATCH_Z[batch] + Z_SPREAD[i])


def create_diary_analysis(diary, z):
    """小分數設在 3 + z 附近（每項 0～4 分）。

    不用量表中點 2：5 項加總會在 10 分左右，被 get_risk_result 判成 high，
    展示資料不該出現「建議諮詢」的回饋。
    """
    scores = {
        name: round(_clamp(3 + z + offset, 0, 4), 2)
        for name, offset in DIARY_SCORE_OFFSETS.items()
    }
    total_score = round(sum(scores.values()), 2)
    risk = get_risk_result(total_score)
    DiaryAnalysis.objects.create(
        diary=diary,
        is_valid=True,
        **scores,
        communication_score=round(
            scores["fluency_score"] * 0.20
            + scores["information_score"] * 0.20
            + scores["sentence_score"] * 0.20
            + scores["naming_score"] * 0.15
            + scores["semantic_score"] * 0.25,
            2,
        ),
        total_score=total_score,
        average_score=round(total_score / 5, 2),
        risk_level=risk["risk_level"],
        ai_feedback=risk["suggestion"],
    )


class Command(BaseCommand):
    help = "建立 demo 帳號的展示資料（五款遊戲各 9 場、聲影日記 9 篇）"

    def add_arguments(self, parser):
        parser.add_argument("--username", default="demo")
        parser.add_argument("--password", default="demo1234")

    @transaction.atomic
    def handle(self, *args, **options):
        user, created = User.objects.get_or_create(username=options["username"])
        if created:
            user.set_password(options["password"])
            user.save()

        games = ensure_games()
        clear_seed_data(user)
        times = batch_times(timezone.now())
        create_game_sessions(user, games, times)
        create_diaries(user, times)

        account = "新建立" if created else "已存在"
        self.stdout.write(
            self.style.SUCCESS(
                f"完成！帳號 {user.username}（{account}）："
                f"五款遊戲各 9 場、聲影日記 9 篇"
            )
        )
