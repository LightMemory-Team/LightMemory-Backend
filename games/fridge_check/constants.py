# 冰箱清點固定食材
FOODS = [
    {
        "food_code": "egg",
        "food_name": "雞蛋",
    },
    {
        "food_code": "milk",
        "food_name": "牛奶",
    },
    {
        "food_code": "tofu",
        "food_name": "豆腐",
    },
    {
        "food_code": "tomato",
        "food_name": "番茄",
    },
    {
        "food_code": "cabbage",
        "food_name": "高麗菜",
    },
    {
        "food_code": "pepper",
        "food_name": "青椒",
    },
    {
        "food_code": "carrot",
        "food_name": "胡蘿蔔",
    },
    {
        "food_code": "apple",
        "food_name": "蘋果",
    },
    {
        "food_code": "banana",
        "food_name": "香蕉",
    },
]


# 冰箱固定 3 × 3 九宮格
POSITIONS = [
    "r1c1",
    "r1c2",
    "r1c3",
    "r2c1",
    "r2c2",
    "r2c3",
    "r3c1",
    "r3c2",
    "r3c3",
]


# 九宮格位置的中文名稱
POSITION_NAMES = {
    "r1c1": "第一排左邊",
    "r1c2": "第一排中間",
    "r1c3": "第一排右邊",
    "r2c1": "第二排左邊",
    "r2c2": "第二排中間",
    "r2c3": "第二排右邊",
    "r3c1": "第三排左邊",
    "r3c2": "第三排中間",
    "r3c3": "第三排右邊",
}


# 三種難度
DIFFICULTY_EASY = "easy"
DIFFICULTY_MEDIUM = "medium"
DIFFICULTY_HARD = "hard"


# 三種題型
QUESTION_TYPE_RELATIVE = "relative_position"
QUESTION_TYPE_LOCATE = "locate_position"
QUESTION_TYPE_PLACE = "place_item"


# 整場遊戲總題數
TOTAL_QUESTIONS = 10


# 每題最多可答錯 3 次
MAX_WRONG_ATTEMPTS = 3


# 連續答對 3 題升級
PROMOTE_STREAK = 3