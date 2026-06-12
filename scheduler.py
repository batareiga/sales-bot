import logging
from datetime import datetime
from zoneinfo import ZoneInfo
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from config import SLOTS, REMINDER_OFFSET_MINUTES, TIMEZONE, VADIM_ID, SALES_GROUP_ID
from data_manager import load_data, reset_data as do_reset, format_report, has_sales, save_data

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler(timezone=TIMEZONE)
_bot_ref = None  # set by setup_scheduler


def _get_bot():
    return _bot_ref


async def notify_vadim(hour: int):
    """Напомнить Вадиму в личку."""
    from handlers import send_reminder_keyboard
    bot = _get_bot()
    if not bot:
        return
    try:
        await send_reminder_keyboard(bot, VADIM_ID, hour)
    except Exception as e:
        logger.error(f"Failed to remind Vadim: {e}")


async def send_report(report_text: str):
    """Отправить отчёт в группу продаж."""
    bot = _get_bot()
    if not bot:
        return
    try:
        await bot.send_message(SALES_GROUP_ID, report_text)
        logger.info(f"Report sent to sales group")
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
    await send_report(report)


async def reset_job():
    tz = ZoneInfo(TIMEZONE)
    today = datetime.now(tz).strftime("%Y-%m-%d")
    data = load_data()
    if data.get("last_reset_date") == today:
        logger.info("Already reset today, skipping")
        return
    do_reset()
    data = load_data()
    data["last_reset_date"] = today
    save_data(data)
    logger.info(f"Data reset for {today}")


def setup_scheduler(bot):
    """Привязать бота и запустить все задачи."""
    global _bot_ref
    _bot_ref = bot

    tz = TIMEZONE

    scheduler.add_job(
        reset_job,
        CronTrigger(hour=11, minute=0, timezone=tz),
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
            CronTrigger(hour=rem_hour, minute=rem_min, timezone=tz),
            args=[hour],
            id=f"remind_{hour}",
            replace_existing=True,
            name=f"Напоминание {hour}:00",
        )
        scheduler.add_job(
            report_job,
            CronTrigger(hour=hour, minute=0, timezone=tz),
            args=[hour],
            id=f"report_{hour}",
            replace_existing=True,
            name=f"Отчёт {hour}:00",
        )

    scheduler.start()
    logger.info(f"Scheduler started: {len(SLOTS) * 2 + 1} jobs")


def slot_status_text(data: dict) -> str:
    """Красивый текст статуса всех слотов."""
    lines = ["⏰ **Состояние кронов:**", ""]
    for h in SLOTS:
        key = str(h)
        enabled = data["slots"].get(key, {}).get("enabled", False)
        status = "🟢 Вкл" if enabled else "🔴 Выкл"
        lines.append(f"  • **{h}:00** — {status}")
    lines.append("")
    lines.append("`/cron enable N` — включить")
    lines.append("`/cron disable N` — выключить")
    lines.append("`/cron pause` — выкл все")
    lines.append("`/cron resume` — вкл все")
    return "\n".join(lines)