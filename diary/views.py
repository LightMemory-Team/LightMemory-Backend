from datetime import date, timedelta
from django.conf import settings
from django.utils import timezone

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions

from social.models import Post
from social.utils import get_visible_post, serialize_post

from .models import Diary, DiaryReply, DiaryAnalysis
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
        if image_url is None:
            return Response({"error": {"code": "UPLOAD_FAILED", "message": "照片上傳失敗，請再試一次"}}, status=500)
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
        if transcript is None:
            return Response({"error": {"code": "TRANSCRIPTION_FAILED", "message": "語音辨識失敗，請再錄一次"}}, status=500)
        audio.seek(0)
        audio_url = external.upload_to_firebase(audio, "audio")
        if audio_url is None:
            return Response({"error": {"code": "UPLOAD_FAILED", "message": "錄音上傳失敗，請再試一次"}}, status=500)

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


class DiaryShareView(APIView):
    """S-1 POST /api/diary/{diary_id}/share/
    分享日記到動態牆。首次分享回傳 201，已分享過回傳 200 並回傳同筆貼文。
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, diary_id):
        try:
            diary = Diary.objects.get(id=diary_id, user=request.user)
        except Diary.DoesNotExist:
            return Response(
                {"error": {"code": "DIARY_NOT_FOUND", "message": "找不到這篇日記"}},
                status=status.HTTP_404_NOT_FOUND,
            )

        if diary.status != "done":
            return Response(
                {"error": {"code": "DIARY_NOT_DONE", "message": "日記還沒完成，完成後才能分享"}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        post, created = Post.objects.get_or_create(
            diary=diary,
            defaults={
                "user": request.user,
                "post_type": "diary",
                "content": diary.post_text,
                "image_path": diary.image_path,
            },
        )

        visible_post = get_visible_post(request.user, post.id)
        data = serialize_post(visible_post, request.user)
        http_status = status.HTTP_201_CREATED if created else status.HTTP_200_OK
        return Response({"data": data}, status=http_status)


class DiaryDetailView(APIView):
    """D-4 GET /api/diary/{diary_id}/
    單篇日記詳情。包含問答列表、AI內容與分享狀態（is_shared, post_id, share_url）。
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, diary_id):
        try:
            diary = (
                Diary.objects.select_related("social_post")
                .prefetch_related("replies")
                .get(id=diary_id, user=request.user)
            )
        except Diary.DoesNotExist:
            return Response(
                {"error": {"code": "DIARY_NOT_FOUND", "message": "找不到這篇日記"}},
                status=status.HTTP_404_NOT_FOUND,
            )

        replies = diary.replies.all().order_by("round_index")
        replies_data = [
            {
                "round_index": r.round_index,
                "question": r.question,
                "transcript": r.transcript,
                "audio_url": r.audio_path,
                "is_skipped": r.is_skipped,
            }
            for r in replies
        ]

        reply_count = len(replies_data)
        non_skipped_count = sum(1 for r in replies_data if not r["is_skipped"])
        is_done = diary.status == "done"

        has_post = hasattr(diary, "social_post") and diary.social_post is not None and diary.social_post.is_enabled
        post = diary.social_post if has_post else None
        post_id = post.id if post else None
        share_url = (
            f"{settings.SHARE_BASE_URL.rstrip('/')}/share/{post.share_token}/"
            if post
            else None
        )

        data = {
            "diary_id": diary.id,
            "date": timezone.localtime(diary.created_at).date().isoformat(),
            "created_at": timezone.localtime(diary.created_at).isoformat(),
            "status": diary.status,
            "photo_url": diary.image_path,
            "first_question": diary.first_question,
            "replies": replies_data,
            "pending_question": diary.pending_question or None,
            "reply_count": reply_count,
            "is_finalizable": non_skipped_count >= 2,
            "is_done": is_done,
            "title": diary.title,
            "ai_response": diary.ai_response,
            "post_text": diary.post_text,
            "hashtags": diary.hashtags,
            "category": diary.category,
            "is_shared": has_post,
            "post_id": post_id,
            "share_url": share_url,
            "invite_text": diary.invite_text,
        }

        return Response({"data": data}, status=status.HTTP_200_OK)


class DiaryReviewView(APIView):
    """D-2 GET /api/diary/review/
    動態回顧：顯示昨天與去年的今天的日記（僅本人且 status='done'）。
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        today = timezone.localdate()
        yesterday = today - timedelta(days=1)
        try:
            last_year_date = today.replace(year=today.year - 1)
        except ValueError:
            last_year_date = today.replace(year=today.year - 1, day=28)

        base_qs = (
            Diary.objects.filter(user=request.user, status="done")
            .select_related("social_post")
            .prefetch_related("replies")
            .order_by("-created_at")
        )

        yesterday_qs = base_qs.filter(created_at__date=yesterday)
        last_year_qs = base_qs.filter(created_at__date=last_year_date)

        def _serialize(d):
            has_post = hasattr(d, "social_post") and d.social_post is not None and d.social_post.is_enabled
            first_reply = next((r for r in d.replies.all() if r.round_index == 1), None)
            audio_url = first_reply.audio_path if first_reply and first_reply.audio_path else None
            return {
                "diary_id": d.id,
                "date": timezone.localtime(d.created_at).date().isoformat(),
                "title": d.title,
                "photo_url": d.image_path,
                "post_text": d.post_text,
                "audio_url": audio_url,
                "is_shared": has_post,
                "post_id": d.social_post.id if has_post else None,
                "created_at": timezone.localtime(d.created_at).isoformat(),
            }

        return Response({
            "data": {
                "yesterday": [_serialize(d) for d in yesterday_qs],
                "last_year": [_serialize(d) for d in last_year_qs],
            }
        }, status=status.HTTP_200_OK)
