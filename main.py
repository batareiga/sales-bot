#!/usr/bin/env python3
"""
Chappie Bot — Sales tracker for Telegram
Single-file version for Pella.app deployment
"""
import os
import json
import copy
import asyncio
import logging
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Optional

from aiogram import Bot, Dispatcher, Router, F, types
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    BotCommand, BotCommandScopeDefault, BotCommandScopeAllGroupChats,
    BotCommandScopeChat, InlineKeyboardMarkup, InlineKeyboardButton,
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

# ─── CONFIG ────────────────────────────────────────────────────

BOT_TOKEN = os.getenv("BOT_TOKEN", "7074124522:AAGDj_9mv1acF0snCP_jrSMP29UZpV31OAk")
VADIM_ID = int(os.getenv("VADIM_ID", "1025948006"))
SALES_GROUP_ID = int(os.getenv("SALES_GROUP_ID", "-4876944974"))
REPORT_FILE = os.getenv("REPORT_FILE", "data.json")
TIMEZONE = os.getenv("TIMEZONE", "Europe/Moscow")
SLOTS = [12, 15, 18, 19]
REMINDER_OFFSET_MINUTES = 45

# ─── LOGGING ──────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# ─── BOT SETUP ─────────────────────────────────────────────────

bot = None  # set in main()
router = Router()
scheduler = AsyncIOScheduler(timezone=TIMEZONE)


# ─── DATA LAYER ────────────────────────────────────────────────

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

DEFAULT_SLOTS = {str(h): {"enabled": True} for h in SLOTS}


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


def update_category(data: dict, name: str, value):
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
    return [c for c in data["categories"] if c["type"] != "label"]


def format_report(data: dict) -> str:
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
    for cat in data["categories"]:
        if cat["type"] == "plan_fact" and cat["fact"] > 0:
            return True
        if cat["type"] == "single" and cat.get("value", 0) > 0:
            return True
    return False


def reset_data():
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


# ─── GUARD ──────────────────────────────────────────────────────

def _is_vadim(user_id: int) -> bool:
    return user_id == VADIM_ID


# ─── KEYBOARDS ──────────────────────────────────────────────────

def main_menu_kb() -> InlineKeyboardMarkup:
    kb = [
        [InlineKeyboardButton(text="📊 Данные", callback_data="menu_data"),
         InlineKeyboardButton(text="✏️ Править", callback_data="menu_edit")],
        [InlineKeyboardButton(text="⏰ Расписание", callback_data="menu_schedule"),
         InlineKeyboardButton(text="🔄 Сброс", callback_data="menu_reset")],
        [InlineKeyboardButton(text="📤 Отправить", callback_data="menu_send")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)


def back_kb(dest: str = "menu_main") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Назад", callback_data=dest)],
    ])


def edit_kb(data: dict) -> InlineKeyboardMarkup:
    cats = get_editable_categories(data)
    kb = []
    for i in range(0, len(cats), 3):
        row = []
        for c in cats[i:i + 3]:
            label = c["name"]
            if c["type"] == "plan_fact" and c["fact"] > 0:
                label += f" {c['fact']}"
            row.append(InlineKeyboardButton(text=label, callback_data=f"edit_val:{c['name']}"))
        kb.append(row)
    kb.append([InlineKeyboardButton(text="✅ Готово", callback_data="menu_main")])
    return InlineKeyboardMarkup(inline_keyboard=kb)


def schedule_kb(data: dict) -> InlineKeyboardMarkup:
    kb = []
    for h in SLOTS:
        key = str(h)
        enabled = data["slots"].get(key, {}).get("enabled", False)
        icon = "🟢" if enabled else "🔴"
        action = "disable" if enabled else "enable"
        kb.append([
            InlineKeyboardButton(text=f"{icon} {h}:00", callback_data="noop"),
            InlineKeyboardButton(text="🔘", callback_data=f"slot_{action}:{h}"),
        ])
    any_on = any(data["slots"].get(str(h), {}).get("enabled", False) for h in SLOTS)
    if any_on:
        kb.append([InlineKeyboardButton(text="⏸ Пауза всех", callback_data="slot_pause")])
    else:
        kb.append([InlineKeyboardButton(text="▶️ Запуск всех", callback_data="slot_resume")])
    kb.append([InlineKeyboardButton(text="◀️ Назад", callback_data="menu_main")])
    return InlineKeyboardMarkup(inline_keyboard=kb)


