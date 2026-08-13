"""
БОТ «ИНЖИНИРИНГ БИЗНЕСА»
Версия 6.2 — Исправлен для python-telegram-bot 22.x
"""

import os
import json
import logging
import re
import sqlite3
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

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

CHANNEL_ID = os.environ.get("CHANNEL_ID", "@YourChannel")
CHANNEL_LINK = os.environ.get("CHANNEL_LINK", "https://t.me/YourChannel")
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
# 2. БАЗА ДАННЫХ
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

# ===================================================================
# 3. ТЕКСТЫ
# ===================================================================

def welcome_text(first_name):
    return f"""Здравствуйте! 👋 Меня зовут Георгий.

Я помогаю собственникам МСБ наводить порядок в бизнесе. Освобождаю от операционки, строю системы, которые работают сами.

Здесь я собрал для вас **бесплатные калькуляторы** — они помогут быстро оценить ключевые показатели вашего бизнеса.

🔒 Чтобы получить доступ ко всем калькуляторам, подпишитесь на мой канал:
👉 {CHANNEL_LINK}

Там я публикую короткие советы и разборы для собственников МСБ.

✅ После подписки нажмите кнопку ниже."""

def after_subscribe_text():
    return """Отлично! Вы подписаны ✅

Теперь вам доступны все калькуляторы.

Помните: **система есть везде. Даже там, где кажется, что её нет.**

Выберите отдел, который хотите проверить:"""

def calc_result_text(name, value, interpretation, advice):
    return f"""📊 **{name}:** {value}

📈 **Что это значит:** {interpretation}

💡 **Как улучшить:**
{advice}

🔄 Попробуйте другой калькулятор или вернитесь в меню.

🌐 А если хотите разобраться глубже — на моём сайте есть статьи с примерами из практики: {SITE_LINK}"""

def touch_2_text():
    return f"""Привет! Это Георгий 👋

Вы недавно пользовались калькуляторами. Как вам результаты? Помогли увидеть что-то новое?

Я знаю, что многие собственники после расчётов говорят: *«Цифры понятны, но что делать дальше — непонятно»*.

Поэтому на моём сайте я собрал **подробные разборы** каждого показателя:
✔ Как считать правильно
✔ Какие ошибки чаще всего допускают
✔ Примеры из моей практики

🌐 Переходите по ссылке: {SITE_LINK}

Кстати, на сайте есть раздел «Кейсы» — там реальные истории моих клиентов.

Если захотите попрактиковаться — у меня есть ещё 20 калькуляторов. Просто выберите отдел ниже."""

def touch_3_text():
    return f"""Здравствуйте! Это снова Георгий.

Хочу поделиться с вами реальным кейсом из моей практики.

---
📂 **Кейс: Производственная компания (МСБ, 45 сотрудников)**

**Ситуация:**
Выручка растёт, а прибыль падает. Собственник на работе 24/7, сотрудники ждут указаний. Хаос.

**Что мы сделали:**
1. Провели анализ бизнес-процессов — нашли узкие места
2. Внедрили простые регламенты для каждого отдела
3. Настроили систему мотивации с прозрачными KPI
4. Внедрили управленческий учёт

**Результат за 3 месяца:**
✔ Прибыль выросла на 34%
✔ Собственник перестал участвовать в каждой планерке
✔ Сотрудники работают без постоянного контроля
✔ Появилась система, которая работает сама

---
💡 **Почему это важно:**
У вас может быть такая же история. Порядок вместо хаоса — это реально. Я это делаю каждый день.

На моём сайте есть ещё 20 таких разборов. Переходите: {SITE_LINK}"""

def touch_4_text():
    return f"""Привет! Это Георгий.

Это последнее сообщение от меня. Я не хочу вас доставать, но хочу оставить вам кое-что ценное.

---
**Гайд «Как навести порядок в бизнесе за 30 дней»**

В нём я по шагам расписал:
✔ Как перестать быть «пожарным» в своей компании
✔ Как внедрить систему, которая работает без вас
✔ Как мотивировать сотрудников без постоянного контроля

Это те самые шаги, с которых начинают мои клиенты.

---
**Как получить гайд?**

Выберите удобный способ:

1️⃣ **Поделиться контактом Telegram** (один клик) — и я сразу пришлю гайд в этот чат.
2️⃣ **Оставить email** — я отправлю гайд на почту.

---
🌐 Также вы можете:
- Посмотреть мой сайт: {SITE_LINK}
- Почитать кейсы: {SITE_LINK}/cases
- Связаться со мной лично: {CONTACT_LINK}

Удачи в наведении порядка в вашем бизнесе! 🚀"""

