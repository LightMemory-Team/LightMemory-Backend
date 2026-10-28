from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import FamilyContact, User


class FamilyContactInline(admin.TabularInline):
    model = FamilyContact
    extra = 0


# 繼承 Django 內建的 UserAdmin：密碼會以雜湊儲存，並提供「修改密碼」表單；
# 一般的 ModelAdmin 會把密碼當普通文字欄位存成明碼。
@admin.register(User)
class LightMemoryUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (
        (
            "個人資料",
            {
                "fields": (
                    "gender",
                    "birth_date",
                    "phone",
                    "address",
                    "region",
                    "avatar_url",
                )
            },
        ),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        ("個人資料", {"fields": ("last_name", "gender", "birth_date", "phone")}),
    )
    list_display = (
        "username",
        "last_name",
        "gender",
        "region",
        "phone",
        "registered_at",
        "is_staff",
    )
    list_filter = UserAdmin.list_filter + ("gender", "region")
    search_fields = ("username", "last_name", "first_name", "phone")
    inlines = [FamilyContactInline]


@admin.register(FamilyContact)
class FamilyContactAdmin(admin.ModelAdmin):
    list_display = ("family_name", "relationship", "phone", "user")
    list_filter = ("relationship",)
    search_fields = ("family_name", "phone", "user__username", "user__last_name")
    list_select_related = ("user",)
