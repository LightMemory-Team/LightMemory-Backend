from datetime import date
from django.utils import timezone

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions

from .models import Diary,DiaryReply, DiaryAnalysis
from . import external, ai_gen, analysis as analysis_utils



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
    def post(self, request):
        photo = request.FILES.get('photo')
        if not photo:
            return Response({"error": {"code": "INVALID_IMAGE", "message": "這張照片無法使用，換一張試試看吧"}}, status=400)

        image_url = external.upload_to_firebase(photo, "images")
        first_question = ai_gen.generate_first_question()

        diary = Diary.objects.create(
            user=request.user,
            image_path=image_url,
            first_question=first_question,
            status="pending",
        )
        return Response({
            "data": {
                "diary_id": diary.id,
                "photo_url": diary.image_path,
                "first_question": first_question,
                "status": diary.status,
                "created_at": diary.created_at.isoformat(),
            }
        }, status=status.HTTP_201_CREATED)

class DiaryReplyView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, diary_id):
        try:
            diary = Diary.objects.get(id=diary_id, user=request.user)
        except Diary.DoesNotExist:
            return Response({"error": {"code": "DIARY_NOT_FOUND", "message": "找不到這篇日記"}}, status=404)

        if diary.status == "done":
            return Response({"error": {"code": "DIARY_ALREADY_FINALIZED", "message": "這篇日記已經完成了"}}, status=400)

        audio = request.FILES.get('audio')
        round_index = request.data.get('round_index')
        if not audio or not round_index:
            return Response({"error": {"code": "INVALID_AUDIO", "message": "這一段錄音沒有收到，請再錄一次"}}, status=400)
        round_index = int(round_index)

        transcript = external.transcribe_audio(audio)
        audio_url = external.upload_to_firebase(audio, "audio")

        question_for_this_round = diary.pending_question or diary.first_question
        DiaryReply.objects.create(
            diary=diary, round_index=round_index,
            question=question_for_this_round, transcript=transcript,
            audio_path=audio_url, is_skipped=False,
        )
        diary.status = "processing"

        reply_count = diary.replies.count()
        non_skipped_count = diary.replies.filter(is_skipped=False).count()
        is_done = reply_count >= 4

        ai_reply = None
        if not is_done:
            ai_reply = ai_gen.generate_follow_up(transcript)
            diary.pending_question = ai_reply
        else:
            diary.pending_question = ""
        diary.save()

        return Response({
            "data": {
                "round_index": round_index,
                "transcript": transcript,
                "audio_url": audio_url,
                "ai_reply": ai_reply,
                "reply_count": reply_count,
                "is_finalizable": non_skipped_count >= 2,
                "is_done": is_done,
            }
        }, status=status.HTTP_201_CREATED)


class DiaryFinalizeView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, diary_id):
        try:
            diary = Diary.objects.get(id=diary_id, user=request.user)
        except Diary.DoesNotExist:
            return Response({"error": {"code": "DIARY_NOT_FOUND", "message": "找不到這篇日記"}}, status=404)

        if diary.status == "done":
            return self._build_response(diary, http_status=200)

        replies = diary.replies.filter(is_skipped=False).order_by('round_index')
        combined = '，'.join(r.transcript for r in replies if r.transcript)
        if not combined:
            return Response({"error": {"code": "NO_VALID_REPLY", "message": "需要先錄一段內容才能生成日記"}}, status=400)

        diary.transcription = combined
        diary.diary_text = combined

        quality = analysis_utils.assess_sample_quality(combined)
        if quality != "ok":
            DiaryAnalysis.objects.update_or_create(diary=diary, defaults={"is_valid": False, "invalid_reason": quality})
        else:
            result = analysis_utils.analyze_transcription(combined)
            DiaryAnalysis.objects.update_or_create(diary=diary, defaults={"is_valid": True, **result})

        content = ai_gen.generate_finalize_content(combined)
        diary.title = content["title"]
        diary.ai_response = content["ai_response"]
        diary.post_text = content["post_text"]
        diary.hashtags = content["hashtags"]
        diary.category = content["category"]
        diary.suggested_replies = content["suggested_replies"]
        diary.invite_text = content["invite_text"]
        diary.status = "done"
        diary.save()

        return self._build_response(diary, http_status=201)

    def _build_response(self, diary, http_status):
        return Response({
            "data": {
                "diary_id": diary.id,
                "status": diary.status,
                "date": diary.created_at.date().isoformat(),
                "created_at": diary.created_at.isoformat(),
                "photo_url": diary.image_path,
                "title": diary.title,
                "ai_response": diary.ai_response,
                "post_text": diary.post_text,
                "hashtags": diary.hashtags,
                "category": diary.category,
                "invite_text": diary.invite_text,
            }
        }, status=http_status)