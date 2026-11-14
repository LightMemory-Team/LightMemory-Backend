from datetime import date, timedelta
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions

from rewards import services as rewards_services
from social.models import Post
from social.utils import get_visible_post, serialize_post

from .models import Diary, DiaryReply, DiaryAnalysis
from . import external, ai_gen, analysis as analysis_utils
from .media import media_url


# 統一回傳格式 {success, data, error}。
# 錯誤一律用 _error；成功回應目前只有 finalize、share 用 _ok，其餘端點尚未統一。
def _ok(data, http_status=status.HTTP_200_OK):
    return Response({"success": True, "data": data, "error": None}, status=http_status)


def _error(code, message, http_status):
    return Response(
        {"success": False, "data": None, "error": {"code": code, "message": message}},
        status=http_status,
    )


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
                "date": timezone.localtime(d.created_at).date().isoformat(),
                "title": d.title,
                "photo_url": media_url(d.image_path),
                "post_text": d.post_text,
                "created_at": timezone.localtime(d.created_at).isoformat(),
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
                "photo_url": media_url(diary.image_path),
                "first_question": first_question,
                "status": diary.status,
                "created_at": timezone.localtime(diary.created_at).isoformat(),
            }
        }, status=status.HTTP_201_CREATED)

# 一篇日記最多問答幾輪：第 4 輪回覆後就算完成（is_done）
MAX_REPLY_ROUNDS = 4


def parse_round_index(raw):
    """把前端送來的 round_index 轉成 1～MAX_REPLY_ROUNDS 的整數。

    不是整數（"abc"、"1.5"、true）或超出範圍都回傳 None。
    multipart 表單送來的是字串（"1"），JSON 送來的可能是整數（1），兩種都接受。
    """
    if isinstance(raw, bool):
        return None
    if isinstance(raw, int):
        value = raw
    elif isinstance(raw, str):
        try:
            value = int(raw.strip())
        except ValueError:
            return None
    else:
        return None
    if not 1 <= value <= MAX_REPLY_ROUNDS:
        return None
    return value


ROUND_ALREADY_ANSWERED = (
    "ROUND_ALREADY_ANSWERED",
    "這一輪已經回答過了",
    status.HTTP_409_CONFLICT,
)


