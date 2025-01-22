import re
from typing import Callable, Any
from datetime import datetime, timedelta
import os
import sqlite3
import asyncio
from aiogram import Bot, Dispatcher
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from aiogram.fsm.context import FSMContext
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from db import Roles, create_connection, setup_database
from inline_keyboards import admin_menu, user_menu, go_to_menu_keyboard, go_to_menu_button
from states import UserCreation, PollCreation, GroupCreation
from utils import get_admin_user_statistics, get_user_statistics, calculate_attention_score
from dotenv import load_dotenv


load_dotenv()
bot = Bot(
    token=os.getenv('TG_BOT_TOKEN'),
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )

dp = Dispatcher()

conn = create_connection()
cursor = conn.cursor()

def check_is_admin(func: Callable[[Message | CallbackQuery, FSMContext | None], Any]) -> Callable[[Message | CallbackQuery], Any]:
    async def wrapper(message_or_callback: Message | CallbackQuery, *args, **kwards):
        user_telegram_id = message_or_callback.from_user.id
        self_conn = create_connection()
        self_cursor = self_conn.cursor()
        try:
            role = self_cursor.execute("SELECT role FROM users WHERE telegram_id = ?", (user_telegram_id,)).fetchone()
            if role is None or role[0] != 'admin':
                print("Недостаточно прав для выполнения этой функции.")
                return None 
        except Exception as e:
            print(f"Ошибка при проверке прав: {e}")
            return None
        finally:
            self_cursor.close()
        
        return await func(message_or_callback, *args, **kwards)
    return wrapper


@dp.message(Command("start"))
@dp.callback_query(lambda c: c.data == 'start')
async def start(message_or_callback: Message | CallbackQuery):
    telegram_id = message_or_callback.from_user.id
    user = cursor.execute("SELECT role FROM users WHERE telegram_id = ?", (telegram_id,)).fetchone()

    if not user:
        if isinstance(message_or_callback, CallbackQuery):
            await message_or_callback.message.edit_text("Вы не зарегистрированы. Попросите преподавателя добавить вас в систему.")
        else:
            await message_or_callback.answer("Вы не зарегистрированы. Попросите преподавателя добавить вас в систему.")
        return
    
    user_role = user[0]
    markup = user_menu
    message_text = "Выберите опцию из меню!"
    
    if user_role == Roles.admin:
        markup = admin_menu
    
    if isinstance(message_or_callback, CallbackQuery):
        await message_or_callback.message.edit_text(message_text, reply_markup=markup)
    else:
        await message_or_callback.answer(message_text, reply_markup=markup)


@dp.callback_query(lambda c: c.data == "groups")
@check_is_admin
async def get_groups(callback: CallbackQuery, *args, **kwards):
    groups = cursor.execute('SELECT name FROM groups').fetchall()

    formatted_groups = ""
    for i, group in enumerate(groups, start=1):
        formatted_groups += f'{1}. {group}'

    await callback.message.edit_text(f"Список групп:\n{formatted_groups}" if formatted_groups else "Групп нет", reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Создать группу", callback_data='create_group')],
        [go_to_menu_button]
    ]))

@dp.callback_query(lambda c: c.data == "create_group")
@check_is_admin
async def create_group(callback: CallbackQuery, state: FSMContext, *args, **kwards):
    await callback.message.edit_text("Введите название группы. Пример: \"43-ИС\"")
    await state.set_state(GroupCreation.wating_for_group_name)

@dp.message(GroupCreation.wating_for_group_name)
async def process_group_name(message: Message, state: FSMContext):
    user_telegram_id = message.from_user.id
    group_name = message.text.strip()
    group_name_regexp = r"[0-9]{2,3}-[А-я]{2,3}"

    existing_group = cursor.execute('select id from groups where name = ?', (group_name, )).fetchone()
    if existing_group:
        await message.answer(f"Группа с названием {group_name} уже добавлена", reply_markup=go_to_menu_keyboard)
        return
    elif not re.match(group_name_regexp, group_name):
        await message.answer("Название группы не соответствует требованиям. Пример: \"43-ИС\"")
        return

    teacher_id = cursor.execute("SELECT id FROM users WHERE telegram_id = ?", (user_telegram_id,)).fetchone()[0]
    cursor.execute(
        "INSERT INTO groups (name, teacher_id) VALUES (?, ?)",
        (group_name, teacher_id)
    )
    conn.commit()
    await message.answer(f"Группа '{group_name}' успешно создана.", reply_markup=admin_menu)
    state.clear()


