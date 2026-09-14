from rest_framework.decorators import api_view
from rest_framework.response import Response


# 1. 取得本場遊戲設定
@api_view(["GET"])
def config(request):
    data = {
        "is_pretest": False,
        "current_stage": "basic",
        "total_questions": 20,
        "timeout_seconds": 20,
        "promote_streak": 5,
        "max_wrong_attempts": 3,
        "stage_exposure_range": {
            "basic": [2000, 1500],
            "intermediate": [1500, 1000],
            "advanced": [1000, 500],
        },
    }
    return Response({"success": True, "data": data, "error": None})
