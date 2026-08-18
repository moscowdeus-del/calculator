"""
БОТ «ИНЖИНИРИНГ БИЗНЕСА»
Версия 15.1 — 50+ КАЛЬКУЛЯТОРОВ + ДАШБОРД + ВИЗУАЛИЗАЦИЯ (БЕЗ ВРЕМЕННЫХ ФАЙЛОВ)
"""

import os
import json
import logging
import re
import sqlite3
from datetime import datetime, timedelta
from functools import wraps
from io import BytesIO

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

# ===================================================================
# 1. КОНФИГУРАЦИЯ
# ===================================================================

BOT_TOKEN = os.environ.get("BOT_TOKEN", "8776638172:AAEmRGbK7ctQ9uc0OJmPdYCoDWv-cxDvXR0")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "6011810304"))
CHANNEL_ID = os.environ.get("CHANNEL_ID", "-1004391759838")
CHANNEL_LINK = os.environ.get("CHANNEL_LINK", "https://t.me/old_stoic")
SITE_LINK = os.environ.get("SITE_LINK", "https://optimasystemc.tilda.ws/")
CONTACT_LINK = os.environ.get("CONTACT_LINK", "@deus_s")

TOUCH_2_DELAY = int(os.environ.get("TOUCH_2_DELAY", "2"))
TOUCH_3_DELAY = int(os.environ.get("TOUCH_3_DELAY", "5"))
TOUCH_4_DELAY = int(os.environ.get("TOUCH_4_DELAY", "10"))

DB_NAME = "business_bot.db"

# ========== НАСТРОЙКА ЛОГИРОВАНИЯ ==========
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ===================================================================
# 2. ПРОВЕРКА БИБЛИОТЕК ВИЗУАЛИЗАЦИИ
# ===================================================================

VISUALIZATION_AVAILABLE = False
try:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import seaborn as sns
    import numpy as np
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import letter
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, Table, TableStyle
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib import colors
    from reportlab.lib.units import inch
    from reportlab.lib.utils import ImageReader
    VISUALIZATION_AVAILABLE = True
    logger.info("✅ Библиотеки визуализации загружены")
except ImportError as e:
    logger.warning(f"⚠️ Библиотеки визуализации не установлены: {e}")
    logger.warning("⚠️ Для работы графиков и PDF установите: pip install matplotlib seaborn numpy reportlab pillow")

# ===================================================================
# 3. БАЗА ДАННЫХ
# ===================================================================

def get_db():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            first_name TEXT,
            last_name TEXT,
            username TEXT,
            phone TEXT,
            email TEXT,
            subscribed INTEGER DEFAULT 0,
            first_contact TEXT,
            calc_counter INTEGER DEFAULT 0,
            touch_2_sent INTEGER DEFAULT 0,
            touch_3_sent INTEGER DEFAULT 0,
            touch_4_sent INTEGER DEFAULT 0,
            status TEXT DEFAULT 'active'
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS states (
            user_id INTEGER PRIMARY KEY,
            state TEXT,
            data TEXT
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS contacts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            first_name TEXT,
            last_name TEXT,
            phone TEXT,
            email TEXT,
            source TEXT,
            created_at TEXT
        )
    ''')

    conn.commit()
    conn.close()
    logger.info("База данных инициализирована")

def get_user(user_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    user = cursor.fetchone()
    conn.close()
    return dict(user) if user else None

def create_user(user_id, first_name, last_name=None, username=None):
    conn = get_db()
    cursor = conn.cursor()
    now = datetime.now().isoformat()
    cursor.execute('''
        INSERT OR IGNORE INTO users (user_id, first_name, last_name, username, first_contact, status)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (user_id, first_name, last_name, username, now, 'active'))
    conn.commit()
    conn.close()

def update_user(user_id, **kwargs):
    conn = get_db()
    cursor = conn.cursor()
    fields = []
    values = []
    for key, value in kwargs.items():
        fields.append(f"{key} = ?")
        values.append(value)
    values.append(user_id)
    cursor.execute(f"UPDATE users SET {', '.join(fields)} WHERE user_id = ?", values)
    conn.commit()
    conn.close()

