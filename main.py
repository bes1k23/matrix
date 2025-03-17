import json
import logging
import time
import traceback
from datetime import datetime
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
)
from tracer_setup import setup_tracing  # Импортируем настройки OpenTelemetry

# Настройка логирования
setup_tracing()  # Инициализация OpenTelemetry

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Загрузка данных из JSON
def load_questions(file_path: str):
    start_time = time.time()
    try:
        with open(file_path, "r", encoding="utf-8") as file:
            questions = json.load(file)["competencies"]
        duration = time.time() - start_time
        logger.info(f"Questions loaded from {file_path} in {duration:.4f} seconds")
        return questions
    except FileNotFoundError:
        logger.error(f"File {file_path} not found.")
        raise
    except json.JSONDecodeError:
        logger.error(f"Invalid JSON format in file {file_path}.")
        raise

QUESTIONS = load_questions("questions.json")
user_data = {}

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

# Команда /help
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = str(update.effective_user.id)
    chat_id = update.effective_chat.id if update.effective_chat else "N/A"
    logger.info(f"User {user_id} requested help in chat {chat_id}.")

    help_text = (
        "Доступные команды:\n"
        "/start - Начать оценку компетенций\n"
        "/repeat - Начать оценку заново\n"
        "/help - Получить справку о боте\n"
        "/cancel - Отменить текущее действие\n"
        "/back - Вернуться к предыдущему вопросу\n"
        "/finish - Завершить тест и показать результаты"
    )
    await update.message.reply_text(help_text)

# Команда /repeat
async def repeat_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = str(update.effective_user.id)
    chat_id = update.effective_chat.id if update.effective_chat else "N/A"
    logger.info(f"User {user_id} requested to repeat the assessment in chat {chat_id}.")

    user_data[user_id] = {"current_question_index": 0, "scores": {}}
    await update.message.reply_text("Оценка начата заново.")
    await start_assessment(update, context, user_id)

# Обработка нажатий на кнопки
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        query = update.callback_query
        await query.answer()

        user_id = str(update.effective_user.id)
        chat_id = update.effective_chat.id if update.effective_chat else "N/A"
        data = query.data

        logger.debug(f"Processing callback data: {data} for user {user_id} in chat {chat_id}")

        if data == "start_assessment":
            await start_assessment(update, context, user_id)
        elif data.startswith("answer_"):
            await handle_answer(update, context)
        elif data == "back":
            await go_back(update, context, user_id)
        elif data == "finish":
            await show_results(update, context, user_id)
    except Exception as e:
        error_message = f"Error handling callback: {e}\n{traceback.format_exc()}"
        logger.error(error_message)
        await update.callback_query.edit_message_text("Произошла ошибка. Пожалуйста, попробуйте снова.")

# Начало оценки
async def start_assessment(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: str) -> None:
    user_data[user_id]["current_question_index"] = 0
    logger.info(f"Assessment started for user {user_id}. Current state: {user_data[user_id]}")
    await ask_question(update, context, user_id)

# Задать вопрос
async def ask_question(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: str) -> None:
    current_index = user_data[user_id]["current_question_index"]
    if current_index >= len(QUESTIONS[0]["questions"]):
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

    progress = f"Вопрос {current_index + 1} из {len(QUESTIONS[0]['questions'])}"
    logger.info(f"Sending question {current_index + 1} to user {user_id}. Current state: {user_data[user_id]}")
    await update.callback_query.edit_message_text(
        f"{progress}\n\n{question['question']}", reply_markup=reply_markup
    )

# Обработка ответов
async def handle_answer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    user_id = str(update.effective_user.id)
    chat_id = update.effective_chat.id if update.effective_chat else "N/A"
    answer_index = int(query.data.split("_")[1])
    current_index = user_data[user_id]["current_question_index"]

    # Сохранение ответа
    competency = QUESTIONS[0]["name"]
    if competency not in user_data[user_id]["scores"]:
        user_data[user_id]["scores"][competency] = []
    user_data[user_id]["scores"][competency].append(answer_index + 1)
    logger.info(
        f"User {user_id} answered question {current_index + 1} with option {answer_index + 1}. "
        f"Current state: {user_data[user_id]}"
    )

    # Переход к следующему вопросу
    user_data[user_id]["current_question_index"] += 1
    if user_data[user_id]["current_question_index"] < len(QUESTIONS[0]["questions"]):
        await ask_question(update, context, user_id)
    else:
        await show_results(update, context, user_id)

# Возврат к предыдущему вопросу
async def go_back(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: str) -> None:
    user_data[user_id]["current_question_index"] -= 1
    if user_data[user_id]["current_question_index"] < 0:
        user_data[user_id]["current_question_index"] = 0  # Защита от выхода за пределы
    logger.info(f"User {user_id} went back. Current state: {user_data[user_id]}")
    await ask_question(update, context, user_id)

# Показ результатов
async def show_results(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: str) -> None:
    scores = user_data[user_id]["scores"]
    teamwork_score = sum(scores["teamwork"]) / len(scores["teamwork"])
    logger.info(
        f"Assessment completed for user {user_id}. Scores: {scores}. Final score: {teamwork_score:.2f}/5"
    )
    await update.callback_query.edit_message_text(
        f"Ваша оценка:\n• Командная работа: {teamwork_score:.2f}/5"
    )

# Обработка неизвестных сообщений
async def handle_unknown(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = str(update.effective_user.id)
    chat_id = update.effective_chat.id if update.effective_chat else "N/A"
    text = update.message.text
    logger.warning(f"Unknown command or text received from user {user_id} in chat {chat_id}: {text}")
    await update.message.reply_text("Я не понимаю эту команду. Пожалуйста, используйте кнопки или команды.")

# Основная функция
def main() -> None:
    logger.info("Starting the bot...")
    application = Application.builder().token("7889453188:AAEmb2hKOv6dWxGrb7aWy59I2DSkMXwGhLY").build()

    # Регистрация обработчиков
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("repeat", repeat_command))
    application.add_handler(CallbackQueryHandler(handle_callback))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_unknown))

    application.run_polling()

if __name__ == "__main__":
    logger.info("Initializing bot environment...")
    main()
