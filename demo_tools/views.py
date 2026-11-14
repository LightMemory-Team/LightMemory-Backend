from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.shortcuts import redirect, render

from . import services


def demo_page(request):
    """後台「維護任務」頁：GET 顯示狀態與按鈕，POST 執行按下的任務。

    在 config/urls.py 用 admin.site.admin_view 包起來，所以一定要先登入後台；
    這裡再限定 superuser，因為按鈕會刪資料。
    """
    if not request.user.is_superuser:
        raise PermissionDenied

    user, _ = services.ensure_demo_user()

    if request.method == "POST":
        task = services.TASKS.get(request.POST.get("task"))
        if task is None:
            messages.error(request, "找不到這個任務")
        else:
            try:
                with transaction.atomic():
                    message = task["run"](user)
            except services.DemoTaskError as error:
                messages.warning(request, str(error))
            else:
                messages.success(request, f"{task['label']}：{message}")
        # 做完導回同一頁，重新整理才不會又送出一次
        return redirect("admin-demo")

    context = {
        **admin.site.each_context(request),
        "title": "維護任務",
        "demo_user": user,
        "status": services.get_status(user),
        "tasks": [{"key": key, **task} for key, task in services.TASKS.items()],
    }
    return render(request, "demo_tools/demo.html", context)