def get_state(user_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT state, data FROM states WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return row['state'], json.loads(row['data']) if row['data'] else {}
    return None, {}

def set_state(user_id, state, data=None):
    conn = get_db()
    cursor = conn.cursor()
    data_json = json.dumps(data) if data else '{}'
    cursor.execute('''
        INSERT OR REPLACE INTO states (user_id, state, data)
        VALUES (?, ?, ?)
    ''', (user_id, state, data_json))
    conn.commit()
    conn.close()

def clear_state(user_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM states WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

def save_contact(user_id, first_name, last_name=None, phone=None, email=None, source='telegram'):
    conn = get_db()
    cursor = conn.cursor()
    now = datetime.now().isoformat()
    cursor.execute('''
        INSERT INTO contacts (user_id, first_name, last_name, phone, email, source, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (user_id, first_name, last_name, phone, email, source, now))
    conn.commit()
    conn.close()

def increment_calc_counter(user_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET calc_counter = calc_counter + 1 WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

def get_active_users():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE status = 'active'")
    users = cursor.fetchall()
    conn.close()
    return [dict(u) for u in users]

def get_all_users_stats():
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) FROM users")
    total = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM users WHERE status = 'active'")
    active = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM users WHERE phone IS NOT NULL AND phone != ''")
    with_phone = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM users WHERE email IS NOT NULL AND email != ''")
    with_email = cursor.fetchone()[0]
    
    cursor.execute("SELECT SUM(calc_counter) FROM users")
    total_calcs = cursor.fetchone()[0] or 0
    
    conn.close()
    
    return {
        'total': total,
        'active': active,
        'with_phone': with_phone,
        'with_email': with_email,
        'total_calcs': total_calcs
    }

# ===================================================================
# 4. ТЕКСТЫ
# ===================================================================

def welcome_text(first_name):
    return f"""Здравствуйте! 👋 Меня зовут Георгий.

Я помогаю собственникам МСБ наводить порядок в бизнесе.

Здесь я собрал для вас бесплатные калькуляторы — они помогут быстро оценить ключевые показатели вашего бизнеса.

🔒 Чтобы получить доступ ко всем калькуляторам, подпишитесь на мой канал:
👉 {CHANNEL_LINK}

✅ После подписки нажмите кнопку ниже."""

def after_subscribe_text():
    return """Отлично! Вы подписаны ✅

Теперь вам доступны все калькуляторы.

Выберите отдел, который хотите проверить:"""

def calc_result_text(name, value, interpretation, advice, problems=None):
    text = f"""📊 {name}: {value}

📈 Что это значит: {interpretation}

💡 Как улучшить:
{advice}"""
    
    if problems:
        text += f"""

⚠️ Частые проблемы:
{problems}"""
    
    text += f"""

🔄 Попробуйте другой калькулятор или вернитесь в меню.

🌐 Подробнее: {SITE_LINK}"""
    
    return text

def touch_2_text():
    return f"""Привет! Это Георгий 👋

Вы недавно пользовались калькуляторами. Как вам результаты?

На моём сайте я собрал подробные разборы каждого показателя:
🌐 {SITE_LINK}"""

def touch_3_text():
    return f"""Здравствуйте! Это снова Георгий.

Хочу поделиться с вами реальным кейсом из моей практики.

---
📂 Кейс: Производственная компания (МСБ, 45 сотрудников)

**Результат за 3 месяца:**
✔ Прибыль выросла на 34%
✔ Собственник перестал участвовать в каждой планерке
✔ Появилась система

---
💡 На моём сайте ещё 20 разборов: {SITE_LINK}"""

def touch_4_text():
    return f"""Привет! Это Георгий.

Это последнее сообщение от меня. Хочу оставить вам гайд.

---
📘 Гайд «Как навести порядок в бизнесе за 30 дней»

**Как получить?** Поделитесь контактом или оставьте email.

---
🌐 Сайт: {SITE_LINK}
📱 Контакты: {CONTACT_LINK}"""

def guide_sent_text(name):
    return f"""Спасибо, {name}! Гайд отправлен вам в чат ниже 📥

📌 Сайт: {SITE_LINK}
📌 Контакты: {CONTACT_LINK}

До встречи!"""

def email_prompt():
    return "Введите ваш email:"

def email_sent_text(email):
    return f"""Спасибо! Гайд отправлен на {email} 📥

📌 Сайт: {SITE_LINK}
📌 Контакты: {CONTACT_LINK}

До встречи!"""

# ===================================================================
# 5. КЛАВИАТУРЫ
# ===================================================================

def get_start_keyboard():
    keyboard = [
        [InlineKeyboardButton("📢 Подписаться", url=CHANNEL_LINK)],
        [InlineKeyboardButton("✅ Проверить подписку", callback_data="check_sub")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_main_menu_with_dashboard():
    """Главное меню с дашбордом и админ-панелью"""
    keyboard = [
        [InlineKeyboardButton("📊 Финансы и учёт", callback_data="menu_finance")],
        [InlineKeyboardButton("📈 Маркетинг", callback_data="menu_marketing")],
        [InlineKeyboardButton("💰 Продажи", callback_data="menu_sales")],
        [InlineKeyboardButton("📦 Логистика и склад", callback_data="menu_logistics")],
        [InlineKeyboardButton("👥 Персонал и HR", callback_data="menu_hr")],
        [InlineKeyboardButton("🏭 Производство", callback_data="menu_production")],
        [InlineKeyboardButton("📱 IT и автоматизация", callback_data="menu_it")],
        [InlineKeyboardButton("📋 Управление проектами", callback_data="menu_management")],
        [InlineKeyboardButton("⚖️ Юридический", callback_data="menu_legal")],
        [InlineKeyboardButton("📊 Управленческий дашборд", callback_data="menu_dashboard")],
        [InlineKeyboardButton("⚙️ Админ-панель", callback_data="admin_panel")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_admin_menu():
    keyboard = [
        [InlineKeyboardButton("📊 Статистика", callback_data="admin_stats")],
        [InlineKeyboardButton("📋 Список пользователей", callback_data="admin_users")],
        [InlineKeyboardButton("📤 Экспорт контактов", callback_data="admin_export")],
        [InlineKeyboardButton("🔙 Назад", callback_data="back_to_menu")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_calc_list_keyboard(calc_list):
    """Генерация клавиатуры со списком калькуляторов"""
    keyboard = []
    for item in calc_list:
        if isinstance(item, tuple) and len(item) == 2:
            key, calc_data = item
            calc_name = calc_data.get('name', str(key))
            keyboard.append([InlineKeyboardButton(str(calc_name), callback_data=f"calc_{str(key)}")])
    keyboard.append([InlineKeyboardButton("🏠 В главное меню", callback_data="back_to_menu")])
    return InlineKeyboardMarkup(keyboard)

def get_calc_input_keyboard():
    keyboard = [[InlineKeyboardButton("🔙 Отмена", callback_data="cancel_calc")]]
    return InlineKeyboardMarkup(keyboard)

def get_after_calc_keyboard():
    keyboard = [
        [InlineKeyboardButton("🔄 Другой калькулятор", callback_data="back_to_category")],
        [InlineKeyboardButton("🏠 В меню", callback_data="back_to_menu")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_contact_keyboard():
    keyboard = [
        [InlineKeyboardButton("📱 Поделиться контактом", callback_data="request_contact")],
        [InlineKeyboardButton("✉️ Оставить email", callback_data="request_email")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_contact_request_keyboard():
    keyboard = [[KeyboardButton("📱 Отправить контакт", request_contact=True)]]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)

def get_dashboard_list_keyboard():
    """Клавиатура со списком дашбордов"""
    keyboard = []
    for key, info in DASHBOARD_CALCS.items():
        keyboard.append([InlineKeyboardButton(f"📊 {info['name']}", callback_data=f"dash_{key}")])
    keyboard.append([InlineKeyboardButton("🏠 В главное меню", callback_data="back_to_menu")])
    return InlineKeyboardMarkup(keyboard)

def get_dashboard_action_keyboard():
    """Клавиатура действий с дашбордом"""
    keyboard = [
        [InlineKeyboardButton("📊 Показать график", callback_data="dash_chart")],
        [InlineKeyboardButton("📄 Скачать PDF-отчёт", callback_data="dash_pdf")],
        [InlineKeyboardButton("🔄 Новый расчёт", callback_data="dash_new")],
        [InlineKeyboardButton("🏠 В меню", callback_data="back_to_menu")]
    ]
    return InlineKeyboardMarkup(keyboard)

# ===================================================================
# 6. КАЛЬКУЛЯТОРЫ (50+ ШТУК)
# ===================================================================

# ===== 6.1. ФИНАНСЫ И УЧЁТ - 9 =====
FINANCE_CALCS = {
    "net_profit": {
        "name": "Чистая прибыль",
        "inputs": ["Выручка (руб)", "Расходы (руб)", "Налоги (руб)"],
        "formula": "a - b - c",
        "interpretation": "Сколько денег остаётся после всех расходов и налогов. Главный показатель здоровья бизнеса.",
        "advice": "1. Посчитайте маржинальность каждого продукта\n2. Сократите неэффективные расходы\n3. Пересмотрите ценообразование",
        "problems": "❌ Расходы растут быстрее выручки\n❌ Нет контроля над себестоимостью\n❌ Налоговая нагрузка завышена"
    },
    "margin": {
        "name": "Маржинальность",
        "inputs": ["Выручка (руб)", "Себестоимость (руб)"],
        "formula": "((a - b) / a) * 100",
        "interpretation": "Сколько процентов от выручки остаётся после покрытия себестоимости. Чем выше, тем лучше.",
        "advice": "1. Повышайте цены на 5-10%\n2. Снижайте закупочные цены\n3. Оптимизируйте производственные процессы",
        "problems": "❌ Маржинальность ниже 20% — бизнес уязвим\n❌ Нет контроля закупочных цен\n❌ Себестоимость растёт быстрее цен"
    },
    "roe": {
        "name": "Рентабельность капитала (ROE)",
        "inputs": ["Чистая прибыль (руб)", "Собственный капитал (руб)"],
        "formula": "(a / b) * 100",
        "interpretation": "Сколько прибыли приносит каждый рубль, вложенный собственником в бизнес.",
        "advice": "1. Увеличьте чистую прибыль\n2. Оптимизируйте структуру капитала\n3. Выводите неиспользуемые средства",
        "problems": "❌ Капитал работает неэффективно\n❌ Нет дивидендной политики\n❌ Избыток денег на счетах"
    },
    "roa": {
        "name": "Рентабельность активов (ROA)",
        "inputs": ["Чистая прибыль (руб)", "Активы (руб)"],
        "formula": "(a / b) * 100",
        "interpretation": "Сколько прибыли приносит каждый рубль, вложенный в активы компании.",
        "advice": "1. Продайте неиспользуемые активы\n2. Увеличьте загрузку оборудования\n3. Пересмотрите инвестиции",
        "problems": "❌ Активы простаивают\n❌ Много неликвидных запасов\n❌ Инвестиции не приносят отдачи"
    },
    "bep": {
        "name": "Точка безубыточности",
        "inputs": ["Постоянные расходы (руб/мес)", "Цена за единицу (руб)", "Себестоимость единицы (руб)"],
        "formula": "a / (b - c)",
        "interpretation": "Сколько единиц товара нужно продать, чтобы покрыть все расходы. Ниже этой цифры — убыток.",
        "advice": "1. Повысьте цену за единицу на 5-10%\n2. Снизьте себестоимость единицы\n3. Сократите постоянные расходы",
        "problems": "❌ Постоянные расходы слишком высоки\n❌ Цена ниже себестоимости\n❌ Маржинальность меньше 20%"
    },
    "roi": {
        "name": "Рентабельность инвестиций (ROI)",
        "inputs": ["Прибыль от инвестиций (руб)", "Сумма инвестиций (руб)"],
        "formula": "(a / b) * 100",
        "interpretation": "Сколько процентов приносят вложенные инвестиции. ROI > 30% — отличный результат.",
        "advice": "1. Рассчитывайте ROI до начала инвестиций\n2. Инвестируйте только с ROI > 30%\n3. Сравнивайте ROI разных проектов",
        "problems": "❌ Инвестиции не окупаются\n❌ Нет расчёта окупаемости\n❌ Деньги вложены неэффективно"
    },
    "cash_flow": {
        "name": "Денежный поток (FCF)",
        "inputs": ["Поступления денег (руб)", "Платежи (руб)"],
        "formula": "a - b",
        "interpretation": "Положительный — бизнес генерирует деньги. Отрицательный — бизнес сжигает деньги.",
        "advice": "1. Ускорьте сбор дебиторки\n2. Договоритесь об отсрочке с поставщиками\n3. Сократите складские запасы",
        "problems": "❌ Деньги заморожены в дебиторке\n❌ Нет прогноза денежных потоков\n❌ Склады переполнены"
    },
    "ebitda": {
        "name": "Операционная прибыль (EBITDA)",
        "inputs": ["Чистая прибыль (руб)", "Проценты по кредитам (руб)", "Налоги (руб)", "Амортизация (руб)"],
        "formula": "a + b + c + d",
        "interpretation": "Прибыль до вычета процентов, налогов и амортизации. Показывает операционную эффективность.",
        "advice": "1. Оптимизируйте операционные расходы\n2. Внедрите управленческий учёт\n3. Повысьте эффективность процессов",
        "problems": "❌ Нет понимания операционной прибыли\n❌ Нет управленческого учёта\n❌ Смешение операционных и финансовых расходов"
    },
    "autonomy": {
        "name": "Финансовая независимость",
        "inputs": ["Собственный капитал (руб)", "Активы (руб)"],
        "formula": "(a / b) * 100",
        "interpretation": "Чем выше показатель, тем меньше зависимость от кредиторов. Норма — выше 50%.",
        "advice": "1. Наращивайте собственный капитал\n2. Сокращайте кредитную нагрузку\n3. Рефинансируйте дорогие кредиты",
        "problems": "❌ Высокая долговая нагрузка\n❌ Зависимость от займов\n❌ Нет финансовой подушки"
    }
}

# ===== 6.2. МАРКЕТИНГ - 6 =====
MARKETING_CALCS = {
    "cac": {
        "name": "Стоимость привлечения клиента (CAC)",
        "inputs": ["Расходы на маркетинг (руб)", "Новые клиенты"],
        "formula": "a / b",
        "interpretation": "Сколько денег вы тратите на привлечение одного нового клиента.",
        "advice": "1. Сократите неэффективные каналы\n2. Увеличьте конверсию\n3. Настройте реферальную программу",
        "problems": "❌ CAC выше LTV\n❌ Нет аналитики по каналам\n❌ Деньги уходят в неэффективные каналы"
    },
    "ltv": {
        "name": "Пожизненная ценность клиента (LTV)",
        "inputs": ["Средний чек (руб)", "Покупок в год", "Срок жизни клиента (лет)"],
        "formula": "a * b * c",
        "interpretation": "Сколько денег приносит один клиент за всё время сотрудничества.",
        "advice": "1. Увеличьте средний чек через апсейл\n2. Внедрите программу лояльности\n3. Работайте с возражениями",
        "problems": "❌ Клиенты уходят быстро\n❌ Нет программы лояльности\n❌ Не используется апсейл"
    },
    "romi": {
        "name": "Окупаемость маркетинга (ROMI)",
        "inputs": ["Доход от маркетинга (руб)", "Расходы на маркетинг (руб)"],
        "formula": "((a - b) / b) * 100",
        "interpretation": "Сколько процентов приносит каждый рубль, вложенный в маркетинг. ROMI > 200% — отлично.",
        "advice": "1. Проанализируйте каждый канал\n2. Отключите неэффективные каналы\n3. Увеличьте бюджет на топ-каналы",
        "problems": "❌ Маркетинг работает в минус\n❌ Бюджет распределён хаотично\n❌ Нет аналитики по каналам"
    },
    "conversion": {
        "name": "Конверсия",
        "inputs": ["Покупки/заявки", "Посетители/лиды"],
        "formula": "(a / b) * 100",
        "interpretation": "Какой процент посетителей становится клиентами. Чем выше, тем эффективнее воронка.",
        "advice": "1. Проверьте юзабилити сайта\n2. Улучшите оффер\n3. Настройте ретаргетинг",
        "problems": "❌ Низкая конверсия на всех этапах\n❌ Сложный путь клиента\n❌ Плохой оффер"
    },
    "cpl": {
        "name": "Стоимость лида (CPL)",
        "inputs": ["Расходы на маркетинг (руб)", "Количество лидов"],
        "formula": "a / b",
        "interpretation": "Сколько стоит привлечение одного потенциального клиента (лида).",
        "advice": "1. Оптимизируйте рекламные кампании\n2. Улучшите качество трафика\n3. Настройте таргетинг",
        "problems": "❌ CPL слишком высокий\n❌ Много нецелевых лидов\n❌ Реклама не окупается"
    },
    "churn": {
        "name": "Отток клиентов",
        "inputs": ["Ушедшие клиенты", "Всего клиентов на начало периода"],
        "formula": "(a / b) * 100",
        "interpretation": "Какой процент клиентов уходит за период. Чем ниже, тем лучше.",
        "advice": "1. Проведите опросы уходящих клиентов\n2. Улучшите качество обслуживания\n3. Внедрите программу возврата",
        "problems": "❌ Клиенты массово уходят\n❌ Нет работы с оттоками\n❌ Низкое качество обслуживания"
    }
}

# ===== 6.3. ПРОДАЖИ - 6 =====
SALES_CALCS = {
    "closure": {
        "name": "Коэффициент закрытия сделок",
        "inputs": ["Выигранные сделки", "Все сделки"],
        "formula": "(a / b) * 100",
        "interpretation": "Какой процент сделок ваши менеджеры выигрывают. Норма — от 30%.",
        "advice": "1. Проверьте квалификацию лидов\n2. Обучите менеджеров продажам\n3. Анализируйте проигранные сделки",
        "problems": "❌ Менеджеры не закрывают сделки\n❌ Нет скриптов продаж\n❌ Плохая квалификация лидов"
    },
    "avg_check": {
        "name": "Средний чек",
        "inputs": ["Выручка (руб)", "Количество транзакций"],
        "formula": "a / b",
        "interpretation": "Средняя сумма одной покупки. Ключевой драйвер роста прибыли.",
        "advice": "1. Предлагайте дополнительные товары\n2. Внедрите систему скидок за сумму\n3. Используйте апсейл и кросс-сейл",
        "problems": "❌ Нет системы апсейла\n❌ Клиенты уходят после первой покупки\n❌ Цены ниже рыночных"
    },
    "pipeline": {
        "name": "Скорость сделки",
        "inputs": ["Сделок в воронке", "Среднее время закрытия (дней)", "Конверсия (%)"],
        "formula": "a * b / (c / 100)",
        "interpretation": "Средняя скорость прохождения сделок по воронке. Показывает загрузку менеджеров.",
        "advice": "1. Ускорьте обработку лидов\n2. Внедрите CRM-систему\n3. Автоматизируйте рутинные задачи",
        "problems": "❌ Сделки затягиваются\n❌ Нет CRM-системы\n❌ Много «висящих» сделок"
    },
    "win_ratio": {
        "name": "Соотношение побед и поражений",
        "inputs": ["Выигранные сделки", "Проигранные сделки"],
        "formula": "a / b",
        "interpretation": "Сколько выигранных сделок приходится на одну проигранную.",
        "advice": "1. Анализируйте причины проигрышей\n2. Улучшайте презентации\n3. Работайте с возражениями",
        "problems": "❌ Слишком много проигранных сделок\n❌ Нет анализа проигрышей\n❌ Слабые презентации"
    },
    "sales_cost": {
        "name": "Себестоимость продажи",
        "inputs": ["Расходы отдела продаж (руб)", "Количество сделок"],
        "formula": "a / b",
        "interpretation": "Сколько рублей тратится на одну закрытую сделку с учётом всех расходов отдела.",
        "advice": "1. Оптимизируйте расходы отдела\n2. Повысьте эффективность менеджеров\n3. Автоматизируйте процессы",
        "problems": "❌ Расходы на продажи растут\n❌ Низкая эффективность менеджеров\n❌ Нет контроля бюджета отдела"
    },
    "crm_rate": {
        "name": "Заполнение CRM",
        "inputs": ["Заполненные карточки", "Всего карточек"],
        "formula": "(a / b) * 100",
        "interpretation": "Какой процент данных внесён в CRM. Чем выше, тем больше контроля.",
        "advice": "1. Внедрите обязательное заполнение\n2. Мотивируйте менеджеров\n3. Проводите проверки",
        "problems": "❌ CRM пустая\n❌ Нет контроля заполнения\n❌ Менеджеры саботируют"
    }
}

# ===== 6.4. ЛОГИСТИКА И СКЛАД - 6 =====
LOGISTICS_CALCS = {
    "turnover": {
        "name": "Оборачиваемость запасов",
        "inputs": ["Себестоимость проданных товаров (руб/год)", "Средние запасы (руб)"],
        "formula": "a / b",
        "interpretation": "Сколько раз за год ваши запасы полностью оборачиваются. Чем выше, тем лучше.",
        "advice": "1. Проведите ABC-анализ\n2. Сократите заказы по медленным товарам\n3. Используйте систему «точно в срок»",
        "problems": "❌ Много залежалого товара\n❌ Деньги заморожены на складе\n❌ Нет системы управления запасами"
    },
    "turnover_days": {
        "name": "Длительность оборота запасов",
        "inputs": ["Оборачиваемость (раз в год)"],
        "formula": "365 / a",
        "interpretation": "Сколько дней в среднем товар лежит на складе. Чем меньше, тем лучше.",
        "advice": "1. Заменяйте медленные товары\n2. Проводите акции на залежавшийся товар\n3. Настройте авто-заказ по остаткам",
        "problems": "❌ Товар лежит месяцами\n❌ Нет прогноза спроса\n❌ Закупки без анализа"
    },
    "fill_rate": {
        "name": "Выполнение заказов",
        "inputs": ["Заказы выполненные полностью", "Все заказы"],
        "formula": "(a / b) * 100",
        "interpretation": "Какой процент заказов выполняется полностью. Норма — выше 95%.",
        "advice": "1. Оптимизируйте поставки\n2. Внедрите страховой запас\n3. Наладьте отношения с поставщиками",
        "problems": "❌ Постоянные недопоставки\n❌ Проблемы с поставщиками\n❌ Нет страхового запаса"
    },
    "warehouse_cost": {
        "name": "Стоимость хранения 1 единицы",
        "inputs": ["Расходы на склад (руб/мес)", "Количество единиц на складе"],
        "formula": "a / b",
        "interpretation": "Сколько стоит хранение одной единицы товара в месяц.",
        "advice": "1. Оптимизируйте площадь склада\n2. Внедрите систему адресного хранения\n3. Автоматизируйте учёт",
        "problems": "❌ Склад переполнен\n❌ Высокая арендная плата\n❌ Нет системы учёта"
    },
    "delivery_time": {
        "name": "Среднее время доставки",
        "inputs": ["Общее время доставки (дней)", "Количество заказов"],
        "formula": "a / b",
        "interpretation": "Среднее время доставки одного заказа. Чем меньше, тем лучше для клиентов.",
        "advice": "1. Оптимизируйте маршруты\n2. Внедрите систему отслеживания\n3. Работайте над скоростью",
        "problems": "❌ Долгая доставка\n❌ Нет системы отслеживания\n❌ Проблемы с логистикой"
    },
    "return_rate": {
        "name": "Возвраты товаров",
        "inputs": ["Возвращённые товары", "Всего проданных товаров"],
        "formula": "(a / b) * 100",
        "interpretation": "Какой процент товаров возвращают клиенты. Норма — до 5%.",
        "advice": "1. Улучшите качество товаров\n2. Проверяйте товары перед отгрузкой\n3. Работайте с рекламациями",
        "problems": "❌ Много возвратов\n❌ Проблемы с качеством\n❌ Нет работы с рекламациями"
    }
}

# ===== 6.5. ПЕРСОНАЛ И HR - 7 =====
HR_CALCS = {
    "employee_turnover": {
        "name": "Текучесть кадров",
        "inputs": ["Уволенные сотрудники", "Среднесписочная численность"],
        "formula": "(a / b) * 100",
        "interpretation": "Какой процент сотрудников покидает компанию. Норма — до 15%.",
        "advice": "1. Проведите exit-интервью\n2. Внедрите прозрачную мотивацию\n3. Проверьте адаптацию новичков",
        "problems": "❌ Сотрудники массово уходят\n❌ Плохая адаптация\n❌ Нет системы мотивации"
    },
    "productivity": {
        "name": "Производительность труда",
        "inputs": ["Выручка (руб)", "Количество сотрудников"],
        "formula": "a / b",
        "interpretation": "Сколько выручки приносит один сотрудник в год.",
        "advice": "1. Автоматизируйте ручные процессы\n2. Внедрите KPI\n3. Обучайте сотрудников",
        "problems": "❌ Низкая эффективность\n❌ Много ручного труда\n❌ Нет системы KPI"
    },
    "staff_cost": {
        "name": "Доля ФОТ в выручке",
        "inputs": ["Фонд оплаты труда (руб)", "Выручка (руб)"],
        "formula": "(a / b) * 100",
        "interpretation": "Какой процент выручки уходит на зарплаты. Норма — 20-30%.",
        "advice": "1. Оптимизируйте штат\n2. Внедрите систему мотивации\n3. Автоматизируйте процессы",
        "problems": "❌ ФОТ съедает прибыль\n❌ Штат неоптимален\n❌ Нет системы мотивации"
    },
    "hour_cost": {
        "name": "Стоимость часа работы",
        "inputs": ["Зарплата (руб/мес)", "Рабочих дней в месяце"],
        "formula": "a / (b * 8)",
        "interpretation": "Сколько стоит один час работы сотрудника с учётом всех налогов.",
        "advice": "1. Оцените эффективность задач\n2. Делегируйте низкоприоритетные задачи\n3. Оптимизируйте процессы",
        "problems": "❌ Сотрудники занимаются не своей работой\n❌ Нет делегирования\n❌ Нет оценки эффективности"
    },
    "training_roi": {
        "name": "Окупаемость обучения",
        "inputs": ["Прирост выручки после обучения (руб)", "Затраты на обучение (руб)"],
        "formula": "(a / b) * 100",
        "interpretation": "Сколько процентов приносит каждый рубль, вложенный в обучение сотрудников.",
        "advice": "1. Измеряйте результаты обучения\n2. Обучайте только ключевых сотрудников\n3. Внедрите наставничество",
        "problems": "❌ Обучение не приносит результата\n❌ Обучение для галочки\n❌ Нет оценки эффективности"
    },
    "absenteeism": {
        "name": "Прогулы и больничные",
        "inputs": ["Пропущенные дни", "Всего рабочих дней"],
        "formula": "(a / b) * 100",
        "interpretation": "Какой процент рабочего времени теряется из-за прогулов и больничных.",
        "advice": "1. Внедрите мотивацию посещаемости\n2. Улучшите условия труда\n3. Проведите опросы",
        "problems": "❌ Частые больничные\n❌ Плохие условия труда\n❌ Нет мотивации"
    },
    "engagement": {
        "name": "Вовлечённость сотрудников",
        "inputs": ["Удовлетворённые сотрудники", "Всего сотрудников"],
        "formula": "(a / b) * 100",
        "interpretation": "Какой процент сотрудников вовлечён в работу. Норма — выше 70%.",
        "advice": "1. Проводите опросы\n2. Внедрите систему мотивации\n3. Развивайте корпоративную культуру",
        "problems": "❌ Низкая вовлечённость\n❌ Сотрудники работают без энтузиазма\n❌ Нет обратной связи"
    }
}

# ===== 6.6. ПРОИЗВОДСТВО - 6 =====
PRODUCTION_CALCS = {
    "oee": {
        "name": "Эффективность оборудования (OEE)",
        "inputs": ["Доступность оборудования (%)", "Производительность (%)", "Качество (%)"],
        "formula": "(a / 100) * (b / 100) * (c / 100) * 100",
        "interpretation": "Насколько эффективно используется оборудование. Мировой стандарт — OEE > 85%.",
        "advice": "1. Сократите простои\n2. Уменьшите брак\n3. Повысьте производительность",
        "problems": "❌ Частые простои оборудования\n❌ Много брака\n❌ Низкая производительность"
    },
    "defect_rate": {
        "name": "Процент брака",
        "inputs": ["Бракованные единицы", "Всего произведено"],
        "formula": "(a / b) * 100",
        "interpretation": "Какой процент продукции бракуется. Норма — до 3%.",
        "advice": "1. Внедрите контроль качества\n2. Обновите оборудование\n3. Обучите персонал",
        "problems": "❌ Много бракованной продукции\n❌ Нет системы контроля качества\n❌ Оборудование устарело"
    },
    "capacity": {
        "name": "Загрузка мощностей",
        "inputs": ["Фактический объём производства", "Максимальная мощность"],
        "formula": "(a / b) * 100",
        "interpretation": "Какой процент производственных мощностей используется. Норма — 80-90%.",
        "advice": "1. Увеличьте загрузку\n2. Диверсифицируйте производство\n3. Сократите простои",
        "problems": "❌ Мощности простаивают\n❌ Неэффективное планирование\n❌ Нет заказов"
    },
    "downtime": {
        "name": "Простои оборудования",
        "inputs": ["Время простоев (часы)", "Общее рабочее время (часы)"],
        "formula": "(a / b) * 100",
        "interpretation": "Какой процент времени оборудование простаивает. Норма — до 10%.",
        "advice": "1. Внедрите систему ТОиР\n2. Улучшите планирование\n3. Обучите операторов",
        "problems": "❌ Частые поломки\n❌ Нет профилактики\n❌ Неквалифицированные операторы"
    },
    "cycle_time": {
        "name": "Время производственного цикла",
        "inputs": ["Время производства заказа (дней)"],
        "formula": "a",
        "interpretation": "Сколько дней занимает производство одного заказа. Чем меньше, тем лучше.",
        "advice": "1. Оптимизируйте процесс\n2. Сократите переналадку\n3. Внедрите бережливое производство",
        "problems": "❌ Долгое производство\n❌ Частые переналадки\n❌ Нет стандартизации"
    },
    "scrap_rate": {
        "name": "Потери материалов",
        "inputs": ["Потерянные материалы (руб)", "Всего материалов (руб)"],
        "formula": "(a / b) * 100",
        "interpretation": "Какой процент материалов теряется при производстве. Норма — до 5%.",
        "advice": "1. Оптимизируйте раскрой\n2. Обучите персонал\n3. Внедрите систему учёта",
        "problems": "❌ Большие потери материалов\n❌ Нет контроля расхода\n❌ Неквалифицированный персонал"
    }
}

# ===== 6.7. IT И АВТОМАТИЗАЦИЯ - 5 =====
IT_CALCS = {
    "automation_roi": {
        "name": "ROI автоматизации",
        "inputs": ["Экономия от автоматизации (руб/год)", "Затраты на внедрение (руб)"],
        "formula": "(a / b) * 100",
        "interpretation": "Сколько процентов приносит каждый рубль, вложенный в автоматизацию.",
        "advice": "1. Автоматизируйте самые болезненные процессы\n2. Обучите персонал\n3. Начинайте с малого",
        "problems": "❌ Автоматизация не окупается\n❌ Сотрудники сопротивляются\n❌ Нет расчёта TCO"
    },
    "implementation_time": {
        "name": "Время внедрения системы",
        "inputs": ["Объём работ (человеко-месяцев)", "Количество исполнителей"],
        "formula": "a / b",
        "interpretation": "Сколько месяцев займёт внедрение системы автоматизации.",
        "advice": "1. Правильно оценивайте объём\n2. Используйте Agile\n3. Вовлекайте бизнес-экспертов",
        "problems": "❌ Внедрение затягивается\n❌ Нет чёткого плана\n❌ Сотрудники не обучены"
    },
    "tco": {
        "name": "Совокупная стоимость владения (TCO)",
        "inputs": ["Внедрение (руб)", "Поддержка в год (руб)", "Срок использования (лет)"],
        "formula": "a + b * c",
        "interpretation": "Общие затраты на систему за весь срок использования.",
        "advice": "1. Учитывайте все затраты\n2. Сравнивайте разные системы\n3. Планируйте обновления",
        "problems": "❌ Не учтены скрытые затраты\n❌ Нет бюджета на поддержку\n❌ Система требует доработок"
    },
    "digital_maturity": {
        "name": "Цифровая зрелость",
        "inputs": ["Автоматизированные процессы", "Всего процессов"],
        "formula": "(a / b) * 100",
        "interpretation": "Какой процент бизнес-процессов автоматизирован.",
        "advice": "1. Проведите аудит процессов\n2. Составьте дорожную карту\n3. Внедряйте поэтапно",
        "problems": "❌ Низкая цифровизация\n❌ Нет стратегии\n❌ Сотрудники не используют системы"
    },
    "it_budget": {
        "name": "Доля IT-бюджета",
        "inputs": ["IT-бюджет (руб)", "Выручка (руб)"],
        "formula": "(a / b) * 100",
        "interpretation": "Какой процент выручки тратится на IT. Норма — 3-5%.",
        "advice": "1. Оптимизируйте IT-расходы\n2. Инвестируйте в развитие\n3. Внедрите управление IT",
        "problems": "❌ IT-бюджет неэффективен\n❌ Нет стратегии развития\n❌ Переплата за софт"
    }
}

# ===== 6.8. УПРАВЛЕНИЕ ПРОЕКТАМИ - 5 =====
MANAGEMENT_CALCS = {
    "spi": {
        "name": "Выполнение сроков (SPI)",
        "inputs": ["Фактический объём работ", "Запланированный объём"],
        "formula": "a / b",
        "interpretation": "SPI > 1 — проекты быстрее плана. SPI < 1 — проекты отстают от плана.",
        "advice": "1. Корректируйте план\n2. Ускорьте критические задачи\n3. Сократите бюрократию",
        "problems": "❌ Постоянное отставание от плана\n❌ Нет управления рисками\n❌ Плохое планирование"
    },
    "cpi": {
        "name": "Выполнение бюджета (CPI)",
        "inputs": ["Фактический бюджет", "Запланированный бюджет"],
        "formula": "a / b",
        "interpretation": "CPI > 1 — перерасход бюджета. CPI < 1 — экономия бюджета.",
        "advice": "1. Контролируйте бюджет\n2. Пересматривайте сметы\n3. Сокращайте неэффективные расходы",
        "problems": "❌ Постоянный перерасход бюджета\n❌ Плохая смета\n❌ Нет контроля затрат"
    },
    "project_success": {
        "name": "Успешность проектов",
        "inputs": ["Успешные проекты", "Всего проектов"],
        "formula": "(a / b) * 100",
        "interpretation": "Какой процент проектов завершается успешно. Норма — выше 80%.",
        "advice": "1. Внедрите проектное управление\n2. Собирайте уроки из ошибок\n3. Обучите менеджеров",
        "problems": "❌ Много провальных проектов\n❌ Нет методологии\n❌ Нет проектного офиса"
    },
    "risk_score": {
        "name": "Индекс рисков проекта",
        "inputs": ["Выявленные риски", "Реализовавшиеся риски"],
        "formula": "(a / b) * 100",
        "interpretation": "Какой процент выявленных рисков реализуется. Чем ниже, тем лучше.",
        "advice": "1. Улучшите управление рисками\n2. Создайте реестр рисков\n3. Регулярно проводите анализ",
        "problems": "❌ Риски не управляются\n❌ Реагирование по факту\n❌ Нет реестра рисков"
    },
    "schedule_variance": {
        "name": "Отклонение от графика",
        "inputs": ["Отклонение (дней)", "Плановая длительность (дней)"],
        "formula": "(a / b) * 100",
        "interpretation": "На сколько процентов проект отклоняется от графика. Норма — до 10%.",
        "advice": "1. Добавьте буфер времени\n2. Ускорьте критические задачи\n3. Пересмотрите план",
        "problems": "❌ Постоянные задержки\n❌ Плохое планирование\n❌ Нет буфера времени"
    }
}

# ===== 6.9. ЮРИДИЧЕСКИЙ - 4 =====
LEGAL_CALCS = {
    "contract_risk": {
        "name": "Юридические риски по договорам",
        "inputs": ["Спорные договоры", "Всего договоров"],
        "formula": "(a / b) * 100",
        "interpretation": "Какой процент договоров содержит потенциальные юридические риски.",
        "advice": "1. Внедрите стандартные шаблоны\n2. Проводите юридический аудит\n3. Обучите менеджеров",
        "problems": "❌ Много споров по договорам\n❌ Нет стандартных шаблонов\n❌ Менеджеры не знают рисков"
    },
    "legal_claims": {
        "name": "Судебная нагрузка",
        "inputs": ["Судебные дела", "Выручка (руб)"],
        "formula": "a / (b / 1000000)",
        "interpretation": "Сколько судебных дел приходится на 1 миллион рублей выручки.",
        "advice": "1. Внедрите досудебное урегулирование\n2. Проведите аудит рисков\n3. Наймите юриста",
        "problems": "❌ Много судебных дел\n❌ Нет досудебной работы\n❌ Отсутствует юрзащита"
    },
    "compliance": {
        "name": "Соблюдение требований",
        "inputs": ["Нарушения", "Проверки"],
        "formula": "100 - (a / b) * 100",
        "interpretation": "Какой процент требований законодательства соблюдается. Норма — выше 90%.",
        "advice": "1. Внедрите систему контроля\n2. Проводите внутренние аудиты\n3. Обучайте сотрудников",
        "problems": "❌ Штрафы и санкции\n❌ Нет системы контроля\n❌ Сотрудники не знают требований"
    },
    "contract_efficiency": {
        "name": "Эффективность договорной работы",
        "inputs": ["Заключённые договоры", "Одобренные юристом"],
        "formula": "(a / b) * 100",
        "interpretation": "Какой процент договоров проходит юридическую проверку.",
        "advice": "1. Внедрите систему согласования\n2. Создайте шаблоны\n3. Обучите менеджеров",
        "problems": "❌ Договоры без проверки\n❌ Нет системы согласования\n❌ Много правок от юриста"
    }
}

# ===================================================================
# 7. ОБЪЕДИНЕНИЕ ВСЕХ КАЛЬКУЛЯТОРОВ
# ===================================================================

def get_calc_groups():
    groups = {
        "finance": list(FINANCE_CALCS.items()),
        "marketing": list(MARKETING_CALCS.items()),
        "sales": list(SALES_CALCS.items()),
        "logistics": list(LOGISTICS_CALCS.items()),
        "hr": list(HR_CALCS.items()),
        "production": list(PRODUCTION_CALCS.items()),
        "it": list(IT_CALCS.items()),
        "management": list(MANAGEMENT_CALCS.items()),
        "legal": list(LEGAL_CALCS.items())
    }
    return groups

def get_calc_info(calc_key):
    all_calcs = {}
    all_calcs.update(FINANCE_CALCS)
    all_calcs.update(MARKETING_CALCS)
    all_calcs.update(SALES_CALCS)
    all_calcs.update(LOGISTICS_CALCS)
    all_calcs.update(HR_CALCS)
    all_calcs.update(PRODUCTION_CALCS)
    all_calcs.update(IT_CALCS)
    all_calcs.update(MANAGEMENT_CALCS)
    all_calcs.update(LEGAL_CALCS)
    return all_calcs.get(calc_key)

def calculate(formula_key, inputs):
    try:
        names = ["a", "b", "c", "d", "e"]
        local_vars = {}
        for i, val in enumerate(inputs):
            local_vars[names[i]] = float(val)
        info = get_calc_info(formula_key)
        if not info:
            return None
        result = eval(info["formula"], {}, local_vars)
        if result % 1 == 0:
            return int(result)
        else:
            return round(result, 2)
    except:
        return None

# ===================================================================
# 8. ДАШБОРД И ВИЗУАЛИЗАЦИЯ
# ===================================================================

# ===== 8.1. ДАШБОРД-КАЛЬКУЛЯТОРЫ =====

DASHBOARD_CALCS = {
    "financial_health": {
        "name": "Финансовое здоровье бизнеса",
        "description": "Оценка финансовой устойчивости и эффективности",
        "inputs": [
            "Выручка (руб/год)",
            "Себестоимость (руб/год)",
            "Операционные расходы (руб/год)",
            "Активы (руб)",
            "Обязательства (руб)",
            "Собственный капитал (руб)"
        ],
        "category": "finance"
    },
    "business_efficiency": {
        "name": "Эффективность бизнес-процессов",
        "description": "Оценка операционной эффективности компании",
        "inputs": [
            "Выручка (руб/год)",
            "Чистая прибыль (руб/год)",
            "Кол-во сотрудников",
            "Кол-во клиентов активных",
            "Операционные расходы (руб/год)"
        ],
        "category": "management"
    },
    "marketing_performance": {
        "name": "Маркетинговая эффективность",
        "description": "Анализ окупаемости маркетинговых инвестиций",
        "inputs": [
            "Бюджет маркетинга (руб/мес)",
            "Новые клиенты в месяц",
            "Средний чек (руб)",
            "Маржинальность (%)",
            "Количество лидов в месяц"
        ],
        "category": "marketing"
    },
    "hr_metrics": {
        "name": "HR-метрики и управление персоналом",
        "description": "Анализ эффективности работы с персоналом",
        "inputs": [
            "ФОТ (руб/мес)",
            "Кол-во сотрудников",
            "Выручка (руб/мес)",
            "Кол-во уволившихся за год",
            "Средняя зарплата по рынку (руб/мес)"
        ],
        "category": "hr"
    }
}

def calculate_dashboard(dash_key, inputs):
    """
    Расчёт комплексных показателей для дашборда
    Используются проверенные бизнес-формулы
    """
    try:
        # Конвертируем все входные данные в числа
        values = [float(x) for x in inputs]
        
        if dash_key == "financial_health":
            # Финансовое здоровье - проверенные формулы
            revenue, cost_of_goods, operating_expenses, assets, liabilities, equity = values[:6]
            
            # Валовая прибыль
            gross_profit = revenue - cost_of_goods
            gross_margin = (gross_profit / revenue) * 100 if revenue > 0 else 0
            
            # Операционная прибыль (EBIT)
            ebit = gross_profit - operating_expenses
            ebit_margin = (ebit / revenue) * 100 if revenue > 0 else 0
            
            # Чистая прибыль (приблизительно)
            net_profit = ebit * 0.8  # Примерный налог 20%
            net_margin = (net_profit / revenue) * 100 if revenue > 0 else 0
            
            # Рентабельность активов (ROA)
            roa = (net_profit / assets) * 100 if assets > 0 else 0
            
            # Рентабельность капитала (ROE)
            roe = (net_profit / equity) * 100 if equity > 0 else 0
            
            # Коэффициент автономии (финансовая независимость)
            autonomy_ratio = (equity / assets) * 100 if assets > 0 else 0
            
            # Текущая ликвидность (упрощённо)
            current_ratio = (assets / liabilities) if liabilities > 0 else 0
            
            # Оценка финансового здоровья
            score = 0
            if gross_margin > 40: score += 1
            if net_margin > 10: score += 1
            if roe > 15: score += 1
            if autonomy_ratio > 50: score += 1
            if current_ratio > 1.5: score += 1
            
            if score >= 4:
                rating = "Отлично 🟢"
            elif score >= 3:
                rating = "Хорошо 🟡"
            else:
                rating = "Требует внимания 🔴"
            
            return {
                "Валовая маржинальность": f"{gross_margin:.1f}%",
                "Операционная маржинальность": f"{ebit_margin:.1f}%",
                "Чистая маржинальность": f"{net_margin:.1f}%",
                "ROA (рентабельность активов)": f"{roa:.1f}%",
                "ROE (рентабельность капитала)": f"{roe:.1f}%",
                "Финансовая независимость": f"{autonomy_ratio:.1f}%",
                "Текущая ликвидность": f"{current_ratio:.2f}",
                "Общая оценка": rating
            }
        
        elif dash_key == "business_efficiency":
            # Эффективность бизнес-процессов
            revenue, net_profit, employees, clients, operating_expenses = values[:5]
            
            # Производительность труда
            revenue_per_employee = revenue / employees if employees > 0 else 0
            profit_per_employee = net_profit / employees if employees > 0 else 0
            
            # Выручка на клиента
            revenue_per_client = revenue / clients if clients > 0 else 0
            
            # Операционная эффективность
            opex_ratio = (operating_expenses / revenue) * 100 if revenue > 0 else 0
            
            # Маржинальность
            margin = (net_profit / revenue) * 100 if revenue > 0 else 0
            
            # Оценка эффективности
            score = 0
            if revenue_per_employee > 5000000: score += 1  # >5 млн на сотрудника
            if profit_per_employee > 500000: score += 1    # >500 тыс прибыли
            if opex_ratio < 30: score += 1                 # расходы < 30%
            if margin > 15: score += 1                     # маржинальность > 15%
            if revenue_per_client > 100000: score += 1     # >100 тыс на клиента
            
            if score >= 4:
                rating = "Высокая 🟢"
            elif score >= 3:
                rating = "Средняя 🟡"
            else:
                rating = "Низкая 🔴"
            
            return {
                "Выручка на сотрудника": f"{revenue_per_employee:,.0f} руб.",
                "Прибыль на сотрудника": f"{profit_per_employee:,.0f} руб.",
                "Выручка на клиента": f"{revenue_per_client:,.0f} руб.",
                "Доля операционных расходов": f"{opex_ratio:.1f}%",
                "Маржинальность": f"{margin:.1f}%",
                "Эффективность": rating
            }
        
        elif dash_key == "marketing_performance":
            # Маркетинговая эффективность
            budget, new_clients, avg_check, margin_pct, leads = values[:5]
            
            # CAC - Cost of Customer Acquisition
            cac = budget / new_clients if new_clients > 0 else 0
            
            # LTV - Lifetime Value (упрощённо)
            # Предполагаем, что клиент совершает 3 покупки в год и живёт 2 года
            ltv = avg_check * 3 * 2 * (margin_pct / 100)
            
            # ROMI - Return on Marketing Investment
            revenue_from_marketing = new_clients * avg_check
            romi = ((revenue_from_marketing - budget) / budget) * 100 if budget > 0 else 0
            
            # Конверсия из лида в клиента
            conversion_rate = (new_clients / leads) * 100 if leads > 0 else 0
            
            # Соотношение LTV/CAC
            ltv_cac_ratio = ltv / cac if cac > 0 else 0
            
            # Оценка маркетинга
            score = 0
            if romi > 200: score += 1
            if ltv_cac_ratio > 3: score += 1  # Золотое правило маркетинга
            if conversion_rate > 10: score += 1
            if cac < avg_check * 0.3: score += 1
            
            if score >= 3:
                rating = "Отлично 🟢"
            elif score >= 2:
                rating = "Хорошо 🟡"
            else:
                rating = "Требует внимания 🔴"
            
            return {
                "CAC (стоимость привлечения)": f"{cac:,.0f} руб.",
                "LTV (пожизненная ценность)": f"{ltv:,.0f} руб.",
                "ROMI (окупаемость)": f"{romi:.1f}%",
                "LTV/CAC": f"{ltv_cac_ratio:.2f}",
                "Конверсия в клиента": f"{conversion_rate:.1f}%",
                "Оценка маркетинга": rating
            }
        
        elif dash_key == "hr_metrics":
            # HR-метрики
            payroll, employees, revenue, annual_turnover, market_salary = values[:5]
            
            # Средняя зарплата
            avg_salary = payroll / employees if employees > 0 else 0
            
            # Производительность труда
            revenue_per_employee = revenue / employees if employees > 0 else 0
            
            # Доля ФОТ в выручке
            payroll_ratio = (payroll / revenue) * 100 if revenue > 0 else 0
            
            # Коэффициент текучести (годовой)
            turnover_rate = (annual_turnover / employees) * 100 if employees > 0 else 0
            
            # Индекс удовлетворённости зарплатой (относительно рынка)
            salary_index = (avg_salary / market_salary) * 100 if market_salary > 0 else 0
            
            # Оценка HR
            score = 0
            if turnover_rate < 15: score += 1
            if payroll_ratio < 30: score += 1
            if revenue_per_employee > 100000: score += 1
            if salary_index > 100: score += 1
            
            if score >= 3:
                rating = "Отлично 🟢"
            elif score >= 2:
                rating = "Хорошо 🟡"
            else:
                rating = "Требует внимания 🔴"
            
            return {
                "Средняя зарплата": f"{avg_salary:,.0f} руб.",
                "Выручка на сотрудника": f"{revenue_per_employee:,.0f} руб.",
                "Доля ФОТ в выручке": f"{payroll_ratio:.1f}%",
                "Годовая текучесть": f"{turnover_rate:.1f}%",
                "Индекс зарплаты (рынок=100)": f"{salary_index:.1f}%",
                "Оценка HR": rating
            }
        
        return None
        
    except Exception as e:
        logger.error(f"Ошибка расчёта дашборда: {e}")
        return None

# ===== 8.2. ВИЗУАЛИЗАЦИЯ (БЕЗ ВРЕМЕННЫХ ФАЙЛОВ) =====

def create_dashboard_chart(dash_key, results):
    """Создание графиков для дашборда (возвращает BytesIO)"""
    if not VISUALIZATION_AVAILABLE:
        return None
    
    try:
        # Настройка стиля
        sns.set_style("whitegrid")
        sns.set_palette("husl")
        
        fig, axes = plt.subplots(1, 2, figsize=(14, 6), facecolor='white')
        
        # Извлекаем числовые данные
        numeric_data = {}
        labels = []
        values = []
        
        for key, value in results.items():
            if isinstance(value, str):
                numbers = re.findall(r'[\d.]+', value.replace(',', ''))
                if numbers:
                    try:
                        num_val = float(numbers[0])
                        numeric_data[key] = num_val
                        labels.append(key)
                        values.append(num_val)
                    except:
                        pass
            elif isinstance(value, (int, float)):
                numeric_data[key] = value
                labels.append(key)
                values.append(value)
        
        if not numeric_data:
            # Если нет данных, создаём информационный график
            for ax in axes:
                ax.text(0.5, 0.5, 'Нет данных для визуализации', 
                       ha='center', va='center', fontsize=14, transform=ax.transAxes)
                ax.set_xticks([])
                ax.set_yticks([])
            # Сохраняем в BytesIO
            buf = BytesIO()
            fig.savefig(buf, format='png', dpi=150, bbox_inches='tight', facecolor='white')
            buf.seek(0)
            plt.close(fig)
            return buf
        
        # График 1: Столбчатая диаграмма - основные показатели
        ax1 = axes[0]
        
        # Нормализуем значения для наглядности
        max_val = max(values) if values else 1
        normalized = [v/max_val * 100 for v in values]
        
        # Цвета в зависимости от значений
        colors_list = []
        for v in values:
            if v > max_val * 0.7:
                colors_list.append('#2ecc71')  # зелёный
            elif v > max_val * 0.4:
                colors_list.append('#f1c40f')  # жёлтый
            else:
                colors_list.append('#e74c3c')  # красный
        
        bars = ax1.barh(labels[:8], normalized[:8], color=colors_list[:8], 
                       edgecolor='white', linewidth=2)
        ax1.set_xlabel('Относительное значение, %', fontsize=11)
        ax1.set_title('Ключевые показатели', fontsize=14, fontweight='bold')
        
        # Добавляем значения
        for bar, val in zip(bars, values[:8]):
            width = bar.get_width()
            ax1.text(width + 1, bar.get_y() + bar.get_height()/2,
                    f'{val:,.0f}', va='center', fontsize=9)
        
        # График 2: Круговая диаграмма - структура
        ax2 = axes[1]
        
        # Берём первые 5 показателей для круговой диаграммы
        top_labels = labels[:5]
        top_values = values[:5]
        
        if top_values and sum(top_values) > 0:
            # Создаём круговую диаграмму
            wedges, texts, autotexts = ax2.pie(
                top_values, 
                labels=top_labels,
                autopct='%1.1f%%',
                startangle=90,
                colors=sns.color_palette("husl", len(top_values))
            )
            
            # Настройка текста
            for text in texts:
                text.set_fontsize(9)
            for autotext in autotexts:
                autotext.set_color('white')
                autotext.set_fontweight('bold')
                autotext.set_fontsize(10)
            
            ax2.set_title('Структура показателей', fontsize=14, fontweight='bold')
        else:
            ax2.text(0.5, 0.5, 'Недостаточно данных', 
                    ha='center', va='center', fontsize=14, transform=ax2.transAxes)
            ax2.set_xticks([])
            ax2.set_yticks([])
        
        plt.tight_layout()
        
        # Сохраняем в BytesIO
        buf = BytesIO()
        fig.savefig(buf, format='png', dpi=150, bbox_inches='tight', facecolor='white')
        buf.seek(0)
        plt.close(fig)
        return buf
        
    except Exception as e:
        logger.error(f"Ошибка создания графика: {e}")
        return None

def create_dashboard_pdf(results, chart_buf, user_info=None):
    """Создание PDF-отчёта (без временных файлов)"""
    if not VISUALIZATION_AVAILABLE:
        return None
    
    try:
        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter, 
                               rightMargin=72, leftMargin=72,
                               topMargin=72, bottomMargin=18)
        
        styles = getSampleStyleSheet()
        
        # Стили
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=24,
            textColor=colors.HexColor('#2c3e50'),
            alignment=1,
            spaceAfter=30
        )
        
        header_style = ParagraphStyle(
            'CustomHeader',
            parent=styles['Heading2'],
            fontSize=16,
            textColor=colors.HexColor('#34495e'),
            spaceAfter=12
        )
        
        normal_style = ParagraphStyle(
            'CustomNormal',
            parent=styles['Normal'],
            fontSize=11,
            spaceAfter=6
        )
        
        story = []
        
        # Заголовок
        story.append(Paragraph("📊 Управленческий дашборд", title_style))
        if user_info:
            story.append(Paragraph(f"Отчёт для: {user_info}", normal_style))
        story.append(Paragraph(f"Дата формирования: {datetime.now().strftime('%d.%m.%Y %H:%M')}", normal_style))
        story.append(Spacer(1, 20))
        
        # График из BytesIO
        if chart_buf:
            chart_buf.seek(0)
            img_reader = ImageReader(chart_buf)
            img = Image(img_reader, width=6*inch, height=3.5*inch)
            story.append(img)
            story.append(Spacer(1, 20))
        
        # Результаты в таблице
        story.append(Paragraph("📋 Детальный анализ показателей:", header_style))
        
        table_data = [['Показатель', 'Значение', 'Оценка']]
        for key, value in results.items():
            if '🟢' in str(value):
                status = '✅ Отлично'
            elif '🟡' in str(value):
                status = '⚠️ Средне'
            elif '🔴' in str(value):
                status = '❌ Требует внимания'
            else:
                status = '—'
            
            table_data.append([
                Paragraph(key, normal_style), 
                Paragraph(str(value), normal_style),
                Paragraph(status, normal_style)
            ])
        
        table = Table(table_data, colWidths=[2.5*inch, 2*inch, 1.5*inch])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#3498db')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 12),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]))
        
        story.append(table)
        story.append(Spacer(1, 20))
        
        # Рекомендации
        story.append(Paragraph("💡 Рекомендации по улучшению:", header_style))
        
        recommendations = []
        has_issues = False
        
        for key, value in results.items():
            if '🔴' in str(value):
                has_issues = True
                if 'финанс' in key.lower() or 'маржинальность' in key.lower():
                    recommendations.append("• Требуется оптимизация финансовых показателей. Рекомендуется снизить издержки и повысить эффективность.")
                elif 'hr' in key.lower() or 'текучесть' in key.lower():
                    recommendations.append("• Высокая текучесть кадров. Проведите анализ причин увольнений и пересмотрите систему мотивации.")
                elif 'маркетинг' in key.lower() or 'romi' in key.lower():
                    recommendations.append("• Маркетинговые инвестиции неэффективны. Пересмотрите рекламные каналы и проведите A/B-тестирование.")
                else:
                    recommendations.append(f"• {key} требует детального анализа и разработки плана улучшений.")
            elif '🟡' in str(value):
                if recommendations and len(recommendations) < 3:
                    recommendations.append(f"• {key} на среднем уровне. Есть потенциал для роста, рекомендуется провести дополнительный анализ.")
        
        if not has_issues:
            recommendations.append("✅ Все показатели в норме. Рекомендуется поддерживать текущий уровень и искать новые точки роста.")
        
        if not recommendations:
            recommendations.append("• Проведите регулярный мониторинг ключевых показателей.")
        
        for rec in recommendations[:5]:
            story.append(Paragraph(rec, normal_style))
        
        story.append(Spacer(1, 20))
        story.append(Paragraph("📌 Отчёт сгенерирован автоматически. Для более детального анализа обратитесь к специалисту.", 
                              ParagraphStyle('Footer', parent=styles['Normal'], fontSize=9, textColor=colors.grey)))
        
        doc.build(story)
        buffer.seek(0)
        return buffer
        
    except Exception as e:
        logger.error(f"Ошибка создания PDF: {e}")
        return None

# ===================================================================
# 9. MIDDLEWARE ДЛЯ ПРОВЕРКИ ПОДПИСКИ
# ===================================================================

subscription_cache = {}

async def is_subscribed(user_id: int) -> bool:
    if user_id in subscription_cache:
        result, timestamp = subscription_cache[user_id]
        if (datetime.now() - timestamp).seconds < 300:
            return result
    
    try:
        app = Application.builder().token(BOT_TOKEN).build()
        bot = app.bot
        
        member = await bot.get_chat_member(CHANNEL_ID, user_id)
        is_member = member.status in ['member', 'administrator', 'creator']
        
        subscription_cache[user_id] = (is_member, datetime.now())
        
        logger.info(f"Статус подписки для {user_id}: {member.status}")
        return is_member
        
    except Exception as e:
        logger.error(f"Ошибка проверки подписки: {e}")
        if user_id in subscription_cache:
            return subscription_cache[user_id][0]
        return False

# ===================================================================
# 10. ОСНОВНОЙ БОТ
# ===================================================================

init_db()

def send_guide(context, user_id):
    guide_text = """📘 Гайд «Как навести порядок в бизнесе за 30 дней»

Вступление
Меня зовут Георгий. Я помогаю собственникам МСБ наводить порядок в бизнесе.

---
Глава 1. Диагностика хаоса (Дни 1-3)
1. Нарисуйте карту процессов
2. Проведите аудит времени
3. Сделайте финансовый срез

---
Глава 2. Наведение порядка (Дни 4-14)
1. Внедрите управленческий учёт
2. Создайте регламенты
3. Введите KPI

---
Глава 3. Автоматизация (Дни 15-21)
1. Внедрите точки контроля
2. Начните делегировать

---
Глава 4. Устойчивая система (Дни 22-30)
1. Проведите тренинг
2. Закрепите дисциплину

---
Свяжитесь со мной: """ + CONTACT_LINK + """
Сайт: """ + SITE_LINK

    context.bot.send_message(user_id, guide_text, parse_mode=None)

# ===== ОБРАБОТЧИКИ КОМАНД =====

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    first_name = update.effective_user.first_name or "Друг"
    last_name = update.effective_user.last_name
    username = update.effective_user.username

    user = get_user(user_id)
    if not user:
        create_user(user_id, first_name, last_name, username)

    if user_id == ADMIN_ID:
        await update.message.reply_text(
            "👋 Добро пожаловать!",
            reply_markup=get_main_menu_with_dashboard()
        )
        return

    await update.message.reply_text(
        welcome_text(first_name),
        reply_markup=get_start_keyboard(),
        parse_mode=None
    )

async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if user_id == ADMIN_ID:
        await update.message.reply_text(
            "👋 Главное меню:",
            reply_markup=get_main_menu_with_dashboard()
        )
        return
    
    subscribed = await is_subscribed(user_id)
    if not subscribed:
        await update.message.reply_text(
            "⚠️ Подпишитесь на канал:",
            reply_markup=get_start_keyboard()
        )
        return
    
    await update.message.reply_text(
        after_subscribe_text(),
        reply_markup=get_main_menu_with_dashboard(),
        parse_mode=None
    )

# ===== ОБРАБОТЧИКИ КНОПОК =====

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    data = query.data

    # ===== АДМИН-ПАНЕЛЬ =====
    if data == "admin_panel":
        if user_id != ADMIN_ID:
            await query.answer("Нет доступа")
            return
        
        await query.edit_message_text(
            "⚙️ Админ-панель",
            reply_markup=get_admin_menu()
        )
        return

    if data == "admin_stats":
        if user_id != ADMIN_ID:
            await query.answer("Нет доступа")
            return
        
        stats = get_all_users_stats()
        text = f"""📊 Статистика

👥 Всего: {stats['total']}
🟢 Активных: {stats['active']}
📱 С телефоном: {stats['with_phone']}
✉️ С email: {stats['with_email']}
🧮 Расчётов: {stats['total_calcs']}

📅 {datetime.now().strftime('%d.%m.%Y %H:%M')}"""
        
        await query.edit_message_text(text, reply_markup=get_admin_menu(), parse_mode=None)
        return

    if data == "admin_users":
        if user_id != ADMIN_ID:
            await query.answer("Нет доступа")
            return
        
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT user_id, first_name, username, phone, email, calc_counter, first_contact FROM users ORDER BY first_contact DESC LIMIT 20")
        users = cursor.fetchall()
        conn.close()
        
        if not users:
            await query.edit_message_text("📋 Пользователей пока нет", reply_markup=get_admin_menu())
            return
        
        text = "📋 Последние 20 пользователей:\n\n"
        for user in users:
            name = user['first_name'] or "Без имени"
            username = f"@{user['username']}" if user['username'] else "—"
            phone = user['phone'] or "—"
            email = user['email'] or "—"
            calcs = user['calc_counter'] or 0
            date = user['first_contact'][:16] if user['first_contact'] else "—"
            text += f"👤 {name} ({username})\n   📱 {phone} | ✉️ {email}\n   🧮 {calcs} | 📅 {date}\n\n"
        
        await query.edit_message_text(text, reply_markup=get_admin_menu(), parse_mode=None)
        return

    if data == "admin_export":
        if user_id != ADMIN_ID:
            await query.answer("Нет доступа")
            return
        
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT first_name, phone, email, username, created_at FROM contacts ORDER BY created_at DESC")
        contacts = cursor.fetchall()
        conn.close()
        
        if not contacts:
            await query.edit_message_text("📤 Контактов пока нет", reply_markup=get_admin_menu())
            return
        
        csv = "Имя;Телефон;Email;Telegram;Дата\n"
        for c in contacts:
            csv += f"{c['first_name'] or ''};{c['phone'] or ''};{c['email'] or ''};{c['username'] or ''};{c['created_at'] or ''}\n"
        
        await query.edit_message_text("📤 Экспорт готов!", reply_markup=get_admin_menu())
        await context.bot.send_document(
            chat_id=user_id,
            document=('contacts.csv', csv.encode('utf-8-sig')),
            filename='contacts.csv'
        )
        return

    # ===== ПРОВЕРКА ПОДПИСКИ =====
    if data == "check_sub":
        subscribed = await is_subscribed(user_id)
        if subscribed:
            update_user(user_id, subscribed=1)
            try:
                await query.edit_message_text(
                    after_subscribe_text(),
                    reply_markup=get_main_menu_with_dashboard() if user_id == ADMIN_ID else get_main_menu_with_dashboard(),
                    parse_mode=None
                )
            except Exception as e:
                logger.error(f"Ошибка: {e}")
                await query.message.reply_text(
                    after_subscribe_text(),
                    reply_markup=get_main_menu_with_dashboard() if user_id == ADMIN_ID else get_main_menu_with_dashboard(),
                    parse_mode=None
                )
        else:
            await query.answer("❌ Вы не подписаны. Подпишитесь и нажмите 'Проверить' снова.", show_alert=True)
        return

    # ===== ДАШБОРД =====
    if data == "menu_dashboard":
        if not VISUALIZATION_AVAILABLE:
            await query.edit_message_text(
                "📊 **Управленческий дашборд**\n\n"
                "⚠️ **Внимание!** Библиотеки визуализации не установлены.\n\n"
                "Для работы графиков и PDF установите:\n"
                "`pip install matplotlib seaborn numpy reportlab pillow`\n\n"
                "Пока доступен только текстовый расчёт показателей.",
                reply_markup=get_dashboard_list_keyboard(),
                parse_mode="Markdown"
            )
        else:
            await query.edit_message_text(
                "📊 **Управленческий дашборд**\n\n"
                "Выберите тип комплексного анализа. Я покажу ключевые показатели "
                "вашего бизнеса и дам рекомендации.\n\n"
                "Доступны 4 вида анализа:",
                reply_markup=get_dashboard_list_keyboard(),
                parse_mode="Markdown"
            )
        return

    if data.startswith("dash_"):
        dash_key = data.replace("dash_", "")
        info = DASHBOARD_CALCS.get(dash_key)
        if not info:
            await query.answer("Дашборд не найден.")
            return
        
        set_state(user_id, "dash_input", {
            "dash_key": dash_key,
            "inputs": [],
            "step": 0,
            "total": len(info["inputs"])
        })
        
        first_input = info["inputs"][0]
        await query.edit_message_text(
            f"📊 **{info['name']}**\n\n"
            f"_{info['description']}_\n\n"
            f"Введите {first_input}:",
            reply_markup=get_calc_input_keyboard(),
            parse_mode="Markdown"
        )
        return

    if data == "dash_chart":
        if not VISUALIZATION_AVAILABLE:
            await query.answer("❌ Библиотеки визуализации не установлены. Установите: pip install matplotlib seaborn numpy", show_alert=True)
            return
        
        state, state_data = get_state(user_id)
        if "dash_results" not in state_data:
            await query.answer("Сначала выполните расчёт!")
            return
        
        try:
            results = state_data.get("dash_results", {})
            dash_key = state_data.get("dash_key", "financial_health")
            
            # Получаем BytesIO с изображением
            chart_buf = create_dashboard_chart(dash_key, results)
            if not chart_buf:
                await query.answer("❌ Ошибка создания графика")
                return
            
            # Отправляем изображение
            await query.message.reply_photo(
                photo=chart_buf,
                caption="📊 **Визуализация показателей**\n\n_На графике отображены ключевые метрики вашего бизнеса._",
                parse_mode="Markdown"
            )
            chart_buf.close()
            
        except Exception as e:
            logger.error(f"Ошибка: {e}")
            await query.answer(f"❌ Ошибка: {str(e)[:50]}", show_alert=True)
        return

    if data == "dash_pdf":
        if not VISUALIZATION_AVAILABLE:
            await query.answer("❌ Библиотеки для PDF не установлены. Установите: pip install reportlab pillow", show_alert=True)
            return
        
        state, state_data = get_state(user_id)
        if "dash_results" not in state_data:
            await query.answer("Сначала выполните расчёт!")
            return
        
        try:
            results = state_data.get("dash_results", {})
            dash_key = state_data.get("dash_key", "financial_health")
            
            # Создаём график для PDF
            chart_buf = create_dashboard_chart(dash_key, results)
            if not chart_buf:
                await query.answer("❌ Ошибка создания графика")
                return
            
            # Создаём PDF
            pdf_buffer = create_dashboard_pdf(results, chart_buf, user_info=query.from_user.first_name)
            chart_buf.close()
            
            if not pdf_buffer:
                await query.answer("❌ Ошибка создания PDF")
                return
            
            # Отправляем PDF
            await context.bot.send_document(
                chat_id=user_id,
                document=('dashboard_report.pdf', pdf_buffer.getvalue()),
                filename='dashboard_report.pdf',
                caption="📄 **Управленческий отчёт сформирован!**\n\nВ отчёте: график, таблица показателей и рекомендации.",
                parse_mode="Markdown"
            )
            pdf_buffer.close()
            
        except Exception as e:
            logger.error(f"Ошибка: {e}")
            await query.answer(f"❌ Ошибка: {str(e)[:50]}", show_alert=True)
        return

    if data == "dash_new":
        await query.edit_message_text(
            "📊 **Управленческий дашборд**\n\n"
            "Выберите тип комплексного анализа:",
            reply_markup=get_dashboard_list_keyboard(),
            parse_mode="Markdown"
        )
        return

    # ===== Меню =====
    if data.startswith("menu_"):
        category = data.replace("menu_", "")
        calc_list = get_calc_groups().get(category, [])
        if calc_list:
            set_state(user_id, "category", {"category": category})
            await query.edit_message_text(
                "Выберите калькулятор:",
                reply_markup=get_calc_list_keyboard(calc_list)
            )
        else:
            await query.answer("Калькуляторов пока нет в этом разделе.")
        return

    # ===== ВЫБОР КАЛЬКУЛЯТОРА =====
    if data.startswith("calc_"):
        calc_key = data.replace("calc_", "")
        info = get_calc_info(calc_key)
        if not info:
            await query.answer("Калькулятор не найден.")
            return

        calc_name = info['name']
        first_input = info['inputs'][0]

        set_state(user_id, "calc_input", {
            "calc_key": calc_key,
            "inputs": [],
            "step": 0,
            "total": len(info["inputs"])
        })

        text_msg = f"📊 {calc_name}\n\nВведите {first_input}:"

        await query.edit_message_text(
            text_msg,
            reply_markup=get_calc_input_keyboard(),
            parse_mode=None
        )
        return

    # ===== Отмена ввода =====
    if data == "cancel_calc":
        clear_state(user_id)
        state, state_data = get_state(user_id)
        category = state_data.get("category", "finance")
        calc_list = get_calc_groups().get(category, [])
        
        await query.edit_message_text(
            "❌ Ввод отменён.\n\nВыберите калькулятор:",
            reply_markup=get_calc_list_keyboard(calc_list)
        )
        return

    # ===== Назад в меню =====
    if data == "back_to_menu":
        clear_state(user_id)
        text = after_subscribe_text()
        await query.edit_message_text(
            text,
            reply_markup=get_main_menu_with_dashboard(),
            parse_mode=None
        )
        return

    # ===== Назад к категории =====
    if data == "back_to_category":
        state, state_data = get_state(user_id)
        category = state_data.get("category", "finance")
        calc_list = get_calc_groups().get(category, [])
        await query.edit_message_text(
            "Выберите калькулятор:",
            reply_markup=get_calc_list_keyboard(calc_list)
        )
        return

    # ===== Запрос контакта =====
    if data == "request_contact":
        await query.message.reply_text(
            "📱 Нажмите кнопку ниже:",
            reply_markup=get_contact_request_keyboard()
        )
        return

    # ===== Запрос email =====
    if data == "request_email":
        set_state(user_id, "waiting_email", {})
        await query.message.reply_text(
            email_prompt(),
            reply_markup=ReplyKeyboardRemove()
        )
        return

    await query.answer("Действие не распознано.")

# ===== ОБРАБОТЧИКИ СООБЩЕНИЙ =====

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()

    state, state_data = get_state(user_id)

    # ===== ВВОД ДЛЯ ДАШБОРДА =====
    if state == "dash_input":
        dash_key = state_data.get("dash_key")
        info = DASHBOARD_CALCS.get(dash_key)
        if not info:
            await update.message.reply_text("Ошибка. Попробуйте снова /menu")
            clear_state(user_id)
            return
        
        step = state_data.get("step", 0)
        total = state_data.get("total", len(info["inputs"]))
        inputs = state_data.get("inputs", [])
        
        try:
            value = float(text.replace(",", "."))
            inputs.append(value)
        except ValueError:
            await update.message.reply_text(
                "❌ Введите число (например, 1000):",
                reply_markup=get_calc_input_keyboard()
            )
            return
        
        step += 1
        
        if step >= total:
            # Выполняем расчёт
            results = calculate_dashboard(dash_key, inputs)
            if results is None:
                await update.message.reply_text("❌ Ошибка расчёта.")
                clear_state(user_id)
                return
            
            # Сохраняем результаты
            set_state(user_id, "dash_result", {
                "dash_key": dash_key,
                "dash_results": results,
                "inputs": inputs
            })
            
            # Формируем текстовый ответ
            result_text = f"📊 **{info['name']}**\n\n"
            for key, value in results.items():
                result_text += f"**{key}:** {value}\n"
            
            await update.message.reply_text(
                result_text,
                reply_markup=get_dashboard_action_keyboard(),
                parse_mode="Markdown"
            )
            
            increment_calc_counter(user_id)
            
        else:
            next_input = info["inputs"][step]
            set_state(user_id, "dash_input", {
                "dash_key": dash_key,
                "inputs": inputs,
                "step": step,
                "total": total
            })
            await update.message.reply_text(
                f"Введите {next_input}:",
                reply_markup=get_calc_input_keyboard()
            )
        return

    # ===== ВВОД ДЛЯ КАЛЬКУЛЯТОРА =====
    if state == "calc_input":
        calc_key = state_data.get("calc_key")
        info = get_calc_info(calc_key)
        if not info:
            await update.message.reply_text("Ошибка. Попробуйте снова /menu")
            clear_state(user_id)
            return

        step = state_data.get("step", 0)
        total = state_data.get("total", len(info["inputs"]))
        inputs = state_data.get("inputs", [])

        try:
            value = float(text.replace(",", "."))
            inputs.append(value)
        except ValueError:
            await update.message.reply_text(
                "❌ Введите число (например, 1000):",
                reply_markup=get_calc_input_keyboard()
            )
            return

        step += 1

        if step >= total:
            result = calculate(calc_key, inputs)
            if result is None:
                await update.message.reply_text("❌ Ошибка расчёта.")
                clear_state(user_id)
                return

            increment_calc_counter(user_id)
            
            text_result = calc_result_text(
                info['name'],
                result,
                info.get('interpretation', 'Показатель рассчитан.'),
                info.get('advice', 'Анализируйте показатели.'),
                info.get('problems', None)
            )

            await update.message.reply_text(
                text_result,
                reply_markup=get_after_calc_keyboard(),
                parse_mode=None
            )
            clear_state(user_id)

        else:
            next_input = info["inputs"][step]
            set_state(user_id, "calc_input", {
                "calc_key": calc_key,
                "inputs": inputs,
                "step": step,
                "total": total
            })
            await update.message.reply_text(
                f"Введите {next_input}:",
                reply_markup=get_calc_input_keyboard()
            )
        return

    if state == "waiting_email":
        if re.match(r'^[^@]+@[^@]+\.[^@]+$', text):
            user = get_user(user_id)
            save_contact(user_id, user.get('first_name', ''), user.get('last_name', ''), email=text, source='email')
            update_user(user_id, email=text)
            clear_state(user_id)
            await update.message.reply_text(email_sent_text(text), parse_mode=None)
            send_guide(context, user_id)
        else:
            await update.message.reply_text("❌ Введите корректный email:")
        return

    await update.message.reply_text(
        "Я не понимаю эту команду. Используйте /menu."
    )

async def handle_contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    contact = update.message.contact

    if contact:
        phone = contact.phone_number
        first_name = contact.first_name or update.effective_user.first_name
        last_name = contact.last_name or update.effective_user.last_name

        user = get_user(user_id)
        save_contact(user_id, first_name, last_name, phone=phone, source='telegram')
        update_user(user_id, phone=phone)

        await update.message.reply_text(
            guide_sent_text(first_name),
            reply_markup=ReplyKeyboardRemove(),
            parse_mode=None
        )
        send_guide(context, user_id)
    else:
        await update.message.reply_text("❌ Не удалось получить контакт.")

# ===================================================================
# 11. ПЛАНИРОВЩИК
# ===================================================================

async def send_touch_2(context, user_id):
    try:
        await context.bot.send_message(user_id, touch_2_text(), parse_mode=None)
        update_user(user_id, touch_2_sent=1)
        logger.info(f"Касание 2 отправлено {user_id}")
    except Exception as e:
        logger.error(f"Ошибка: {e}")

async def send_touch_3(context, user_id):
    try:
        await context.bot.send_message(user_id, touch_3_text(), parse_mode=None)
        update_user(user_id, touch_3_sent=1)
        logger.info(f"Касание 3 отправлено {user_id}")
    except Exception as e:
        logger.error(f"Ошибка: {e}")

async def send_touch_4(context, user_id):
    try:
        await context.bot.send_message(
            user_id,
            touch_4_text(),
            reply_markup=get_contact_keyboard(),
            parse_mode=None
        )
        update_user(user_id, touch_4_sent=1)
        logger.info(f"Касание 4 отправлено {user_id}")
    except Exception as e:
        logger.error(f"Ошибка: {e}")

async def check_and_send_touches(context: ContextTypes.DEFAULT_TYPE):
    users = get_active_users()
    now = datetime.now()

    for user in users:
        if user['user_id'] == ADMIN_ID:
            continue
            
        try:
            first_contact = datetime.fromisoformat(user['first_contact'])
            days_passed = (now - first_contact).days

            if days_passed >= TOUCH_2_DELAY and not user.get('touch_2_sent', 0):
                if not user.get('phone') and not user.get('email'):
                    await send_touch_2(context, user['user_id'])

            if days_passed >= TOUCH_3_DELAY and not user.get('touch_3_sent', 0):
                if not user.get('phone') and not user.get('email'):
                    await send_touch_3(context, user['user_id'])

            if days_passed >= TOUCH_4_DELAY and not user.get('touch_4_sent', 0):
                if not user.get('phone') and not user.get('email'):
                    await send_touch_4(context, user['user_id'])
        except Exception as e:
            logger.error(f"Ошибка обработки {user['user_id']}: {e}")

# ===================================================================
# 12. ЗАПУСК
# ===================================================================

def main():
    logger.info("🚀 Бот запущен!")
    logger.info(f"📢 Канал: {CHANNEL_LINK}")
    logger.info(f"🌐 Сайт: {SITE_LINK}")
    logger.info(f"📊 Визуализация: {'✅ Доступна' if VISUALIZATION_AVAILABLE else '❌ Недоступна'}")
    
    if not VISUALIZATION_AVAILABLE:
        logger.warning("⚠️ Для работы графиков и PDF установите: pip install matplotlib seaborn numpy reportlab pillow")

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("menu", menu))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.CONTACT, handle_contact))

    job_queue = app.job_queue
    if job_queue:
        job_queue.run_repeating(check_and_send_touches, interval=1800, first=60)
        logger.info("⏰ Планировщик запущен")

    logger.info("✅ Бот готов к работе!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
