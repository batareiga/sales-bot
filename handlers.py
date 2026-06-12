import logging
from aiogram import Router, F, types
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from config import SLOTS, VADIM_ID
from data_manager import load_data, update_category, get_editable_categories, format_report, \
    reset_data as do_reset, set_slot, save_data
from scheduler import slot_status_text

logger = logging.getLogger(__name__)

router = Router()


# ─── FSM ──────────────────────────────────────────────────
class EditState(StatesGroup):
    waiting_value = State()


# ─── HELPERS ──────────────────────────────────────────────
def _is_vadim(user_id: int) -> bool:
    return user_id == VADIM_ID


def _category_keyboard(data: dict, prefix: str = "edit") -> InlineKeyboardMarkup:
    """Клавиатура со всеми редактируемыми категориями."""
    cats = get_editable_categories(data)
    kb = []
    for i in range(0, len(cats), 3):
        row = []
        for c in cats[i:i + 3]:
            row.append(InlineKeyboardButton(
                text=c["name"],
                callback_data=f"{prefix}:{c['name']}"
            ))
        kb.append(row)
    kb.append([InlineKeyboardButton(text="✅ Готово", callback_data=f"{prefix}_done")])
    return InlineKeyboardMarkup(inline_keyboard=kb)


async def send_reminder_keyboard(bot, chat_id: int, hour: int):
    """Отправить напоминание с клавиатурой."""
    data = load_data()
    emoji = {12: "☀️", 15: "⏰", 18: "⏰", 19: "🌆"}
    e = emoji.get(hour, "⏰")
    text = (
        f"{e} Через 45 мин отчёт в **{hour}:00**.\n"
        f"Введи данные по продажам — нажми на категорию:"
    )
    await bot.send_message(
        chat_id,
        text,
        reply_markup=_category_keyboard(data),
    )


# ─── COMMANDS ─────────────────────────────────────────────

@router.message(Command("start"))
async def cmd_start(message: types.Message):
    if not _is_vadim(message.from_user.id):
        return
    await message.answer(
        "👋 Привет! Я бот отчётов по продажам.\n\n"
        "Команды:\n"
        "`/cron` — статус расписания\n"
        "`/cron enable 12` — включить слот 12:00\n"
        "`/cron disable 18` — выключить слот\n"
        "`/cron pause` — стоп всем\n"
        "`/cron resume` — запустить всем\n"
        "`/data` — текущий отчёт\n"
        "`/reset` — сбросить данные\n"
        "`/send` — отправить отчёт сейчас\n"
        "`/edit` — открыть клавиатуру редактирования\n"
    )


@router.message(Command("data"))
async def cmd_data(message: types.Message):
    if not _is_vadim(message.from_user.id):
        return
    data = load_data()
    report = format_report(data)
    await message.answer(report)


@router.message(Command("reset"))
async def cmd_reset(message: types.Message):
    if not _is_vadim(message.from_user.id):
        return
    do_reset()
    await message.answer("✅ Данные сброшены в нули.")


@router.message(Command("send"))
async def cmd_send(message: types.Message):
    if not _is_vadim(message.from_user.id):
        return
    from scheduler import send_report as sr
    from data_manager import has_sales
    data = load_data()
    if not has_sales(data):
        await message.answer("❌ Нет продаж — отправлять нечего.")
        return
    report = format_report(data)
    await sr(report)
    await message.answer("✅ Отчёт отправлен в группу продаж.")


@router.message(Command("edit"))
async def cmd_edit(message: types.Message):
    if not _is_vadim(message.from_user.id):
        return
    data = load_data()
    await message.answer(
        "Выбери категорию для редактирования:",
        reply_markup=_category_keyboard(data),
    )


@router.message(Command("cron"))
async def cmd_cron(message: types.Message, command: CommandObject):
    if not _is_vadim(message.from_user.id):
        return
    args = command.args or ""
    parts = args.strip().split()
    data = load_data()

    if not parts:
        await message.answer(slot_status_text(data))
        return

    action = parts[0].lower()

    if action == "list":
        await message.answer(slot_status_text(data))

    elif action == "enable" and len(parts) > 1:
        h = parts[1]
        if h.isdigit() and int(h) in SLOTS:
            set_slot(data, int(h), True)
            await message.answer(f"🟢 Слот **{h}:00** включён.")
        else:
            await message.answer(f"❌ Некорректный час. Доступны: {', '.join(map(str, SLOTS))}")

    elif action == "disable" and len(parts) > 1:
        h = parts[1]
        if h.isdigit() and int(h) in SLOTS:
            set_slot(data, int(h), False)
            await message.answer(f"🔴 Слот **{h}:00** выключен.")
        else:
            await message.answer(f"❌ Некорректный час. Доступны: {', '.join(map(str, SLOTS))}")

    elif action == "pause":
        for h in SLOTS:
            set_slot(data, h, False)
        await message.answer("⏸ Все слоты выключены.")

    elif action == "resume":
        for h in SLOTS:
            set_slot(data, h, True)
        await message.answer("▶️ Все слоты включены.")

    else:
        await message.answer(slot_status_text(data))


# ─── CALLBACKS (inline keyboard) ─────────────────────────

@router.callback_query(F.data.startswith("edit:"))
async def cb_edit_category(callback: types.CallbackQuery, state: FSMContext):
    category = callback.data.split(":", 1)[1]
    data = load_data()

    # Найти категорию для подсказки
    hint = ""
    for c in data["categories"]:
        if c["name"] == category:
            if c["type"] == "plan_fact":
                hint = f" (план: {c['plan']})"
            break

    await callback.message.answer(f"Введи сумму для **{category}**{hint}:")
    await state.set_state(EditState.waiting_value)
    await state.update_data(edit_category=category)
    await callback.answer()


@router.callback_query(F.data == "edit_done")
async def cb_edit_done(callback: types.CallbackQuery):
    await callback.message.answer("✅ Готово. Данные сохранены.")
    await callback.answer()


# ─── TEXT: ввод значения ──────────────────────────────────

@router.message(EditState.waiting_value)
async def handle_value_input(message: types.Message, state: FSMContext):
    if not _is_vadim(message.from_user.id):
        return
    data = await state.get_data()
    category = data.get("edit_category")
    if not category:
        await state.clear()
        return

    value = message.text.strip().lower()
    # Специальные значения для статусов
    if value in ("закрыт", "0", ""):
        value = 0 if value == "0" else value

    result = update_category(load_data(), category, value)
    await message.answer(result)

    # Показать клавиатуру снова
    data = load_data()
    await message.answer(
        "Можешь продолжить или закончить:",
        reply_markup=_category_keyboard(data),
    )
    await state.clear()