# ─── MENU TEXT ──────────────────────────────────────────────────

MAIN_MENU_TEXT = (
    "🏠 **Главное меню**\n\n"
    "Выбери действие:"
)


# ─── FSM ────────────────────────────────────────────────────────

class EditState(StatesGroup):
    waiting_value = State()


# ─── COMMAND HANDLERS ──────────────────────────────────────────

@router.message(Command("start"))
async def cmd_start(message: types.Message):
    if not _is_vadim(message.from_user.id):
        return
    await message.answer(MAIN_MENU_TEXT, reply_markup=main_menu_kb())


@router.message(Command("data"))
async def cmd_data(message: types.Message):
    if not _is_vadim(message.from_user.id):
        return
    data = load_data()
    report = format_report(data)
    await message.answer(report, reply_markup=back_kb("menu_main"))


@router.message(Command("edit"))
async def cmd_edit(message: types.Message):
    if not _is_vadim(message.from_user.id):
        return
    data = load_data()
    await message.answer(
        "✏️ **Редактирование данных**\n\nНажми на категорию, чтобы изменить её значение.",
        reply_markup=edit_kb(data),
    )


@router.message(Command("send"))
async def cmd_send(message: types.Message):
    if not _is_vadim(message.from_user.id):
        return
    data = load_data()
    if not has_sales(data):
        await message.answer(
            "❌ Нет данных о продажах. Сначала введи их через /edit.",
            reply_markup=back_kb("menu_main"),
        )
        return
    await message.answer(
        "📤 Отправить отчёт в группу продаж?",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Отправить", callback_data="send_confirm")],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="menu_main")],
        ]),
    )


@router.message(Command("reset"))
async def cmd_reset(message: types.Message):
    if not _is_vadim(message.from_user.id):
        return
    reset_data()
    await message.answer("🔄 Данные сброшены в нули.", reply_markup=back_kb("menu_main"))


@router.message(Command("schedule"))
async def cmd_schedule(message: types.Message):
    if not _is_vadim(message.from_user.id):
        return
    data = load_data()
    await message.answer(
        "⏰ **Расписание отчётов**\n\nНажимай 🔘 чтобы включить/выключить слот.",
        reply_markup=schedule_kb(data),
    )


# ─── MAIN MENU CALLBACKS ───────────────────────────────────────

@router.callback_query(F.data == "menu_main")
async def cb_main_menu(callback: types.CallbackQuery):
    await callback.message.edit_text(MAIN_MENU_TEXT, reply_markup=main_menu_kb())
    await callback.answer()


@router.callback_query(F.data == "menu_data")
async def cb_show_data(callback: types.CallbackQuery):
    data = load_data()
    report = format_report(data)
    await callback.message.edit_text(report, reply_markup=back_kb("menu_main"))
    await callback.answer()


@router.callback_query(F.data == "menu_edit")
async def cb_edit_menu(callback: types.CallbackQuery):
    data = load_data()
    await callback.message.edit_text(
        "✏️ **Редактирование данных**\n\nНажми на категорию, чтобы изменить её значение. Рядом с названием — текущее значение.",
        reply_markup=edit_kb(data),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("edit_val:"))
async def cb_edit_category(callback: types.CallbackQuery, state: FSMContext):
    category = callback.data.split(":", 1)[1]
    data = load_data()
    hint = ""
    for c in data["categories"]:
        if c["name"] == category:
            if c["type"] == "plan_fact":
                hint = f" (план: {c['plan']}, факт: {c['fact']})"
            elif c["type"] == "single":
                hint = f" (тек: {c['value']})"
            elif c["type"] == "status":
                hint = f" (тек: {c['value']})"
            break
    await callback.message.answer(f"✏️ Введи значение для **{category}**{hint}:")
    await state.set_state(EditState.waiting_value)
    await state.update_data(edit_category=category)
    await callback.answer()


