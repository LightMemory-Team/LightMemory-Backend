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
            GAME_TYPE, session_id, initial_state={"user_id": request.user.id}
        )

        # 冪等性處理：同一個 session_id 重複送出時，直接回傳既有結果，不重算不重寫
        if not created:
            if session["status"] != "finished":
                return Response(
                    {"success": True, "data": None, "error": None},
                    status=status.HTTP_201_CREATED,
                )
            return self._build_response(request.user, session)

        if not is_complete:
            return Response(
                {"success": True, "data": None, "error": None},
                status=status.HTTP_201_CREATED,
            )

        try:
            result = calculate_cognitive_flexibility_score(questions)
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
                "cognitive_flexibility_score": result["cognitive_flexibility_score"],
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

        current_score = session["result"]["cognitive_flexibility_score"]
        highest_score = max(
            [h["result"]["cognitive_flexibility_score"] for h in history],
            default=current_score,
        )

        others = [h for h in history if h["session_id"] != session["session_id"]]
        recent_scores = [h["result"]["cognitive_flexibility_score"] for h in others[:4]]
        recent_scores.reverse()

        tier = determine_encouragement_tier(current_score, highest_score)

        return Response(
            {
                "success": True,
                "data": {
                    "current_score": current_score,
                    "highest_score": highest_score,
                    "recent_scores": recent_scores,
                    "encouragement_tier": tier,
                },
                "error": None,
            },
            status=status.HTTP_201_CREATED,
        )