@dp.callback_query(lambda c: c.data == "users")
@check_is_admin
async def get_users(callback: CallbackQuery, *args, **kwards):
    groups = cursor.execute('SELECT id, name from groups').fetchall()

    if not groups:
        await callback.answer("Группы не найдены.")
        return

    keyboard = [
            [InlineKeyboardButton(text=group[1], callback_data=f"view_users_list_{group[0]} {group[1]}")]
            for group in groups
        ]
    
    keyboard.append([go_to_menu_button])

    await callback.message.edit_text("Выберите группу для просмотра списка пользователей:", reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))


@dp.callback_query(lambda c: c.data.startswith('view_users_list_'))
@check_is_admin
async def view_users_list_by_group_name(callback: CallbackQuery, *args, **kwards):
    group_id, group_name = callback.data.split('_')[-1].split(' ')
    users = cursor.execute('SELECT full_name FROM users where group_id = ?', (group_id)).fetchall()

    formatted_users = ""
    for i, user in enumerate(users, start=1):
        formatted_users += f'{i}. {user[0]}\n'

    await callback.message.edit_text(f"Список пользователей группы <b>{group_name}</b>:\n{formatted_users}" if formatted_users else "Пользователей нет", reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Добавить нового пользователя", callback_data=f'set_user_group_{group_id} {group_name}')],
        [go_to_menu_button]
    ]))

@dp.callback_query(lambda c: c.data.startswith("set_user_group_"))
@check_is_admin
async def set_user_group(callback: CallbackQuery, state: FSMContext, *args, **kwards):
    group_id, group_name = callback.data.split("_")[-1].split(' ')
    await state.update_data(group_id=group_id, group_name=group_name)

    await callback.message.edit_text(
        f"Введите данные студента в формате:\nФИО Telegram_ID",
        reply_markup=go_to_menu_keyboard
    )

    await state.set_state(UserCreation.waiting_for_user_data)

@dp.message(UserCreation.waiting_for_user_data)
@check_is_admin
async def set_user_data(message: Message, state: FSMContext, *args, **kwards):
    data = await state.get_data()
    group_id = data["group_id"]
    group_name = data["group_name"]

    args = message.text.split(" ")
    if len(args) != 3:
        await message.answer("Формат данных некорректный. Пример: Иван Иванов 123456789")
        return

    first_name, last_name, telegram_id = args
    full_name = f'{first_name} {last_name}'
    try:
        cursor.execute(
            "INSERT INTO users (telegram_id, full_name, role, group_id) VALUES (?, ?, 'user', ?)",
            (telegram_id, full_name, group_id)
        )
        conn.commit()
        await message.answer(f"Студент '{full_name}' успешно добавлен в группу '{group_name}'.", reply_markup=admin_menu)
    except sqlite3.IntegrityError as e:
        print(e);
        await message.answer(f"Студент с Telegram ID {telegram_id} уже существует.")


@dp.callback_query(lambda c: c.data == "create_poll")
@check_is_admin
async def select_group_for_poll(callback: CallbackQuery, *args, **kwards):
    cursor.execute(
        "SELECT id, name FROM groups WHERE teacher_id = (SELECT id FROM users WHERE telegram_id = ?)",
        (callback.from_user.id,)
    )
    groups = cursor.fetchall()

    if not groups:
        await callback.message.edit_text("У вас пока нет групп. Сначала создайте группу.")
        return

    group_markup = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=group[1], callback_data=f"select_group_for_poll_creation_{group[0]}")]
            for group in groups
        ]
    )
    await callback.message.edit_text("Выберите группу для опроса:", reply_markup=group_markup)

@dp.callback_query(lambda c: c.data.startswith("select_group_for_poll_creation_"))
@check_is_admin
async def start_poll_creation(callback: CallbackQuery, state: FSMContext, *args, **kwards):
    group_id = callback.data.split("_")[-1]
    await state.update_data(group_id=group_id)

    await state.set_state(PollCreation.waiting_for_question)
    await callback.message.edit_text("Введите текст вопроса для опроса:")


