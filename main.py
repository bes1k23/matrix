import json
import logging
import sqlite3
import time
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Подключение к базе данных SQLite
conn = sqlite3.connect("user_data.db", check_same_thread=False)
cursor = conn.cursor()

# Создание таблицы для хранения результатов
cursor.execute("""
CREATE TABLE IF NOT EXISTS user_results (
    user_id TEXT PRIMARY KEY,
    results TEXT,
    recommendations TEXT
)
""")
conn.commit()

# Загрузка данных из JSON
def load_questions(file_path: str):
    try:
        with open(file_path, "r", encoding="utf-8") as file:
            questions = json.load(file)["competencies"]
        return questions
    except FileNotFoundError:
        logger.error(f"File {file_path} not found.")
        raise
    except json.JSONDecodeError:
        logger.error(f"Invalid JSON format in file {file_path}.")
        raise

QUESTIONS = load_questions("questions.json")
user_data = {}

# Функция для создания шкалы прогресса
def create_progress_bar(current_index: int, total_questions: int) -> str:
    progress = int((current_index / total_questions) * 5)  # 5 блоков для шкалы
    completed_blocks = "🟩" * progress
    remaining_blocks = "⬜️" * (5 - progress)
    percentage = int((current_index / total_questions) * 100)
    return f"{completed_blocks}{remaining_blocks} ({percentage}% выполнено)"

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = str(update.effective_user.id)
    chat_id = update.effective_chat.id if update.effective_chat else "N/A"
    logger.info(f"User {user_id} started the bot in chat {chat_id}.")

    if user_id not in user_data:
        user_data[user_id] = {"current_question_index": 0, "scores": {}}

    keyboard = [[InlineKeyboardButton("Начать оценку", callback_data="start_assessment")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Готовы начать оценку компетенций?", reply_markup=reply_markup)

# Начало оценки
async def start_assessment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    user_id = str(update.effective_user.id)
    logger.info(f"Assessment started for user {user_id}.")

    if user_id not in user_data:
        user_data[user_id] = {"current_question_index": 0, "scores": {}}

    await ask_question(update, context, user_id)

# Задать вопрос
async def ask_question(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: str) -> None:
    current_index = user_data[user_id]["current_question_index"]
    total_questions = len(QUESTIONS[0]["questions"])
    if current_index >= total_questions:
        await show_results(update, context, user_id)
        return

    question = QUESTIONS[0]["questions"][current_index]

    # Кнопки ответов
    keyboard = [
        [InlineKeyboardButton(option["text"], callback_data=f"answer_{i}")]
        for i, option in enumerate(question["options"])
    ]

    # Добавляем кнопки навигации
    navigation_buttons = [
        InlineKeyboardButton("Назад", callback_data="back"),
        InlineKeyboardButton("Завершить", callback_data="finish"),
    ]
    keyboard.append(navigation_buttons)

    reply_markup = InlineKeyboardMarkup(keyboard)

    progress_bar = create_progress_bar(current_index + 1, total_questions)
    message = (
        f"Компетенция: {QUESTIONS[0]['name']}\n"
        f"Вопрос {current_index + 1} из {total_questions} 🔍\n"
        f"{progress_bar}\n\n"
        f"{question['question']}"
    )
    await update.callback_query.edit_message_text(message, reply_markup=reply_markup)

# Обработка ответов
async def handle_answer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    user_id = str(update.effective_user.id)
    answer_index = int(query.data.split("_")[1])
    current_index = user_data[user_id]["current_question_index"]

    # Сохранение ответа
    competency = QUESTIONS[0]["name"]
    if competency not in user_data[user_id]["scores"]:
        user_data[user_id]["scores"][competency] = []
    user_data[user_id]["scores"][competency].append(answer_index + 1)

    # Переход к следующему вопросу
    user_data[user_id]["current_question_index"] += 1
    if user_data[user_id]["current_question_index"] < len(QUESTIONS[0]["questions"]):
        await ask_question(update, context, user_id)
    else:
        await show_results(update, context, user_id)

# Показ результатов
async def show_results(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: str) -> None:
    scores = user_data[user_id]["scores"]
    teamwork_score = sum(scores["teamwork"]) / len(scores["teamwork"])

    # Сохранение результатов в базу данных
    cursor.execute("""
    INSERT OR REPLACE INTO user_results (user_id, results, recommendations)
    VALUES (?, ?, ?)
    """, (user_id, json.dumps(scores), "TODO: Recommendations"))
    conn.commit()

    # Формирование сообщения с результатами
    message = (
        f"Результаты оценки:\n"
        f"• Командная работа: {teamwork_score:.2f}/5\n\n"
        f"Общий уровень: {teamwork_score:.2f}/5\n\n"
        f"Рекомендации:\n"
        f"• Пройдите курс 'Основы командной работы' (LO-AL3-001).\n"
        f"• Изучите материал 'Как работать в команде эффективно' (LO-EL4-001)."
    )
    await update.callback_query.edit_message_text(message)

# Основная функция
def main() -> None:
    application = Application.builder().token("7889453188:AAEmb2hKOv6dWxGrb7aWy59I2DSkMXwGhLY").build()

    # Регистрация обработчиков
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(start_assessment, pattern="^start_assessment$"))
    application.add_handler(CallbackQueryHandler(handle_answer, pattern="^answer_"))
    application.add_handler(CallbackQueryHandler(ask_question, pattern="^back$"))

    application.run_polling()

if __name__ == "__main__":
    main()
