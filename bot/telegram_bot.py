import os
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import anthropic

# ── Config ──────────────────────────────────────────────────────────────────
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
ANTHROPIC_KEY  = os.getenv("ANTHROPIC_API_KEY", "")
ALLOWED_USER   = int(os.getenv("ALLOWED_USER_ID", "0"))  # твой Telegram user ID

client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
log = logging.getLogger(__name__)

# Хранилище истории диалога в памяти
history: dict[int, list] = {}

# ── Системный промпт ─────────────────────────────────────────────────────────
SYSTEM = """Ты — персональный AI-ассистент Дениса Файзельгаянова.

ПРОФИЛЬ:
- Денис — Финансовый директор лизинговой компании в Ташкенте
- 16 лет опыта в финансах: аудит → аналитик → руководитель проектов → CFO
- Экспертиза: финансовый анализ, МСФО (особенно МСФО 9), привлечение инвесторов, лизинговый портфель
- Инструменты: 1С, Microsoft Office, Outlook
- Язык общения: русский

ТВОИ ЗАДАЧИ:
1. Финансовый анализ — ОСВ, баланс, P&L, управленческая отчётность
2. МСФО 9 — резервы ECL, Stage 1/2/3, PD/LGD/EAD
3. Лизинговый портфель — структура, риски, дебиторская задолженность
4. Отчёты для инвесторов и акционеров
5. Деловая переписка — письма партнёрам, банкам, регуляторам
6. Личные вопросы — любые бытовые, организационные, рабочие задачи

СТИЛЬ ОТВЕТОВ:
- Чётко и по делу, без лишних слов
- Используй профессиональную финансовую терминологию
- Структурируй ответы — списки, заголовки, таблицы (где уместно)
- Если нужны уточнения — спроси коротко
- Отвечай на русском языке"""

# ── Шаблоны промптов ─────────────────────────────────────────────────────────
PROMPTS = {
    "osv": (
        "📊 *Анализ ОСВ*\n\n"
        "Вставь данные оборотно-сальдовой ведомости следующим сообщением.\n"
        "Я проверю: нетипичные остатки, отклонения >10%, отрицательные сальдо, аномалии."
    ),
    "ifrs": (
        "📐 *Резервы МСФО 9*\n\n"
        "Вставь данные портфеля или расчёта ECL следующим сообщением.\n"
        "Проверю: Stage 1/2/3, PD/LGD/EAD, форвардные индикаторы, риски для аудиторов."
    ),
    "otchet": (
        "📋 *Управленческий отчёт*\n\n"
        "Вставь данные P&L и баланса следующим сообщением.\n"
        "Подготовлю: резюме для руководства, анализ отклонений, факторы, рекомендации."
    ),
    "investor": (
        "📨 *Отчёт для инвесторов*\n\n"
        "Вставь ключевые показатели и данные следующим сообщением.\n"
        "Составлю профессиональный отчёт: KPI, достижения, вызовы, прогноз."
    ),
    "portfolio": (
        "🗂 *Анализ портфеля*\n\n"
        "Вставь данные лизингового портфеля следующим сообщением.\n"
        "Анализ: структура, концентрация рисков, дебиторка, NPL, тренды."
    ),
    "pismo": (
        "✉️ *Деловое письмо*\n\n"
        "Опиши следующим сообщением:\n"
        "— кому письмо\n— суть / что нужно донести\n— желаемый результат\n— тон (официальный / дружелюбный)"
    ),
}

HELP_TEXT = """*CFO Assistant · Команды:*

📊 /osv — анализ оборотно-сальдовой ведомости
📐 /ifrs — проверка резервов МСФО 9
📋 /otchet — управленческий отчёт (P&L / баланс)
📨 /investor — отчёт для инвесторов
🗂 /portfolio — анализ лизингового портфеля
✉️ /pismo — деловое письмо
🗑 /clear — очистить историю диалога

Или просто напиши вопрос — отвечу как личный помощник."""


# ── Guards ───────────────────────────────────────────────────────────────────
async def check_user(update: Update) -> bool:
    uid = update.effective_user.id
    if ALLOWED_USER and uid != ALLOWED_USER:
        await update.message.reply_text("Доступ закрыт.")
        return False
    return True


# ── Claude API ───────────────────────────────────────────────────────────────
async def ask_claude(user_id: int, user_msg: str) -> str:
    msgs = history.get(user_id, [])
    msgs.append({"role": "user", "content": user_msg})

    try:
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=2048,
            system=SYSTEM,
            messages=msgs
        )
        reply = response.content[0].text
        msgs.append({"role": "assistant", "content": reply})
        # Держим последние 20 сообщений в памяти
        history[user_id] = msgs[-20:]
        return reply
    except Exception as e:
        log.error(f"Claude error: {e}")
        return f"Ошибка при обращении к Claude: {e}"


# ── Handlers ─────────────────────────────────────────────────────────────────
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await check_user(update): return
    name = update.effective_user.first_name or "Денис"
    await update.message.reply_text(
        f"Привет, {name}! Я твой персональный CFO Assistant.\n\n" + HELP_TEXT,
        parse_mode="Markdown"
    )

async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await check_user(update): return
    await update.message.reply_text(HELP_TEXT, parse_mode="Markdown")

async def cmd_clear(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await check_user(update): return
    history.pop(update.effective_user.id, None)
    await update.message.reply_text("✓ История очищена. Начинаем заново.")

# Генератор команд для шаблонов
def make_cmd(key):
    async def handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not await check_user(update): return
        uid = update.effective_user.id
        # Добавляем контекст в историю
        prompt_ctx = f"[Задача: {key.upper()}] Жду данные от пользователя для анализа."
        history.setdefault(uid, [])
        history[uid].append({"role": "assistant", "content": prompt_ctx})
        await update.message.reply_text(PROMPTS[key], parse_mode="Markdown")
    return handler

async def handle_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await check_user(update): return
    uid  = update.effective_user.id
    text = update.message.text or ""
    if not text.strip(): return

    await update.message.chat.send_action("typing")
    reply = await ask_claude(uid, text)

    # Telegram лимит — 4096 символов
    if len(reply) > 4000:
        chunks = [reply[i:i+4000] for i in range(0, len(reply), 4000)]
        for chunk in chunks:
            await update.message.reply_text(chunk)
    else:
        await update.message.reply_text(reply)


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    if not TELEGRAM_TOKEN or not ANTHROPIC_KEY:
        print("Установи переменные окружения TELEGRAM_BOT_TOKEN и ANTHROPIC_API_KEY")
        return

    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start",     cmd_start))
    app.add_handler(CommandHandler("help",      cmd_help))
    app.add_handler(CommandHandler("clear",     cmd_clear))
    app.add_handler(CommandHandler("osv",       make_cmd("osv")))
    app.add_handler(CommandHandler("ifrs",      make_cmd("ifrs")))
    app.add_handler(CommandHandler("otchet",    make_cmd("otchet")))
    app.add_handler(CommandHandler("investor",  make_cmd("investor")))
    app.add_handler(CommandHandler("portfolio", make_cmd("portfolio")))
    app.add_handler(CommandHandler("pismo",     make_cmd("pismo")))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("CFO Assistant запущен...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