@dp.message(PollCreation.waiting_for_question)
@check_is_admin
async def set_poll_question(message: Message, state: FSMContext, *args, **kwards):
    await state.update_data(question=message.text, options=[])
    await message.answer("Отлично. Теперь отправляйте варианты ответа (1 сообщение = 1 вариант).")
    await state.set_state(PollCreation.waiting_for_options)


@dp.message(PollCreation.waiting_for_options)
@check_is_admin
async def add_poll_option(message: Message, state: FSMContext, *args, **kwards):
    text = message.text.strip()
    if text.lower() == "готово":
        data = await state.get_data()
        options = data.get("options", [])
        if len(options) < 2:
            await message.answer("Добавьте как минимум два варианта ответа.")
            return
        await state.set_state(PollCreation.waiting_for_correct_option)
        options_markup = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=option, callback_data=f"set_correct_answer_{i}")]
            for i, option in enumerate(options)
        ])
        await message.reply("Варианты записаны", reply_markup=ReplyKeyboardRemove())
        await message.answer("Выберите правильный вариант ответа:", reply_markup=options_markup)
        return

    data = await state.get_data()
    if text in data["options"]:
        await message.answer("Данный вариант ответа уже добавлен.")
        return
    data["options"].append(text)
    await message.answer(f"Вариант ответа добавлен: {text}", reply_markup=ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="Готово")]
    ], resize_keyboard=True))


@dp.callback_query(lambda c: c.data.startswith("set_correct_answer"))
@check_is_admin
async def set_correct_option(callback: CallbackQuery, state: FSMContext, *args, **kwards):
    correct_index = int(callback.data.split("_")[-1])
    await state.update_data(answer_index=correct_index)

    await state.set_state(PollCreation.waiting_for_duration)
    await callback.message.edit_text("Введите длительность опроса в минутах:")


@dp.message(PollCreation.waiting_for_duration)
@check_is_admin
async def set_poll_duration(message: Message, state: FSMContext, *args, **kwards):
    try:
        duration = int(message.text)
    except ValueError:
        await message.answer("Введите корректное число минут.")
        return

    data = await state.get_data()
    options = data["options"]
    question = data["question"]
    answer_index = data["answer_index"]
    group_id = data['group_id']
    answer = options[answer_index]

    expires_at = datetime.now() + timedelta(minutes=duration)
    poll = cursor.execute("""
      INSERT INTO polls (question, group_id, expires_at) VALUES (?, ?, ?) RETURNING id
    """, (question, group_id, expires_at)).fetchone()
    
    poll_id = poll[0]
    for option in options:
        if option == answer:
            cursor.execute("""
            INSERT INTO options (poll_id, value, is_answer) VALUES (?, ?, ?)
            """, (poll_id, answer, 1))
        else:
            cursor.execute("""
                INSERT INTO options (poll_id, value) VALUES (?, ?)
            """, (poll_id, option))

    conn.commit()
    await state.clear()
    await message.answer(f"Опрос создан!\nВопрос: {question}\nДлительность: {duration} минут.", reply_markup=admin_menu)


@dp.callback_query(lambda c: c.data == "start_poll_compliting")
async def start_poll_compliting(callback: CallbackQuery):
    user_telegram_id = callback.from_user.id
    try:
        user = cursor.execute('select users.id from users where telegram_id = ?', (user_telegram_id,)).fetchone()
        if not user:
            await callback.message.edit_text("Не удалось получить ваши данные", reply_markup=go_to_menu_keyboard)
            return
        
        group = cursor.execute("SELECT group_id FROM users WHERE telegram_id = ?", (user_telegram_id,)).fetchone()
        if not group:
            await callback.message.edit_text("Не удалось получить вашу группу.", reply_markup=go_to_menu_keyboard)
            return
        user_group_id = group[0]  
        active_poll = cursor.execute(
            "select polls.id, polls.question from polls where polls.group_id = ? and polls.expires_at > ? and is_active",
            (user_group_id, datetime.now())
        ).fetchone()

        if not active_poll:
            await callback.message.edit_text("Активных опросов нет.", reply_markup=go_to_menu_keyboard)
            return

        poll_id, question = active_poll

        count = cursor.execute("""
            SELECT COUNT(*) FROM user_options 
            WHERE user_id = ? AND option_id IN (
                SELECT id FROM options WHERE poll_id = ?
            )
        """, (user[0], poll_id)).fetchone()

        if count[0] > 0:
            await callback.message.edit_text("Активных опросов нет.", reply_markup=go_to_menu_keyboard)
            return

        options = cursor.execute("SELECT id, value FROM options WHERE poll_id = ?", (poll_id,)).fetchall()
        options_markup = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=str(row[1]), callback_data=f'select_poll_option_{row[0]}')] for row in options
        ])
        await callback.message.edit_text(question, reply_markup=options_markup)
    except Exception as e:
        print(e)


