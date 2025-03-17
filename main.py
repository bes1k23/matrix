import json
import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Загрузка вопросов из JSON
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
    progress = int((current_index / total_questions) * 5)
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
        user_data[user_id] = {"current_competency_index": 0, "scores": {}}

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
        user_data[user_id] = {"current_competency_index": 0, "scores": {}}

    user_data[user_id]["current_competency_index"] = 0
    user_data[user_id]["current_question_index"] = 0
    await ask_question(update, context, user_id)

# Задать вопрос
async def ask_question(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: str) -> None:
    current_competency_index = user_data[user_id]["current_competency_index"]
    competency = QUESTIONS[current_competency_index]
    questions = competency["questions"]
    current_index = user_data[user_id].get("current_question_index", 0)

    if current_index >= len(questions):
        await finish_competency(update, context, user_id)
        return

    question = questions[current_index]

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

    progress_bar = create_progress_bar(current_index + 1, len(questions))
    message = (
        f"Компетенция: {competency['name'].capitalize()}\n"
        f"Вопрос {current_index + 1} из {len(questions)} 🔍\n"
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
    current_competency_index = user_data[user_id]["current_competency_index"]
    competency = QUESTIONS[current_competency_index]["name"]

    # Инициализация scores как списка, если еще не инициализирован
    scores = user_data[user_id]["scores"].setdefault(competency, [])

    # Проверка типа данных
    if isinstance(scores, float):
        logger.error(f"Unexpected float value for scores: {scores}. Resetting to list.")
        scores = []
        user_data[user_id]["scores"][competency] = scores

    # Добавление ответа
    try:
        scores.append(answer_index + 1)
    except AttributeError as e:
        logger.error(f"Error appending to scores: {e}")
        scores = []  # Сброс на случай ошибки
        scores.append(answer_index + 1)

    # Переход к следующему вопросу
    user_data[user_id]["current_question_index"] += 1
    await ask_question(update, context, user_id)

# Завершение компетенции
async def finish_competency(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: str) -> None:
    current_competency_index = user_data[user_id]["current_competency_index"]
    competency = QUESTIONS[current_competency_index]["name"]

    # Сохраняем результаты для текущей компетенции
    scores = user_data[user_id]["scores"].get(competency, [])
    average_score = sum(scores) / len(scores) if scores else 0
    user_data[user_id]["scores"][competency] = average_score

    # Переходим к следующей компетенции
    current_competency_index += 1
    if current_competency_index < len(QUESTIONS):
        user_data[user_id]["current_competency_index"] = current_competency_index
        user_data[user_id]["current_question_index"] = 0
        await ask_question(update, context, user_id)
    else:
        # Все компетенции завершены
        await show_final_results(update, context, user_id)

# Показ итоговых результатов
async def show_final_results(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: str) -> None:
    scores = user_data[user_id]["scores"]

    message = "📊 Итоговые результаты:\n"
    for competency, score in scores.items():
        message += f"• {competency.capitalize()}: {score:.2f}/5\n"

    overall_score = sum(scores.values()) / len(scores) if scores else 0
    message += f"\nОбщий уровень: {overall_score:.2f}/5\n"

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
