import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "7074124522:AAGDj_9mv1acF0snCP_jrSMP29UZpV31OAk")
VADIM_ID = int(os.getenv("VADIM_ID", "1025948006"))
SALES_GROUP_ID = int(os.getenv("SALES_GROUP_ID", "-4876944974"))
REPORT_FILE = os.getenv("REPORT_FILE", "data.json")
TIMEZONE = os.getenv("TIMEZONE", "Europe/Moscow")

# Слоты расписания (МСК)
SLOTS = [12, 15, 18, 19]
REMINDER_OFFSET_MINUTES = 45