@dp.callback_query(lambda c: c.data.startswith("select_poll_option_"))
async def handle_select_poll_option(callback: CallbackQuery):
    user_telegram_id = callback.from_user.id
    option_id = callback.data.split("_")[-1]

    try:
        student = cursor.execute(
            "SELECT id, attention_score FROM users WHERE telegram_id = ?", 
            (user_telegram_id,)
        ).fetchone()
        
        if not student:
            await callback.message.edit_text(
                "Не удалось получить ваши данные.", 
                reply_markup=go_to_menu_keyboard
            )
            return

        user_id, current_attention_score = student

        # Проверяем, является ли ответ правильным
        is_correct_answer = cursor.execute(
            "SELECT is_answer FROM options WHERE id = ?", 
            (option_id,)
        ).fetchone()[0]

        total_polls_stats = cursor.execute("""
            SELECT 
                COUNT(DISTINCT p.id) as total_polls,
                COUNT(DISTINCT CASE WHEN o.is_answer = 1 THEN p.id END) as correct_polls
            FROM polls p
            JOIN groups g ON p.group_id = (SELECT group_id FROM users WHERE id = ?)
            JOIN options o ON o.poll_id = p.id
            LEFT JOIN user_options uo ON uo.option_id = o.id AND uo.user_id = ?
        """, (user_id, user_id)).fetchone()

        new_attention_score = calculate_attention_score(
            current_attention_score, 
            is_correct_answer, 
            total_polls_stats[0], 
            total_polls_stats[1]
        )

        cursor.execute(
            "INSERT INTO user_options (user_id, option_id) VALUES (?, ?)",
            (user_id, option_id)
        )
        cursor.execute(
            "UPDATE users SET attention_score = ? WHERE id = ?",
            (new_attention_score, user_id)
        )
        conn.commit()

        await callback.message.edit_text(
            f"Ваш ответ учтен! Спасибо.\n", 
            reply_markup=go_to_menu_keyboard
        )

    except Exception as e:
        print(e)
        await callback.message.edit_text(
            "Произошла ошибка. Пожалуйста, попробуйте еще раз.", 
            reply_markup=go_to_menu_keyboard
        )


@dp.callback_query(lambda c: c.data.startswith("my_statistic"))
async def user_stats_handler(callback: CallbackQuery):
    user_stats = await get_user_statistics(callback.from_user.id, cursor)
    if user_stats:
        await callback.message.edit_text(f"""
Статистика пользователя:
👤 Имя: {user_stats['full_name']}
📊 Группа: {user_stats['group_name']}
🏆 Коэфф. внимательности: {user_stats['attention_score']}
✅ Пройдено опросов: {user_stats['completed_polls']}
📈 Процент участия: {user_stats['completion_rate']}%
🎯 Процент правильных ответов: {user_stats['correct_answers_rate']}%
""", reply_markup=go_to_menu_keyboard)

@dp.callback_query(lambda c: c.data.startswith("statistic"))
@check_is_admin
async def admin_stats_handler(callback: CallbackQuery, *args, **kwards):
    users_stats = await get_admin_user_statistics(cursor)
    stats_text = ""
    
    for user in users_stats:
        stats_text += f"""
👤 {user['full_name']}
📊 Группа: {user['group_name']}
🏆 Внимательность: {user['attention_score']}
📝 Всего опросов: {user['total_polls']}
✅ Пройдено опросов: {user['completed_polls']}
📈 Процент участия: {user['completion_rate']}%
🎯 Процент правильных ответов: {user['correct_answers_rate']}%
---
"""
    await callback.message.edit_text(stats_text if stats_text else "Пользователей нет", reply_markup=go_to_menu_keyboard)
    await callback.message.answer()



async def main():
    setup_database(conn=conn)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
