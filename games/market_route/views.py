from rest_framework.decorators import api_view
from rest_framework.response import Response

# 註：以下 6 支 API 目前都回傳假資料，先讓前端可以串接測試。
# 之後 Issue #37 會換成真正的 DB 查詢 / DDA 狀態邏輯。


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


# 2. 開始一場遊戲，建立 session
# 假資料：session_id 先固定回傳，之後改成真的建立 GameSession
@api_view(["POST"])
def start(request):
    data = {
        "session_id": 501,
        "current_stage": "basic",
    }
    return Response({"success": True, "data": data, "error": None})


# 3. 取得單一題目內容
# 假資料：先固定回傳同一題，之後改成依 session 的 DDA 狀態動態出題
@api_view(["GET"])
def round_view(request):
    data = {
        "question_number": 1,
        "stage": "advanced",
        "target_item": "魚",
        "target_position": "q1",
        "distractor_items": [{"item": "貓", "position": "q3"}],
        "exposure_time_ms": 800,
    }
    return Response({"success": True, "data": data, "error": None})


# 4. 送出單題作答
# 假資料：用簡單 if-else 模擬 is_correct / action，之後改成真正的 DDA 判斷邏輯
@api_view(["POST"])
def round_answer(request):
    answer_position = request.data.get("answer_position")
    is_timeout = request.data.get("is_timeout", False)
    is_correct = (not is_timeout) and answer_position == "q1"

    if is_correct:
        action = "next_question"
    elif is_timeout:
        action = "next_question"
    else:
        action = "retry"

    data = {
        "is_correct": is_correct,
        "action": action,
        "current_stage": "intermediate",
        "correct_streak": 3,
        "wrong_attempts": 0 if is_correct else 1,
        "score_earned": 10 if is_correct else 0,
    }
    return Response({"success": True, "data": data, "error": None})


# 5. 結束遊戲，計算總結果
# 假資料：先固定回傳整場統計，之後改成用 market_score.py 彙總真實作答紀錄
@api_view(["POST"])
def finish(request):
    data = {
        "total_questions": 20,
        "answered_count": 18,
        "correct_count": 15,
        "timeout_count": 2,
        "accuracy": 0.83,
        "avg_response_time_ms": 2100,
        "final_stage": "advanced",
        "total_score": 168,
    }
    return Response({"success": True, "data": data, "error": None})


# 6. 查詢單場結果（假資料：先固定回傳，之後改成依 session_id 查 MarketRouteSession）
@api_view(["GET"])
def result(request, session_id):
    data = {
        "session_result": {
            "accuracy": 0.83,
            "correct_count": 15,
            "final_stage": "advanced",
            "total_score": 168,
        }
    }
    return Response({"success": True, "data": data, "error": None})