@router.callback_query(F.data == "menu_schedule")
async def cb_schedule(callback: types.CallbackQuery):
    data = load_data()
    await callback.message.edit_text(
        "⏰ **Расписание отчётов**\n\nНажимай 🔘 чтобы включить/выключить слот.",
        reply_markup=schedule_kb(data),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("slot_"))
async def cb_toggle_slot(callback: types.CallbackQuery):
    action = callback.data.split("_", 1)[1]
    data = load_data()
    if action == "pause":
        for h in SLOTS:
            set_slot(data, h, False)
    elif action == "resume":
        for h in SLOTS:
            set_slot(data, h, True)
    else:
        op, h = action.split(":", 1)
        if h.isdigit():
            set_slot(data, int(h), op == "enable")
    data = load_data()
    await callback.message.edit_text(
        "⏰ **Расписание отчётов**\n\nНажимай 🔘 чтобы включить/выключить слот.",
        reply_markup=schedule_kb(data),
    )
    await callback.answer()


@router.callback_query(F.data == "menu_reset")
async def cb_reset(callback: types.CallbackQuery):
    reset_data()
    await callback.message.edit_text(
        "🔄 Данные сброшены в нули.",
        reply_markup=back_kb("menu_main"),
    )
    await callback.answer()


@router.callback_query(F.data == "menu_send")
async def cb_send_confirm(callback: types.CallbackQuery):
    data = load_data()
    if not has_sales(data):
        await callback.message.edit_text(
            "❌ Нет данных о продажах. Сначала введи их через ✏️ Править.",
            reply_markup=back_kb("menu_main"),
        )
        await callback.answer()
        return
    await callback.message.edit_text(
        "📤 Отправить отчёт в группу продаж?",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Отправить", callback_data="send_confirm")],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="menu_main")],
        ]),
    )
    await callback.answer()


@router.callback_query(F.data == "send_confirm")
async def cb_send_go(callback: types.CallbackQuery):
    data = load_data()
    report = format_report(data)
    await send_report_to_group(report)
    await callback.message.edit_text(
        "✅ Отчёт отправлен в группу продаж.",
        reply_markup=back_kb("menu_main"),
    )
    await callback.answer()


@router.callback_query(F.data == "noop")
async def cb_noop(callback: types.CallbackQuery):
    await callback.answer()


# ─── TEXT INPUT: editing a category ────────────────────────────

@router.message(EditState.waiting_value)
async def handle_value_input(message: types.Message, state: FSMContext):
    if not _is_vadim(message.from_user.id):
        return
    sd = await state.get_data()
    category = sd.get("edit_category")
    if not category:
        await state.clear()
        return
    raw = message.text.strip()
    value = raw.lower()
    if value in ("закрыт",):
        pass
    elif value in ("0", ""):
        value = 0
    else:
        try:
            value = int(raw)
        except ValueError:
            value = raw
    result = update_category(load_data(), category, value)
    await message.answer(result)
    data = load_data()
    await message.answer(
        "✏️ **Редактирование данных** — выбери следующую категорию или нажми ✅ Готово:",
        reply_markup=edit_kb(data),
    )
    await state.clear()


# ─── SCHEDULER ──────────────────────────────────────────────────

async def notify_vadim(hour: int):
    if not bot:
        return
    data = load_data()
    emoji = {12: "☀️", 15: "⏰", 18: "⏰", 19: "🌆"}
    e = emoji.get(hour, "⏰")
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Ввести данные", callback_data="menu_edit")],
        [InlineKeyboardButton(text="📊 Текущий отчёт", callback_data="menu_data")],
    ])
    text = (
        f"{e} Через 45 мин отчёт в **{hour}:00**.\n"
        f"Нажми ✏️ чтобы добавить продажи:"
    )
    try:
        await bot.send_message(VADIM_ID, text, reply_markup=kb)
    except Exception as e:
        logger.error(f"Failed to notify Vadim: {e}")