class DiaryReplyView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, diary_id):
        try:
            diary = Diary.objects.get(id=diary_id, user=request.user)
        except Diary.DoesNotExist:
            return _error("DIARY_NOT_FOUND", "找不到這篇日記", 404)

        if diary.status == "done":
            return _error("DIARY_ALREADY_FINALIZED", "這篇日記已經完成了", 400)

        audio = request.FILES.get('audio')
        raw_round_index = request.data.get('round_index')
        if not audio or raw_round_index is None or raw_round_index == "":
            return _error("INVALID_AUDIO", "這一段錄音沒有收到，請再錄一次", 400)
        round_index = parse_round_index(raw_round_index)
        if round_index is None:
            return _error("INVALID_ROUND_INDEX", "這一輪的編號不正確，請重新錄音", 400)
        # 語音辨識、上傳都很花時間，重複的輪次先擋掉，不要白做
        if diary.replies.filter(round_index=round_index).exists():
            return _error(*ROUND_ALREADY_ANSWERED)

        transcript = external.transcribe_audio(audio)
        if transcript is None:
            return _error("TRANSCRIPTION_FAILED", "語音辨識失敗，請再錄一次", 500)
        audio.seek(0)
        audio_url = external.upload_to_firebase(audio, "audio")
        if audio_url is None:
            return _error("UPLOAD_FAILED", "錄音上傳失敗，請再試一次", 500)

        # 寫入資料庫的部分放在同一個 transaction：新增回覆、更新日記狀態要嘛都成功、
        # 要嘛都不寫。select_for_update 鎖住這篇日記，同一篇同時送來的請求會排隊，
        # 避免重複輪次（IntegrityError → 500）、回覆數算錯。
        with transaction.atomic():
            diary = Diary.objects.select_for_update().get(pk=diary.pk)
            rejected = None
            if diary.status == "done":
                rejected = ("DIARY_ALREADY_FINALIZED", "這篇日記已經完成了", 400)
            elif diary.replies.filter(round_index=round_index).exists():
                rejected = ROUND_ALREADY_ANSWERED
            if rejected:
                # 剛上傳的錄音用不到了，盡力刪掉，不要留下孤兒檔案
                external.delete_from_firebase([audio_url])
                return _error(*rejected)

            question_for_this_round = diary.pending_question or diary.first_question
            DiaryReply.objects.create(
                diary=diary, round_index=round_index,
                question=question_for_this_round, transcript=transcript,
                audio_path=audio_url, is_skipped=False,
            )
            diary.status = "processing"

            reply_count = diary.replies.count()
            non_skipped_count = diary.replies.filter(is_skipped=False).count()
            is_done = reply_count >= MAX_REPLY_ROUNDS

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
                "audio_url": media_url(audio_url),
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
            return _error("DIARY_NOT_FOUND", "找不到這篇日記", status.HTTP_404_NOT_FOUND)

        if diary.status == "done":
            # 已完成的日記再呼叫一次：grant() 不會重複入帳，回 0 點
            return self._build_response(
                diary, http_status=200, rewards=self._grant(diary)
            )

        # 分析、AI 內容、日記狀態放在同一個 transaction：中途失敗全部還原，
        # 不會留下「有分析結果、日記卻停在 processing」的半完成狀態。
        # 鎖住這篇日記，同時送來的第二個請求會等第一個完成，看到 done 後直接回傳，
        # 不會重複分析、重複呼叫 AI。
        with transaction.atomic():
            diary = Diary.objects.select_for_update().get(pk=diary.pk)
            already_done = diary.status == "done"
            if not already_done:
                replies = diary.replies.filter(is_skipped=False).order_by('round_index')
                combined = '，'.join(r.transcript for r in replies if r.transcript)
                if not combined:
                    return _error(
                        "NO_VALID_REPLY",
                        "需要先錄一段內容才能生成日記",
                        status.HTTP_400_BAD_REQUEST,
                    )

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

        # 發點放在 transaction「之外」、日記已確定寫入之後：
        # grant() 是盡力而為（失敗只回 rewards.error、不丟例外），
        # 不該拉長持鎖時間，也不該讓發點失敗影響日記完成。
        # 同時送來而在鎖後才看到 done 的請求，grant() 不會重複入帳。
        return self._build_response(
            diary,
            http_status=200 if already_done else 201,
            rewards=self._grant(diary),
        )

    @staticmethod
    def _grant(diary):
        """日記完成：發放點數與成就，回傳 rewards 區塊。"""
        return rewards_services.grant(
            diary.user, rewards_services.DIARY_COMPLETE, diary
        )

    def _build_response(self, diary, http_status, rewards):
        return _ok(
            {
                "diary_id": diary.id,
                "status": diary.status,
                "date": timezone.localtime(diary.created_at).date().isoformat(),
                "created_at": timezone.localtime(diary.created_at).isoformat(),
                "photo_url": media_url(diary.image_path),
                "title": diary.title,
                "ai_response": diary.ai_response,
                "post_text": diary.post_text,
                "hashtags": diary.hashtags,
                "category": diary.category,
                "invite_text": diary.invite_text,
                "rewards": rewards,
            },
            http_status,
        )


class DiaryShareView(APIView):
    """S-1 POST /api/diary/{diary_id}/share/
    分享日記到動態牆。首次分享回傳 201，已分享過回傳 200 並回傳同筆貼文。
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, diary_id):
        try:
            diary = Diary.objects.get(id=diary_id, user=request.user)
        except Diary.DoesNotExist:
            return _error("DIARY_NOT_FOUND", "找不到這篇日記", status.HTTP_404_NOT_FOUND)

        if diary.status != "done":
            return _error(
                "DIARY_NOT_DONE",
                "日記還沒完成，完成後才能分享",
                status.HTTP_400_BAD_REQUEST,
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
        # 第一次分享解鎖「樂於分享」成就；再分享一次不會重複解鎖
        data["rewards"] = rewards_services.grant(
            request.user, rewards_services.DIARY_SHARED
        )
        http_status = status.HTTP_201_CREATED if created else status.HTTP_200_OK
        return _ok(data, http_status)


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
                "audio_url": media_url(r.audio_path),
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
            "photo_url": media_url(diary.image_path),
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
                "photo_url": media_url(d.image_path),
                "post_text": d.post_text,
                "audio_url": media_url(audio_url),
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
