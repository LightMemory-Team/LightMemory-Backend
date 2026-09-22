from datetime import date
from django.utils import timezone

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions

from .models import Diary


class DiaryCalendarView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        month_param = request.query_params.get('month')
        if month_param:
            try:
                year, month = map(int, month_param.split('-'))
            except (ValueError, AttributeError):
                return Response(
                    {"error": {"code": "INVALID_MONTH", "message": "month格式錯誤"}},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        else:
            today_taipei = timezone.localdate()
            year, month = today_taipei.year, today_taipei.month

        diaries_qs = Diary.objects.filter(
            user=request.user,
            status='done',
            created_at__year=year,
            created_at__month=month,
        ).order_by('created_at')

        diaries_data = [
            {
                "diary_id": d.id,
                "date": d.created_at.date().isoformat(),
                "title": d.title,
                "photo_url": d.image_path,
                "post_text": d.post_text,
                "created_at": d.created_at.isoformat(),
            }
            for d in diaries_qs
        ]

        today = timezone.localdate()
        has_today_diary = Diary.objects.filter(
            user=request.user, status='done', created_at__date=today
        ).exists()

        return Response({
            "data": {
                "month": f"{year:04d}-{month:02d}",
                "has_today_diary": has_today_diary,
                "diaries": diaries_data,
            }
        })