from django.core.paginator import EmptyPage, Paginator
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from config.exceptions import ApiError

from . import services
from .models import PointTransaction

DEFAULT_PAGE_SIZE = 10
MAX_PAGE_SIZE = 50


def _ok(data):
    return Response({"success": True, "data": data, "error": None})


def _int_param(request, name, default, minimum=1, maximum=None):
    raw = request.query_params.get(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        raise ApiError("INVALID_PARAM", f"{name} 必須是整數") from None
    value = max(minimum, value)
    if maximum is not None:
        value = min(maximum, value)
    return value


def _page_url(request, page):
    if page is None:
        return None
    query = request.GET.copy()
    query["page"] = page
    return request.build_absolute_uri(f"{request.path}?{query.urlencode()}")


# 首頁／會員中心：點數總覽
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def summary_view(request):
    return _ok(services.summary(request.user))


# 成就牆：三類分組，每項附是否解鎖與進度
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def achievements_view(request):
    return _ok({"categories": services.achievement_wall(request.user)})


# 點數紀錄（新的在前，分頁）。amount=0 的紀錄（達每日上限時留下的）不顯示
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def points_history_view(request):
    page = _int_param(request, "page", 1)
    page_size = _int_param(
        request, "page_size", DEFAULT_PAGE_SIZE, maximum=MAX_PAGE_SIZE
    )
    rows = PointTransaction.objects.filter(user=request.user, amount__gt=0)
    paginator = Paginator(rows, page_size)
    try:
        current = paginator.page(page)
    except EmptyPage:
        current = None

    items = []
    if current is not None:
        items = [
            {
                "id": row.id,
                "reason": row.reason,
                "label": row.label,
                "amount": row.amount,
                "created_at": timezone.localtime(row.created_at).isoformat(),
            }
            for row in current
        ]
    return _ok(
        {
            "items": items,
            "pagination": {
                "count": paginator.count,
                "next": _page_url(
                    request, current.next_page_number() if current and current.has_next() else None
                ),
                "previous": _page_url(
                    request,
                    current.previous_page_number() if current and current.has_previous() else None,
                ),
            },
        }
    )
