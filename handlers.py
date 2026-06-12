import logging
from aiogram import Router, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from config import SLOTS, VADIM_ID
from data_manager import load_data, update_category, get_editable_categories, format_report, \
    reset_data as do_reset, set_slot, has_sales
from scheduler import send_report

logger = logging.getLogger(__name__)

router = Router()


# ─── FSM ──────────────────────────────────────────────────
class EditState(StatesGroup):
    waiting_value = State()
    edit_from_menu = State()  # True if we should return to edit menu after input


# ─── GUARD ─────────────────────────────────────────────────
def _is_vadim(user_id: int) -> bool:
    return user_id == VADIM_ID


# ─── KEYBOARDS ────────────────────────────────────────────

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
            # Show current value in button text for plan_fact
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
            InlineKeyboardButton(text=f"{icon} {h}:00", callback_data=f"noop"),
            InlineKeyboardButton(text="🔘", callback_data=f"slot_{action}:{h}"),
        ])
    # Pause/Resume all
    any_on = any(data["slots"].get(str(h), {}).get("enabled", False) for h in SLOTS)
    if any_on:
        kb.append([InlineKeyboardButton(text="⏸ Пауза всех", callback_data="slot_pause")])
    else:
        kb.append([InlineKeyboardButton(text="▶️ Запуск всех", callback_data="slot_resume")])
    kb.append([InlineKeyboardButton(text="◀️ Назад", callback_data="menu_main")])
    return InlineKeyboardMarkup(inline_keyboard=kb)


# ─── MENU TEXT ────────────────────────────────────────────

MAIN_MENU_TEXT = (
    "🏠 **Главное меню**\n\n"
    "Выбери действие:"
)


# ─── COMMANDS ─────────────────────────────────────────────

@router.message(Command("start"))
async def cmd_start(message: types.Message):
    if not _is_vadim(message.from_user.id):
        return
    await message.answer(MAIN_MENU_TEXT, reply_markup=main_menu_kb())


# ─── MAIN MENU CALLBACKS ──────────────────────────────────

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
    await state.update_data(edit_category=category, return_to_edit=True)
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
    do_reset()
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
    await send_report(report)
    await callback.message.edit_text(
        "✅ Отчёт отправлен в группу продаж.",
        reply_markup=back_kb("menu_main"),
    )
    await callback.answer()


# ─── NO-OP (for non-interactive buttons) ──────────────────

@router.callback_query(F.data == "noop")
async def cb_noop(callback: types.CallbackQuery):
    await callback.answer()


# ─── TEXT INPUT: editing a category value ─────────────────

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
        pass  # keep as string
    elif value in ("0", ""):
        value = 0
    else:
        try:
            value = int(raw)
        except ValueError:
            value = raw

    result = update_category(load_data(), category, value)
    await message.answer(result)

    # Return to edit menu
    data = load_data()
    await message.answer(
        "✏️ **Редактирование данных** — выбери следующую категорию или нажми ✅ Готово:",
        reply_markup=edit_kb(data),
    )
    await state.clear()


# ─── REMINDER (called from scheduler) ─────────────────────

async def send_reminder_keyboard(bot, chat_id: int, hour: int):
    """Send reminder with inline edit button to Vadim."""
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
    await bot.send_message(chat_id, text, reply_markup=kb)
