import random

from .constants import (
    FOODS,
    POSITIONS,
    POSITION_NAMES,
    DIFFICULTY_EASY,
    DIFFICULTY_MEDIUM,
    DIFFICULTY_HARD,
    QUESTION_TYPE_RELATIVE,
    QUESTION_TYPE_LOCATE,
    QUESTION_TYPE_PLACE,
)


def generate_easy_question():
    """
    Easy：
    9 種食材各出現一次。
    題目詢問某食材左邊或右邊是什麼。
    """

    foods = FOODS.copy()
    random.shuffle(foods)

    board = []

    for position, food in zip(POSITIONS, foods):
        board.append(
            {
                "position": position,
                "food_code": food["food_code"],
                "food_name": food["food_name"],
            }
        )

    # 方便用位置找食材
    board_by_position = {
        item["position"]: item
        for item in board
    }

    # 只挑中間欄，這樣左右一定都有食材
    target_position = random.choice([
        "r1c2",
        "r2c2",
        "r3c2",
    ])

    target_food = board_by_position[target_position]

    # 隨機問左邊或右邊
    direction = random.choice(["left", "right"])

    row = target_position[1]
    col = int(target_position[3])

    if direction == "left":
        answer_position = f"r{row}c{col - 1}"
        direction_name = "左邊"
    else:
        answer_position = f"r{row}c{col + 1}"
        direction_name = "右邊"

    answer_food = board_by_position[answer_position]

    return {
        "question_type": QUESTION_TYPE_RELATIVE,
        "prompt": (
            f'{target_food["food_name"]}的'
            f'{direction_name}是什麼？'
        ),
        "board": board,
        "source_food": None,
        "correct_answer": {
            "food_code": answer_food["food_code"],
        },
    }


def generate_medium_question():
    """
    Medium：
    九宮格全部放相同食材。
    玩家依照提示找出指定位置。
    """

    food = random.choice(FOODS)
    target_position = random.choice(POSITIONS)

    board = [
        {
            "position": position,
            "food_code": food["food_code"],
            "food_name": food["food_name"],
        }
        for position in POSITIONS
    ]

    return {
        "question_type": QUESTION_TYPE_LOCATE,
        "prompt": (
            f'請找出{POSITION_NAMES[target_position]}的'
            f'{food["food_name"]}'
        ),
        "board": board,
        "source_food": None,
        "correct_answer": {
            "position": target_position,
        },
    }


def generate_hard_question():
    """
    Hard：
    冰箱九宮格全部為空。
    下方提供一個食材，
    玩家點選食材後再點指定位置。
    """

    food = random.choice(FOODS)
    target_position = random.choice(POSITIONS)

    board = [
        {
            "position": position,
            "food_code": None,
            "food_name": None,
        }
        for position in POSITIONS
    ]

    source_food = {
        "food_code": food["food_code"],
        "food_name": food["food_name"],
    }

    return {
        "question_type": QUESTION_TYPE_PLACE,
        "prompt": (
            f'請把{food["food_name"]}放到'
            f'{POSITION_NAMES[target_position]}'
        ),
        "board": board,
        "source_food": source_food,
        "correct_answer": {
            "food_code": food["food_code"],
            "position": target_position,
        },
    }


def generate_question(difficulty):
    """
    依目前 DDA 難度產生題目。
    """

    if difficulty == DIFFICULTY_EASY:
        return generate_easy_question()

    if difficulty == DIFFICULTY_MEDIUM:
        return generate_medium_question()

    if difficulty == DIFFICULTY_HARD:
        return generate_hard_question()

    raise ValueError(f"未知難度：{difficulty}")