def guide_sent_text(name):
    return f"""Спасибо, {name}! Гайд отправлен вам в чат ниже 📥

📌 **Что ещё может быть полезным:**
- Мой сайт: {SITE_LINK}
- Раздел с кейсами: {SITE_LINK}/cases
- Мои контакты: {CONTACT_LINK}

Я всегда на связи в Telegram. Если захотите обсудить ваш бизнес — пишите.

До встречи!"""

def email_prompt():
    return "Введите ваш email:"

def email_sent_text(email):
    return f"""Спасибо! Гайд отправлен на {email} 📥

📌 **Что ещё может быть полезным:**
- Мой сайт: {SITE_LINK}
- Раздел с кейсами: {SITE_LINK}/cases
- Мои контакты: {CONTACT_LINK}

Если захотите обсудить ваш бизнес — я на связи в Telegram: {CONTACT_LINK}

До встречи!"""

# ===================================================================
# 4. КЛАВИАТУРЫ (ИСПРАВЛЕНЫ ДЛЯ python-telegram-bot 22.x)
# ===================================================================

def get_start_keyboard():
    """Клавиатура для старта"""
    keyboard = [
        [InlineKeyboardButton("📢 Подписаться", url=CHANNEL_LINK)],
        [InlineKeyboardButton("✅ Проверить подписку", callback_data="check_sub")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_main_menu():
    """Главное меню"""
    keyboard = [
        [InlineKeyboardButton("📊 Общий финансовый", callback_data="menu_ceo")],
        [InlineKeyboardButton("📈 Маркетинг", callback_data="menu_marketing")],
        [InlineKeyboardButton("💰 Продажи", callback_data="menu_sales")],
        [InlineKeyboardButton("📦 Логистика", callback_data="menu_logistics")],
        [InlineKeyboardButton("👥 Персонал", callback_data="menu_hr")],
        [InlineKeyboardButton("📅 Бухгалтерия", callback_data="menu_finance")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_calc_list_keyboard(calc_list):
    """Клавиатура со списком калькуляторов"""
    keyboard = []
    for key, name in calc_list:
        keyboard.append([InlineKeyboardButton(name, callback_data=f"calc_{key}")])
    keyboard.append([InlineKeyboardButton("⬅ Назад к категориям", callback_data="back_to_menu")])
    return InlineKeyboardMarkup(keyboard)

def get_after_calc_keyboard():
    """Клавиатура после расчёта"""
    keyboard = [
        [
            InlineKeyboardButton("🔄 Другой калькулятор", callback_data="back_to_category"),
            InlineKeyboardButton("🏠 В меню", callback_data="back_to_menu")
        ],
        [InlineKeyboardButton("🌐 Перейти на сайт", url=SITE_LINK)]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_contact_keyboard():
    """Клавиатура для запроса контакта"""
    keyboard = [
        [InlineKeyboardButton("📱 Поделиться контактом", callback_data="request_contact")],
        [InlineKeyboardButton("✉️ Оставить email", callback_data="request_email")],
        [InlineKeyboardButton("🌐 Перейти на сайт", url=SITE_LINK)]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_contact_request_keyboard():
    """Клавиатура с кнопкой запроса контакта"""
    keyboard = [
        [KeyboardButton("📱 Отправить контакт", request_contact=True)]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)

# ===================================================================
# 5. КАЛЬКУЛЯТОРЫ
# ===================================================================

CALC_FORMULAS = {
    "net_profit": {
        "name": "Чистая прибыль",
        "inputs": ["Выручка (руб)", "Расходы (руб)", "Налоги (руб)"],
        "formula": "a - b - c"
    },
    "roe": {
        "name": "Рентабельность капитала (ROE)",
        "inputs": ["Чистая прибыль (руб)", "Собственный капитал (руб)"],
        "formula": "(a / b) * 100"
    },
    "roa": {
        "name": "Рентабельность активов (ROA)",
        "inputs": ["Чистая прибыль (руб)", "Активы (руб)"],
        "formula": "(a / b) * 100"
    },
    "bep": {
        "name": "Точка безубыточности",
        "inputs": ["Постоянные расходы (руб/мес)", "Цена продажи (руб)", "Переменные расходы (руб)"],
        "formula": "a / (b - c)"
    },
    "autonomy": {
        "name": "Финансовая независимость",
        "inputs": ["Собственный капитал (руб)", "Активы (руб)"],
        "formula": "(a / b) * 100"
    },
    "cash_flow": {
        "name": "Денежный поток (FCF)",
        "inputs": ["Операционный денежный поток (руб)", "Капитальные затраты (руб)"],
        "formula": "a - b"
    },
    "cac": {
        "name": "Стоимость привлечения клиента (CAC)",
        "inputs": ["Расходы на маркетинг (руб)", "Количество новых клиентов"],
        "formula": "a / b"
    },
    "ltv": {
        "name": "Пожизненная ценность клиента (LTV)",
        "inputs": ["Средний чек (руб)", "Частота покупок в год", "Срок жизни клиента (лет)"],
        "formula": "a * b * c"
    },
    "romi": {
        "name": "Окупаемость маркетинга (ROMI)",
        "inputs": ["Доход от маркетинга (руб)", "Расходы на маркетинг (руб)"],
        "formula": "((a - b) / b) * 100"
    },
    "conversion": {
        "name": "Конверсия (CR)",
        "inputs": ["Количество покупок/заявок", "Количество посетителей/лидов"],
        "formula": "(a / b) * 100"
    },
    "closure": {
        "name": "Коэффициент закрытия сделок",
        "inputs": ["Выигранные сделки", "Все сделки"],
        "formula": "(a / b) * 100"
    },
    "avg_check": {
        "name": "Средний чек",
        "inputs": ["Выручка (руб)", "Количество транзакций"],
        "formula": "a / b"
    },
    "turnover": {
        "name": "Оборачиваемость запасов",
        "inputs": ["Себестоимость проданных товаров (руб/год)", "Средние запасы (руб)"],
        "formula": "a / b"
    },
    "turnover_days": {
        "name": "Длительность оборота запасов (дней)",
        "inputs": ["Оборачиваемость запасов (раз в год)"],
        "formula": "365 / a"
    },
    "employee_turnover": {
        "name": "Текучесть кадров",
        "inputs": ["Уволенные сотрудники", "Среднесписочная численность"],
        "formula": "(a / b) * 100"
    },
    "productivity": {
        "name": "Производительность труда",
        "inputs": ["Выручка (руб)", "Количество сотрудников"],
        "formula": "a / b"
    },
    "hour_cost": {
        "name": "Стоимость часа работы сотрудника",
        "inputs": ["Зарплата (руб/мес)", "Количество рабочих дней в месяце"],
        "formula": "a / (b * 8)"
    },
    "usn_6": {
        "name": "УСН «Доходы» (6%)",
        "inputs": ["Доходы (руб)"],
        "formula": "a * 0.06"
    },
    "usn_15": {
        "name": "УСН «Доходы минус расходы» (15%)",
        "inputs": ["Доходы (руб)", "Расходы (руб)"],
        "formula": "(a - b) * 0.15"
    },
    "nds": {
        "name": "НДС 20%",
        "inputs": ["Сумма без НДС (руб)"],
        "formula": "a * 1.2"
    }
}

def calculate(formula_key, inputs):
    try:
        names = ["a", "b", "c", "d", "e"]
        local_vars = {}
        for i, val in enumerate(inputs):
            local_vars[names[i]] = float(val)
        result = eval(CALC_FORMULAS[formula_key]["formula"], {}, local_vars)
        if result % 1 == 0:
            return int(result)
        else:
            return round(result, 2)
    except:
        return None

def get_interpretation(formula_key, value):
    interpretations = {
        "net_profit": "Чистая прибыль — главный показатель здоровья бизнеса. Стремитесь к росту.",
        "roe": "Рентабельность капитала показывает, как эффективно работают вложенные деньги.",
        "roa": "Рентабельность активов — эффективность использования имущества компании.",
        "bep": "Точка безубыточности — минимальный объём продаж для покрытия расходов.",
        "autonomy": "Финансовая независимость: чем выше, тем меньше зависимость от кредиторов.",
        "cash_flow": "Положительный поток — бизнес генерирует деньги. Отрицательный — сжигает.",
        "cac": "Стоимость привлечения клиента. Должна быть ниже LTV.",
        "ltv": "Пожизненная ценность клиента. Чем выше, тем больше можно вложить в привлечение.",
        "romi": "Окупаемость маркетинга: >200% — отлично, <100% — проблема.",
        "conversion": "Конверсия показывает эффективность воронки продаж.",
        "closure": "Коэффициент закрытия: >30% — отлично, <15% — сигнал.",
        "avg_check": "Средний чек — один из ключевых драйверов прибыли.",
        "turnover": "Оборачиваемость запасов: чем выше, тем меньше денег заморожено.",
        "turnover_days": "Длительность оборота: чем меньше дней, тем эффективнее склад.",
        "employee_turnover": "Текучесть: <10% — отлично, >20% — сигнал.",
        "productivity": "Производительность труда: сколько выручки приносит один сотрудник.",
        "hour_cost": "Стоимость часа работы сотрудника.",
        "usn_6": "Налог по УСН «Доходы» — 6% от выручки.",
        "usn_15": "Налог по УСН «Доходы минус расходы» — 15% от разницы.",
        "nds": "Сумма с НДС 20%."
    }
    return interpretations.get(formula_key, "Показатель рассчитан.")

def get_advice(formula_key, value):
    advice = {
        "net_profit": "1. Посчитайте маржинальность каждого продукта\n2. Сократите неэффективные расходы\n3. Пересмотрите ценообразование",
        "roe": "1. Увеличьте чистую прибыль\n2. Оптимизируйте структуру капитала\n3. Выходите на новые рынки",
        "roa": "1. Продайте неиспользуемые активы\n2. Увеличьте загрузку производства\n3. Пересмотрите инвестиции",
        "bep": "1. Повысьте цену продажи\n2. Снизьте переменные расходы\n3. Сократите постоянные расходы",
        "autonomy": "1. Наращивайте собственный капитал\n2. Сокращайте кредитную нагрузку\n3. Рефинансируйте дорогие кредиты",
        "cash_flow": "1. Ускорьте сбор дебиторки\n2. Договоритесь о рассрочке с поставщиками\n3. Сократите запасы",
        "cac": "1. Сократите бюджет на неэффективные каналы\n2. Увеличьте конверсию\n3. Настройте реферальную программу",
        "ltv": "1. Увеличьте средний чек через апсейл\n2. Внедрите программу лояльности\n3. Работайте с возражениями",
        "romi": "1. Проанализируйте каналы\n2. Увеличьте бюджет на топ-каналы\n3. Отключите неэффективные",
        "conversion": "1. Проверьте юзабилити сайта\n2. Улучшите оффер\n3. Настройте ретаргетинг",
        "closure": "1. Проверьте квалификацию лидов\n2. Обучите менеджеров\n3. Анализируйте проигранные сделки",
        "avg_check": "1. Предлагайте доп. товары/услуги\n2. Внедрите систему скидок\n3. Используйте апсейл",
        "turnover": "1. Проведите ABC-анализ\n2. Сократите заказы по медленным товарам\n3. Используйте систему «точно в срок»",
        "turnover_days": "1. Заменяйте медленные товары\n2. Настройте авто-заказ по остаткам\n3. Проводите акции на залежавшийся товар",
        "employee_turnover": "1. Проведите exit-интервью\n2. Внедрите прозрачную мотивацию\n3. Проверьте адаптацию",
        "productivity": "1. Автоматизируйте ручные процессы\n2. Обучите сотрудников\n3. Внедрите KPI",
        "hour_cost": "1. Оцените эффективность задач\n2. Делегируйте низкоприоритетные задачи\n3. Оптимизируйте процессы",
        "usn_6": "1. Сравните с УСН 15%\n2. Учитывайте страховые взносы\n3. Планируйте доходы",
        "usn_15": "1. Сравните с УСН 6%\n2. Учитывайте все расходы\n3. Храните документы",
        "nds": "1. Проверьте ставку\n2. Учитывайте входной НДС\n3. Сдавайте отчётность вовремя"
    }
    return advice.get(formula_key, "Анализируйте показатели и ищите точки роста.")

def get_calc_groups():
    return {
        "ceo": [
            ("net_profit", "Чистая прибыль"),
            ("roe", "Рентабельность капитала (ROE)"),
            ("roa", "Рентабельность активов (ROA)"),
            ("bep", "Точка безубыточности"),
            ("autonomy", "Финансовая независимость"),
            ("cash_flow", "Денежный поток (FCF)")
        ],
        "marketing": [
            ("cac", "Стоимость привлечения клиента (CAC)"),
            ("ltv", "Пожизненная ценность клиента (LTV)"),
            ("romi", "Окупаемость маркетинга (ROMI)"),
            ("conversion", "Конверсия (CR)")
        ],
        "sales": [
            ("closure", "Коэффициент закрытия сделок"),
            ("avg_check", "Средний чек")
        ],
        "logistics": [
            ("turnover", "Оборачиваемость запасов"),
            ("turnover_days", "Длительность оборота запасов")
        ],
        "hr": [
            ("employee_turnover", "Текучесть кадров"),
            ("productivity", "Производительность труда"),
            ("hour_cost", "Стоимость часа работы")
        ],
        "finance": [
            ("usn_6", "УСН «Доходы» (6%)"),
            ("usn_15", "УСН «Доходы минус расходы» (15%)"),
            ("nds", "НДС 20%")
        ]
    }

def get_calc_info(calc_key):
    return CALC_FORMULAS.get(calc_key)

# ===================================================================
# 6. ОСНОВНОЙ БОТ
# ===================================================================

init_db()

# Хранилище данных для калькуляторов (в оперативной памяти)
calc_data = {}

def is_subscribed(user_id):
    """Проверка подписки на канал"""
    try:
        # Создаём временное приложение для проверки
        app = Application.builder().token(BOT_TOKEN).build()
        status = app.bot.get_chat_member(CHANNEL_ID, user_id).status
        return status in ['member', 'administrator', 'creator']
    except Exception as e:
        logger.error(f"Ошибка проверки подписки: {e}")
        return False

def send_guide(context, user_id):
    """Отправка гайда пользователю"""
    guide_text = f"""📘 **Гайд «Как навести порядок в бизнесе за 30 дней»**

*Вступление*
Меня зовут Георгий. Я помогаю собственникам МСБ наводить порядок в бизнесе.

Этот гайд — не теория. Это пошаговый план, который я проверял на десятках проектов.

---

**Глава 1. Диагностика хаоса (Дни 1–3)**

1. Нарисуйте карту процессов
2. Проведите аудит времени
3. Сделайте финансовый срез

---

**Глава 2. Наведение порядка (Дни 4–14)**

1. Внедрите управленческий учёт
2. Создайте регламенты и инструкции
3. Введите KPI для сотрудников
4. Назначьте зоны ответственности

---

**Глава 3. Автоматизация и контроль (Дни 15–21)**

1. Внедрите точки контроля
2. Используйте цифровые инструменты
3. Начните делегировать задачи

---

**Глава 4. Устойчивая система (Дни 22–30)**

1. Проведите тренинг для сотрудников
2. Соберите обратную связь
3. Закрепите дисциплину
4. Наслаждайтесь свободой

---

*Поздравляю! Вы прошли путь от хаоса к системе.*

Если вы чувствуете, что не справляетесь самостоятельно — я рядом.

**Свяжитесь со мной:**
- Telegram: {CONTACT_LINK}
- Сайт: {SITE_LINK}

*Помните: система есть везде. Даже там, где кажется, что её нет.*

*Георгий, 10+ лет в операционном консалтинге*"""

    context.bot.send_message(user_id, guide_text, parse_mode='Markdown')

# ===== ОБРАБОТЧИКИ КОМАНД =====

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    user_id = update.effective_user.id
    first_name = update.effective_user.first_name or "Друг"
    last_name = update.effective_user.last_name
    username = update.effective_user.username

    user = get_user(user_id)
    if not user:
        create_user(user_id, first_name, last_name, username)

    await update.message.reply_text(
        welcome_text(first_name),
        reply_markup=get_start_keyboard(),
        parse_mode='Markdown'
    )

async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /menu"""
    user_id = update.effective_user.id
    
    if not is_subscribed(user_id):
        await update.message.reply_text(
            "⚠️ Для доступа к калькуляторам подпишитесь на канал:",
            reply_markup=get_start_keyboard()
        )
        return
    
    await update.message.reply_text(
        after_subscribe_text(),
        reply_markup=get_main_menu(),
        parse_mode='Markdown'
    )

# ===== ОБРАБОТЧИКИ КНОПОК =====

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик нажатий на кнопки"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    data = query.data

    # Проверка подписки
    if data == "check_sub":
        if is_subscribed(user_id):
            update_user(user_id, subscribed=1)
            try:
                await query.edit_message_text(
                    after_subscribe_text(),
                    reply_markup=get_main_menu(),
                    parse_mode='Markdown'
                )
            except:
                await query.message.reply_text(
                    after_subscribe_text(),
                    reply_markup=get_main_menu(),
                    parse_mode='Markdown'
                )
        else:
            await query.answer("❌ Вы не подписаны. Подпишитесь и нажмите 'Проверить' снова.")

    # Меню
    elif data.startswith("menu_"):
        category = data.replace("menu_", "")
        calc_list = get_calc_groups().get(category, [])
        if calc_list:
            set_state(user_id, "category", {"category": category})
            try:
                await query.edit_message_text(
                    "Выберите калькулятор:",
                    reply_markup=get_calc_list_keyboard(calc_list)
                )
            except:
                await query.message.reply_text(
                    "Выберите калькулятор:",
                    reply_markup=get_calc_list_keyboard(calc_list)
                )
        else:
            await query.answer("Калькуляторов пока нет в этом разделе.")

    # Выбор калькулятора
    elif data.startswith("calc_"):
        calc_key = data.replace("calc_", "")
        info = get_calc_info(calc_key)
        if not info:
            await query.answer("Калькулятор не найден.")
            return

        set_state(user_id, "calc_input", {
            "calc_key": calc_key,
            "inputs": [],
            "step": 0,
            "total": len(info["inputs"])
        })

        try:
            await query.edit_message_text(
                f"📊 **{info['name']}**\n\nВведите {info['inputs'][0]}:",
                parse_mode='Markdown'
            )
        except:
            await query.message.reply_text(
                f"📊 **{info['name']}**\n\nВведите {info['inputs'][0]}:",
                parse_mode='Markdown'
            )

    # Назад в меню
    elif data == "back_to_menu":
        clear_state(user_id)
        try:
            await query.edit_message_text(
                after_subscribe_text(),
                reply_markup=get_main_menu(),
                parse_mode='Markdown'
            )
        except:
            await query.message.reply_text(
                after_subscribe_text(),
                reply_markup=get_main_menu(),
                parse_mode='Markdown'
            )

    # Назад к категории
    elif data == "back_to_category":
        state, state_data = get_state(user_id)
        category = state_data.get("category", "ceo")
        calc_list = get_calc_groups().get(category, [])
        try:
            await query.edit_message_text(
                "Выберите калькулятор:",
                reply_markup=get_calc_list_keyboard(calc_list)
            )
        except:
            await query.message.reply_text(
                "Выберите калькулятор:",
                reply_markup=get_calc_list_keyboard(calc_list)
            )

    # Запрос контакта
    elif data == "request_contact":
        await query.message.reply_text(
            "📱 Нажмите кнопку ниже, чтобы поделиться контактом:",
            reply_markup=get_contact_request_keyboard()
        )

    # Запрос email
    elif data == "request_email":
        set_state(user_id, "waiting_email", {})
        await query.message.reply_text(
            email_prompt(),
            reply_markup=ReplyKeyboardRemove()
        )

    else:
        await query.answer("Действие не распознано.")

# ===== ОБРАБОТЧИКИ СООБЩЕНИЙ =====

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик текстовых сообщений"""
    user_id = update.effective_user.id
    text = update.message.text.strip()

    state, state_data = get_state(user_id)

    # Состояние: ввод данных для калькулятора
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
            await update.message.reply_text("❌ Введите число (например, 1000 или 1000.50):")
            return

        step += 1

        if step >= total:
            result = calculate(calc_key, inputs)
            if result is None:
                await update.message.reply_text("❌ Ошибка расчёта. Проверьте введённые данные.")
                clear_state(user_id)
                return

            increment_calc_counter(user_id)
            interpretation = get_interpretation(calc_key, result)
            advice = get_advice(calc_key, result)

            if isinstance(result, float):
                result_str = f"{result:.2f}"
            else:
                result_str = str(result)

            await update.message.reply_text(
                calc_result_text(info['name'], result_str, interpretation, advice),
                reply_markup=get_after_calc_keyboard(),
                parse_mode='Markdown'
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
            await update.message.reply_text(f"Введите {next_input}:")
        return

    # Состояние: ожидание email
    elif state == "waiting_email":
        if re.match(r'^[^@]+@[^@]+\.[^@]+$', text):
            user = get_user(user_id)
            save_contact(
                user_id,
                user.get('first_name', ''),
                user.get('last_name', ''),
                email=text,
                source='email'
            )
            update_user(user_id, email=text)
            clear_state(user_id)
            await update.message.reply_text(email_sent_text(text), parse_mode='Markdown')
            send_guide(context, user_id)
        else:
            await update.message.reply_text("❌ Введите корректный email (например, name@domain.com):")
        return

    # Любое другое сообщение
    else:
        await update.message.reply_text(
            "Я не понимаю эту команду. Используйте /menu для доступа к калькуляторам."
        )

async def handle_contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик контакта"""
    user_id = update.effective_user.id
    contact = update.message.contact

    if contact:
        phone = contact.phone_number
        first_name = contact.first_name or update.effective_user.first_name
        last_name = contact.last_name or update.effective_user.last_name

        user = get_user(user_id)
        save_contact(
            user_id,
            first_name,
            last_name,
            phone=phone,
            source='telegram'
        )
        update_user(user_id, phone=phone)

        await update.message.reply_text(
            guide_sent_text(first_name),
            reply_markup=ReplyKeyboardRemove(),
            parse_mode='Markdown'
        )
        send_guide(context, user_id)
    else:
        await update.message.reply_text(
            "❌ Не удалось получить контакт. Попробуйте ещё раз или оставьте email."
        )

# ===================================================================
# 7. ПЛАНИРОВЩИК
# ===================================================================

async def send_touch_2(context, user_id):
    try:
        await context.bot.send_message(user_id, touch_2_text(), parse_mode='Markdown')
        update_user(user_id, touch_2_sent=1)
        logger.info(f"✅ Касание 2 отправлено пользователю {user_id}")
    except Exception as e:
        logger.error(f"❌ Ошибка касания 2: {e}")

async def send_touch_3(context, user_id):
    try:
        await context.bot.send_message(user_id, touch_3_text(), parse_mode='Markdown')
        update_user(user_id, touch_3_sent=1)
        logger.info(f"✅ Касание 3 отправлено пользователю {user_id}")
    except Exception as e:
        logger.error(f"❌ Ошибка касания 3: {e}")

async def send_touch_4(context, user_id):
    try:
        await context.bot.send_message(
            user_id,
            touch_4_text(),
            reply_markup=get_contact_keyboard(),
            parse_mode='Markdown'
        )
        update_user(user_id, touch_4_sent=1)
        logger.info(f"✅ Касание 4 отправлено пользователю {user_id}")
    except Exception as e:
        logger.error(f"❌ Ошибка касания 4: {e}")

async def check_and_send_touches(context: ContextTypes.DEFAULT_TYPE):
    """Проверка и отправка касаний"""
    users = get_active_users()
    now = datetime.now()

    for user in users:
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
            logger.error(f"❌ Ошибка обработки пользователя {user['user_id']}: {e}")

# ===================================================================
# 8. ЗАПУСК
# ===================================================================

def main():
    """Запуск бота"""
    logger.info("🚀 Бот «Инжиниринг бизнеса» запущен!")
    logger.info(f"📢 Канал: {CHANNEL_LINK}")
    logger.info(f"🌐 Сайт: {SITE_LINK}")

    app = Application.builder().token(BOT_TOKEN).build()

    # Регистрация обработчиков
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("menu", menu))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.CONTACT, handle_contact))

    # Планировщик (проверка каждые 30 минут)
    job_queue = app.job_queue
    if job_queue:
        job_queue.run_repeating(check_and_send_touches, interval=1800, first=60)
        logger.info("⏰ Планировщик запущен. Проверка каждые 30 минут...")

    logger.info("✅ Бот готов к работе на BotHost.ru!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
