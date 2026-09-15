from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions

from .serializers import MarketSortSubmitSerializer
from .services import calculate_cognitive_flexibility_score, determine_encouragement_tier, InsufficientDataError
from ..models import MarketSortResult


class MarketSortSubmitView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = MarketSortSubmitSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {"error": {"code": "INVALID_QUESTION_DATA", "details": serializer.errors}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        validated = serializer.validated_data
        session_id = validated["session_id"]
        is_complete = validated["is_complete"]
        questions = validated["questions"]

        # 冪等性處理：同一個 session_id 重複送出時，直接回傳既有結果，不重新計算、不重複寫入
        existing = MarketSortResult.objects.filter(session_id=session_id).first()
        if existing:
            if not existing.is_complete:
                return Response({"data": None}, status=status.HTTP_201_CREATED)
            return self._build_response(request.user, existing)

        if not is_complete:
            MarketSortResult.objects.create(
                user=request.user, session_id=session_id, is_complete=False,
            )
            return Response({"data": None}, status=status.HTTP_201_CREATED)

        try:
            result = calculate_cognitive_flexibility_score(questions)
        except InsufficientDataError as e:
            return Response(
                {"error": {"code": e.code, "message": str(e)}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        record = MarketSortResult.objects.create(
            user=request.user,
            session_id=session_id,
            is_complete=True,
            raw_metrics=result["raw_metrics"],
            z_scores=result["z_scores"],
            cognitive_flexibility_score=result["cognitive_flexibility_score"],
        )

        return self._build_response(request.user, record)

    def _build_response(self, user, record):
        history = MarketSortResult.objects.filter(
            user=user, is_complete=True
        ).order_by("-generated_at")

        current_score = record.cognitive_flexibility_score
        highest_score = max([r.cognitive_flexibility_score for r in history], default=current_score)

        others = [r for r in history if r.session_id != record.session_id]
        recent_scores = [r.cognitive_flexibility_score for r in others[:4]]
        recent_scores.reverse()

        tier = determine_encouragement_tier(current_score, highest_score)

        return Response(
            {"data": {
                "current_score": current_score,
                "highest_score": highest_score,
                "recent_scores": recent_scores,
                "encouragement_tier": tier,
            }},
            status=status.HTTP_201_CREATED,
        )