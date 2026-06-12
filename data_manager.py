import json
import os
import copy
from typing import Optional
from config import REPORT_FILE

DEFAULT_CATEGORIES = [
    {"name": "Мп2", "type": "label"},
    {"name": "Сто", "type": "plan_fact", "plan": "10000", "fact": 0},
    {"name": "Сим", "type": "plan_fact", "plan": "5", "fact": 0},
    {"name": "Мнп", "type": "plan_fact", "plan": "2", "fact": 0},
    {"name": "Супер", "type": "plan_fact", "plan": "2", "fact": 0},
    {"name": "Аб", "type": "plan_fact", "plan": "1", "fact": 0},
    {"name": "Тв", "type": "plan_fact", "plan": "13500", "fact": 0},
    {"name": "Акс", "type": "plan_fact", "plan": "3000", "fact": 0},
    {"name": "Наст", "type": "plan_fact", "plan": "1000", "fact": 0},
    {"name": "Страх", "type": "plan_fact", "plan": "500", "fact": 0},
    {"name": "Епо", "type": "status", "value": "закрыт"},
    {"name": "Бештау", "type": "plan_fact", "plan": "1", "fact": 0},
    {"name": "Висяк", "type": "single", "value": 0},
    {"name": "Перо", "type": "single", "value": 0},
    {"name": "Пленки", "type": "plan_fact", "plan": "2", "fact": 0},
]

DEFAULT_SLOTS = {str(h): {"enabled": True} for h in [12, 15, 18, 19]}


def _default_data() -> dict:
    return {
        "categories": copy.deepcopy(DEFAULT_CATEGORIES),
        "slots": copy.deepcopy(DEFAULT_SLOTS),
        "last_reset_date": "",
    }


def load_data() -> dict:
    if not os.path.exists(REPORT_FILE):
        data = _default_data()
        save_data(data)
        return data
    with open(REPORT_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_data(data: dict):
    with open(REPORT_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def update_category(data: dict, name: str, value) -> str:
    """Обновить категорию. Возвращает текст подтверждения."""
    for cat in data["categories"]:
        if cat["name"] != name:
            continue
        if cat["type"] == "label":
            return f"❌ {name} — это заголовок, его не редактируют"
        elif cat["type"] == "plan_fact":
            cat["fact"] = int(value) if value else 0
            save_data(data)
            return f"✅ {name}: {cat['plan']}/{cat['fact']}"
        elif cat["type"] == "single":
            cat["value"] = int(value) if value else 0
            save_data(data)
            return f"✅ {name}: {cat['value']}"
        elif cat["type"] == "status":
            cat["value"] = str(value)
            save_data(data)
            return f"✅ {name}: {cat['value']}"
    return f"❌ Категория {name} не найдена"


def get_editable_categories(data: dict) -> list:
    """Категории, которые можно редактировать (не label)."""
    return [c for c in data["categories"] if c["type"] != "label"]


def format_report(data: dict) -> str:
    """Сформировать текст отчёта как в старом data.txt."""
    lines = ["📊 Отчёт по продажам:", ""]
    for cat in data["categories"]:
        if cat["type"] == "label":
            lines.append(cat["name"])
        elif cat["type"] == "plan_fact":
            lines.append(f"{cat['name']} {cat['plan']}/{cat['fact']}")
        elif cat["type"] == "single":
            lines.append(f"{cat['name']} {cat['value']}")
        elif cat["type"] == "status":
            lines.append(f"{cat['name']} {cat['value']}")
    return "\n".join(lines)


def has_sales(data: dict) -> bool:
    """Есть ли хоть одна ненулевая продажа."""
    for cat in data["categories"]:
        if cat["type"] == "plan_fact" and cat["fact"] > 0:
            return True
        if cat["type"] == "single" and cat.get("value", 0) > 0:
            return True
    return False


def reset_data():
    """Сбросить все факты в 0."""
    data = load_data()
    for cat in data["categories"]:
        if cat["type"] == "plan_fact":
            cat["fact"] = 0
        elif cat["type"] == "single":
            cat["value"] = 0
    save_data(data)
    return data


def set_slot(data: dict, hour: int, enabled: bool):
    key = str(hour)
    if key in data["slots"]:
        data["slots"][key]["enabled"] = enabled
        save_data(data)
        return True
    return False
