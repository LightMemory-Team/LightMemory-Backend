from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from games import session_service

from .serializers import MarketSortSubmitSerializer
from .services import (
    InsufficientDataError,
    calculate_cognitive_flexibility_score,
    determine_encouragement_tier,
)

GAME_TYPE = "market_sort"


def _previous_raw_metrics(session_id):
    """這場之前已結束場次的原始指標，給 z-score 當比較基準。

    回傳 (自己的清單, {其他使用者 id: 清單})，全體依使用者分組。
    """

    def raw_metrics_of(results):
        return [r["raw_metrics"] for r in results if "raw_metrics" in r]

    personal = raw_metrics_of(
        session_service.list_previous_results(GAME_TYPE, session_id)
    )
    population = {
        user_id: raw_metrics_of(results)
        for user_id, results in session_service.list_previous_results_by_user(
            GAME_TYPE, session_id
        ).items()
    }
    return personal, population


class MarketSortSubmitView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = MarketSortSubmitSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {
                    "success": False,
                    "data": None,
                    "error": {
                        "code": "INVALID_QUESTION_DATA",
                        "details": serializer.errors,
                    },
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        validated = serializer.validated_data
        session_id = validated["session_id"]
        is_complete = validated["is_complete"]
        questions = validated["questions"]

        session, created = session_service.get_or_create_session(
            GAME_TYPE,
            session_id,
            initial_state={"user_id": request.user.id},
            user=request.user,
            is_pretest=session_service.is_first_session(GAME_TYPE, request.user),
        )

        # 冪等性處理：同一個 session_id 已經算過分，直接回傳既有結果，不重算不重寫。
        # 還沒結束的（之前送過未完成、或資料不足被擋下）照常往下驗證、計分，
        # 否則補送完整資料也永遠拿不到分數。
        if not created and session["status"] == "finished":
            return self._build_response(request.user, session)

        if not is_complete:
            return Response(
                {"success": True, "data": None, "error": None},
                status=status.HTTP_201_CREATED,
            )

        # 熟悉場不算分，給空歷史讓 z、分數都是 None
        histories = (
            ([], {}) if session["is_pretest"] else _previous_raw_metrics(session_id)
        )
        try:
            result = calculate_cognitive_flexibility_score(questions, *histories)
        except InsufficientDataError as e:
            return Response(
                {
                    "success": False,
                    "data": None,
                    "error": {"code": e.code, "message": str(e)},
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        session = session_service.finish_session(
            GAME_TYPE,
            session_id,
            result={
                "raw_metrics": result["raw_metrics"],
                "z_scores": result["z_scores"],
                "z_score": result["z_score"],
                "cognitive_flexibility_score": result["cognitive_flexibility_score"],
                # 這款遊戲玩完才一次送出，session 的開始、結束時間幾乎一樣，
                # 遊玩時間改用 28 題反應時間加總（週報表用）
                "play_seconds": round(
                    sum(q["reaction_time_ms"] for q in questions) / 1000
                ),
                "generated_at": timezone.now().isoformat(),
            },
        )

        return self._build_response(request.user, session)

    def _build_response(self, user, session):
        all_sessions = session_service.list_sessions(GAME_TYPE)
        history = [
            s
            for s in all_sessions
            if s["status"] == "finished" and s["state"].get("user_id") == user.id
        ]
        history.sort(key=lambda s: s["result"]["generated_at"], reverse=True)

        # 資料不足的場次分數是 None，最高分、近期分數都不算它
        current_score = session["result"]["cognitive_flexibility_score"]
        highest_score = max(
            (
                h["result"]["cognitive_flexibility_score"]
                for h in history
                if h["result"]["cognitive_flexibility_score"] is not None
            ),
            default=current_score,
        )

        others = [h for h in history if h["session_id"] != session["session_id"]]
        recent_scores = [
            h["result"]["cognitive_flexibility_score"]
            for h in others
            if h["result"]["cognitive_flexibility_score"] is not None
        ][:4]
        recent_scores.reverse()

        tier = determine_encouragement_tier(current_score, highest_score)

        return Response(
            {
                "success": True,
                "data": {
                    "is_pretest": session["is_pretest"],
                    "current_score": current_score,
                    "highest_score": highest_score,
                    "recent_scores": recent_scores,
                    "encouragement_tier": tier,
                },
                "error": None,
            },
            status=status.HTTP_201_CREATED,
        )
