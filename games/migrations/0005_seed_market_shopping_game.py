from django.db import migrations


def create_market_shopping_game(apps, schema_editor):
    GameCategory = apps.get_model("games", "GameCategory")
    Game = apps.get_model("games", "Game")

    category, _ = GameCategory.objects.get_or_create(
        category_name="數學",
        defaults={
            "category_description": "金錢計算與生活情境訓練"
        },
    )

    Game.objects.get_or_create(
        game_name="市場買菜",
        defaults={
            "game_category": category,
            "game_description": "透過購物清單、商品選擇與找零進行認知訓練",
            "default_difficulty": "easy",
            "is_enabled": True,
        },
    )


def remove_market_shopping_game(apps, schema_editor):
    GameCategory = apps.get_model("games", "GameCategory")
    Game = apps.get_model("games", "Game")

    Game.objects.filter(
        game_name="市場買菜",
        game_category__category_name="數學",
    ).delete()

    category = GameCategory.objects.filter(
        category_name="數學"
    ).first()

    if category and not Game.objects.filter(
        game_category=category
    ).exists():
        category.delete()


class Migration(migrations.Migration):

    dependencies = [
        (
            "games",
            "0004_marketshoppingsession_first_try_correct_count",
        ),
    ]

    operations = [
        migrations.RunPython(
            create_market_shopping_game,
            remove_market_shopping_game,
        ),
    ]