from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

user_menu = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Пройти опрос", callback_data="start_poll_compliting")],
        [InlineKeyboardButton(text="Статистика", callback_data="my_statistic")]
    ])

admin_menu = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Группы", callback_data="groups")],
        [InlineKeyboardButton(text="Пользователи", callback_data="users")],
        [InlineKeyboardButton(text="Создать опрос", callback_data="create_poll")],
        [InlineKeyboardButton(text="Проверить статистику", callback_data="statistic")]
    ])

go_to_menu_button = InlineKeyboardButton(text="Назад к опциям", callback_data='start')

go_to_menu_keyboard = InlineKeyboardMarkup(inline_keyboard=[
    [go_to_menu_button]
])