async def send_report_to_group(report_text: str):
    if not bot:
        return
    try:
        await bot.send_message(SALES_GROUP_ID, report_text)
        logger.info("Report sent to sales group")
    except Exception as e:
        logger.error(f"Failed to send report: {e}")


async def reminder_job(hour: int):
    data = load_data()
    key = str(hour)
    if not data["slots"].get(key, {}).get("enabled", False):
        logger.info(f"Slot {hour}: disabled, skipping reminder")
        return
    await notify_vadim(hour)


async def report_job(hour: int):
    data = load_data()
    key = str(hour)
    if not data["slots"].get(key, {}).get("enabled", False):
        logger.info(f"Slot {hour}: disabled, skipping report")
        return
    if not has_sales(data):
        logger.info(f"Slot {hour}: no sales data, skipping report")
        return
    report = format_report(data)
    await send_report_to_group(report)


async def reset_job_func():
    tz = ZoneInfo(TIMEZONE)
    today = datetime.now(tz).strftime("%Y-%m-%d")
    data = load_data()
    if data.get("last_reset_date") == today:
        logger.info("Already reset today, skipping")
        return
    reset_data()
    data = load_data()
    data["last_reset_date"] = today
    save_data(data)
    logger.info(f"Data reset for {today}")


def setup_scheduler():
    scheduler.add_job(
        reset_job_func,
        CronTrigger(hour=11, minute=0, timezone=TIMEZONE),
        id="reset_daily",
        replace_existing=True,
        name="Ежедневный сброс",
    )
    for hour in SLOTS:
        total_min = hour * 60 - REMINDER_OFFSET_MINUTES
        rem_hour = total_min // 60
        rem_min = total_min % 60
        scheduler.add_job(
            reminder_job,
            CronTrigger(hour=rem_hour, minute=rem_min, timezone=TIMEZONE),
            args=[hour],
            id=f"remind_{hour}",
            replace_existing=True,
            name=f"Напоминание {hour}:00",
        )
        scheduler.add_job(
            report_job,
            CronTrigger(hour=hour, minute=0, timezone=TIMEZONE),
            args=[hour],
            id=f"report_{hour}",
            replace_existing=True,
            name=f"Отчёт {hour}:00",
        )
    scheduler.start()
    logger.info(f"Scheduler started: {len(SLOTS) * 2 + 1} jobs")


# ─── SET COMMANDS ──────────────────────────────────────────────

async def set_commands():
    global bot
    cmds = [
        BotCommand(command="start", description="🏠 Главное меню"),
        BotCommand(command="data", description="📊 Текущие данные"),
        BotCommand(command="edit", description="✏️ Править категорию"),
        BotCommand(command="send", description="📤 Отправить отчёт"),
        BotCommand(command="reset", description="🔄 Сбросить данные"),
        BotCommand(command="schedule", description="⏰ Расписание отчётов"),
    ]
    scopes = [
        ("Default", BotCommandScopeDefault()),
        ("All groups", BotCommandScopeAllGroupChats()),
        ("Sales group", BotCommandScopeChat(chat_id=SALES_GROUP_ID)),
        ("Vadim", BotCommandScopeChat(chat_id=VADIM_ID)),
    ]
    for name, scope in scopes:
        try:
            await bot.set_my_commands(cmds, scope=scope)
            logger.info(f"Commands set for scope: {name}")
        except Exception as e:
            logger.error(f"Failed set_my_commands for {name}: {e}")


# ─── MAIN ──────────────────────────────────────────────────────

async def main():
    global bot, router

    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN),
    )
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)

    await set_commands()
    setup_scheduler()

    logger.info("Bot started. Polling...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped.")
