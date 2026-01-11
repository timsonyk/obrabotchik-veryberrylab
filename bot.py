import os
import logging
from io import BytesIO
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile, BufferedInputFile, ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from dotenv import load_dotenv
import asyncio

from image_processor import process_image_stream
from PIL import Image
from io import BytesIO

# Загрузка переменных окружения
load_dotenv()

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Инициализация бота с увеличенным таймаутом для больших файлов
BOT_TOKEN = os.getenv("BOTKEY")
if not BOT_TOKEN:
    raise ValueError("BOTKEY не найден в .env файле!")

# Пароль для авторизации
AUTH_PASSWORD = "CHANGE_ME"

# Таймаут 5 минут для отправки больших файлов (~17 МБ)
session = AiohttpSession(timeout=300)
bot = Bot(token=BOT_TOKEN, session=session)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# Состояния
class UserStates(StatesGroup):
    waiting_for_password = State()
    waiting_for_photo = State()
    waiting_for_custom_prompt = State()

# Хранилище настроек пользователей (в продакшене использовать БД)
user_settings = {}

# Хранилище авторизованных и заблокированных пользователей
authorized_users = set()
blocked_users = set()

# Очередь обработки (только 1 обработка одновременно)
processing_semaphore = asyncio.Semaphore(1)
queue_count = 0  # Счетчик ожидающих в очереди

def get_user_settings(user_id: int) -> dict:
    """Получить настройки пользователя"""
    if user_id not in user_settings:
        user_settings[user_id] = {
            'variants_count': 5,  # По умолчанию 5 вариантов
            'use_custom_prompt': False,  # Использовать кастомный промпт
            'custom_prompt': None  # Кастомный промпт
        }
    return user_settings[user_id]

def get_persistent_keyboard() -> ReplyKeyboardMarkup:
    """Постоянная клавиатура внизу экрана"""
    keyboard = [[KeyboardButton(text="🏠 Главное меню")]]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

def get_main_menu() -> InlineKeyboardMarkup:
    """Главное меню"""
    keyboard = [
        [InlineKeyboardButton(text="📸 Отправить фото", callback_data="send_photo")],
        [InlineKeyboardButton(text="⚙️ Настройки", callback_data="settings")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_settings_menu(user_id: int) -> InlineKeyboardMarkup:
    """Меню настроек"""
    settings = get_user_settings(user_id)

    prompt_status = "Кастомный" if settings['use_custom_prompt'] else "Стандартный"

    keyboard = [
        [InlineKeyboardButton(
            text=f"Количество фото: {settings['variants_count']}",
            callback_data="change_variants"
        )],
        [InlineKeyboardButton(
            text=f"Промпт: {prompt_status}",
            callback_data="change_prompt_mode"
        )],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="main_menu")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_variants_menu() -> InlineKeyboardMarkup:
    """Меню выбора количества вариантов"""
    keyboard = [
        [InlineKeyboardButton(text="1", callback_data="variants_1"),
         InlineKeyboardButton(text="3", callback_data="variants_3"),
         InlineKeyboardButton(text="5", callback_data="variants_5")],
        [InlineKeyboardButton(text="7", callback_data="variants_7"),
         InlineKeyboardButton(text="10", callback_data="variants_10")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="settings")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_prompt_menu(user_id: int) -> InlineKeyboardMarkup:
    """Меню выбора типа промпта"""
    settings = get_user_settings(user_id)
    has_custom = settings['custom_prompt'] is not None

    keyboard = [
        [InlineKeyboardButton(text="📝 Стандартный промпт", callback_data="prompt_default")],
    ]

    if has_custom:
        keyboard.append([InlineKeyboardButton(text="✏️ Использовать свой промпт", callback_data="prompt_custom")])
        keyboard.append([InlineKeyboardButton(text="🔄 Изменить свой промпт", callback_data="prompt_new")])
    else:
        keyboard.append([InlineKeyboardButton(text="➕ Добавить свой промпт", callback_data="prompt_new")])

    keyboard.append([InlineKeyboardButton(text="◀️ Назад", callback_data="settings")])

    return InlineKeyboardMarkup(inline_keyboard=keyboard)

@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    """Обработка команды /start"""
    user_id = message.from_user.id

    # Проверяем, заблокирован ли пользователь
    if user_id in blocked_users:
        await message.answer("🚫 Доступ запрещен.")
        return

    # Проверяем, авторизован ли пользователь
    if user_id in authorized_users:
        user_name = message.from_user.first_name
        await message.answer(
            f"👋 С возвращением, {user_name}!\n\n"
            "Выбери действие:",
            reply_markup=get_main_menu()
        )
        await message.answer("⬇️", reply_markup=get_persistent_keyboard())
        return

    # Запрашиваем пароль
    await message.answer(
        "🔐 Для доступа к боту введите пароль:"
    )
    await state.set_state(UserStates.waiting_for_password)

@dp.message(UserStates.waiting_for_password)
async def check_password(message: types.Message, state: FSMContext):
    """Проверка пароля"""
    user_id = message.from_user.id

    if message.text == AUTH_PASSWORD:
        # Пароль верный - авторизуем
        authorized_users.add(user_id)
        await state.clear()

        user_name = message.from_user.first_name
        await message.answer(
            f"✅ Авторизация успешна!\n\n"
            f"👋 Привет, {user_name}!\n\n"
            "Я бот для обработки фотографий клубники в шоколаде.\n"
            "Отправь мне фото, и я создам несколько улучшенных вариантов!\n\n"
            "Выбери действие:",
            reply_markup=get_main_menu()
        )
        await message.answer("⬇️", reply_markup=get_persistent_keyboard())
    else:
        # Пароль неверный - блокируем
        blocked_users.add(user_id)
        await state.clear()
        await message.answer("🚫 Неверный пароль. Доступ запрещен.")

@dp.message(lambda m: m.text == "🏠 Главное меню")
async def handle_main_menu_button(message: types.Message, state: FSMContext):
    """Обработка кнопки Главное меню"""
    user_id = message.from_user.id

    if user_id in blocked_users:
        await message.answer("🚫 Доступ запрещен.")
        return

    if user_id not in authorized_users:
        await message.answer("🔐 Для доступа к боту введите /start")
        return

    await state.clear()
    await message.answer(
        "Выбери действие:",
        reply_markup=get_main_menu()
    )

async def check_auth(user_id: int) -> bool:
    """Проверка авторизации пользователя"""
    return user_id in authorized_users and user_id not in blocked_users

@dp.callback_query(lambda c: c.data == "main_menu")
async def show_main_menu(callback: types.CallbackQuery):
    """Показать главное меню"""
    if not await check_auth(callback.from_user.id):
        await callback.answer("🚫 Доступ запрещен", show_alert=True)
        return

    await callback.message.edit_text(
        "Выбери действие:",
        reply_markup=get_main_menu()
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data == "send_photo")
async def request_photo(callback: types.CallbackQuery, state: FSMContext):
    """Запросить фото у пользователя"""
    if not await check_auth(callback.from_user.id):
        await callback.answer("🚫 Доступ запрещен", show_alert=True)
        return

    await callback.message.answer(
        "📸 Отправь мне фотографию, которую нужно обработать.\n"
        "Пожалуйста, отправь фото как документ (без сжатия) для лучшего качества."
    )
    await state.set_state(UserStates.waiting_for_photo)
    await callback.answer()

@dp.callback_query(lambda c: c.data == "settings")
async def show_settings(callback: types.CallbackQuery):
    """Показать настройки"""
    user_id = callback.from_user.id
    if not await check_auth(user_id):
        await callback.answer("🚫 Доступ запрещен", show_alert=True)
        return

    await callback.message.edit_text(
        "⚙️ Настройки:",
        reply_markup=get_settings_menu(user_id)
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data == "change_variants")
async def change_variants(callback: types.CallbackQuery):
    """Изменить количество вариантов"""
    if not await check_auth(callback.from_user.id):
        await callback.answer("🚫 Доступ запрещен", show_alert=True)
        return

    await callback.message.edit_text(
        "Выбери количество генерируемых фотографий:",
        reply_markup=get_variants_menu()
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("variants_"))
async def set_variants(callback: types.CallbackQuery):
    """Установить количество вариантов"""
    user_id = callback.from_user.id
    if not await check_auth(user_id):
        await callback.answer("🚫 Доступ запрещен", show_alert=True)
        return

    count = int(callback.data.split("_")[1])

    settings = get_user_settings(user_id)
    settings['variants_count'] = count

    await callback.message.edit_text(
        f"✅ Количество фото изменено на {count}",
        reply_markup=get_settings_menu(user_id)
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data == "change_prompt_mode")
async def change_prompt_mode(callback: types.CallbackQuery):
    """Открыть меню выбора промпта"""
    user_id = callback.from_user.id
    if not await check_auth(user_id):
        await callback.answer("🚫 Доступ запрещен", show_alert=True)
        return

    await callback.message.edit_text(
        "Выбери тип промпта для обработки изображений:",
        reply_markup=get_prompt_menu(user_id)
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data == "prompt_default")
async def set_default_prompt(callback: types.CallbackQuery):
    """Установить стандартный промпт"""
    user_id = callback.from_user.id
    if not await check_auth(user_id):
        await callback.answer("🚫 Доступ запрещен", show_alert=True)
        return

    settings = get_user_settings(user_id)
    settings['use_custom_prompt'] = False

    await callback.message.edit_text(
        "✅ Установлен стандартный промпт",
        reply_markup=get_settings_menu(user_id)
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data == "prompt_custom")
async def set_custom_prompt(callback: types.CallbackQuery):
    """Использовать кастомный промпт"""
    user_id = callback.from_user.id
    if not await check_auth(user_id):
        await callback.answer("🚫 Доступ запрещен", show_alert=True)
        return

    settings = get_user_settings(user_id)

    if settings['custom_prompt'] is None:
        await callback.answer("Сначала добавьте свой промпт!", show_alert=True)
        return

    settings['use_custom_prompt'] = True

    await callback.message.edit_text(
        "✅ Установлен ваш кастомный промпт",
        reply_markup=get_settings_menu(user_id)
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data == "prompt_new")
async def request_new_prompt(callback: types.CallbackQuery, state: FSMContext):
    """Запросить новый промпт"""
    if not await check_auth(callback.from_user.id):
        await callback.answer("🚫 Доступ запрещен", show_alert=True)
        return

    await callback.message.answer(
        "Отправь свой промпт для обработки изображений.\n\n"
        "Промпт должен описывать, как нужно обработать изображение.\n"
        "Например: 'Создай реалистичное фото с мягким освещением и белым фоном'\n\n"
        "Для отмены отправь /cancel"
    )
    await state.set_state(UserStates.waiting_for_custom_prompt)
    await callback.answer()

@dp.message(UserStates.waiting_for_custom_prompt)
async def save_custom_prompt(message: types.Message, state: FSMContext):
    """Сохранить кастомный промпт"""
    user_id = message.from_user.id
    if not await check_auth(user_id):
        await message.answer("🚫 Доступ запрещен.")
        await state.clear()
        return

    if message.text == "/cancel":
        await message.answer(
            "Отменено",
            reply_markup=get_main_menu()
        )
        await state.clear()
        return

    settings = get_user_settings(user_id)
    settings['custom_prompt'] = message.text
    settings['use_custom_prompt'] = True

    await message.answer(
        f"✅ Промпт сохранен!\n\n"
        f"Ваш промпт:\n{message.text[:100]}{'...' if len(message.text) > 100 else ''}",
        reply_markup=get_settings_menu(user_id)
    )
    await state.clear()

@dp.message(lambda m: m.photo or (m.document and m.document.mime_type and m.document.mime_type.startswith('image/')))
async def handle_any_photo(message: types.Message, state: FSMContext):
    """Обработка любого фото сразу при отправке"""
    global queue_count
    user_id = message.from_user.id

    # Проверяем авторизацию
    if not await check_auth(user_id):
        await message.answer("🚫 Доступ запрещен. Введите /start для авторизации.")
        return

    # Сбрасываем состояние если было
    await state.clear()

    # Получаем file_id
    if message.photo:
        file_id = message.photo[-1].file_id
    else:
        file_id = message.document.file_id

    # Проверяем очередь
    if processing_semaphore.locked():
        queue_count += 1
        queue_pos = queue_count
        processing_msg = await message.answer(f"⏳ Сервер занят. Вы {queue_pos}-й в очереди, подождите...")
    else:
        processing_msg = await message.answer("⏳ Обрабатываю фото...")

    # Ждем своей очереди
    async with processing_semaphore:
        if queue_count > 0:
            queue_count -= 1

        try:
            await processing_msg.edit_text("⏳ Скачиваю фото...")

            file = await bot.get_file(file_id)
            file_bytes = await bot.download_file(file.file_path)

            # Получаем настройки пользователя
            settings = get_user_settings(user_id)
            variants_count = settings['variants_count']

            # Определяем какой промпт использовать
            custom_prompt = None
            if settings['use_custom_prompt'] and settings['custom_prompt']:
                custom_prompt = settings['custom_prompt']

            await processing_msg.edit_text(
                f"⏳ Генерирую {variants_count} вариантов...\n"
                "Отправляю каждый по мере готовности!"
            )

            # Обрабатываем и отправляем по мере готовности
            sent_count = 0
            async for idx, img_bytes in process_image_stream(file_bytes, variants_count, custom_prompt):
                sent_count += 1

                # Создаем сжатое превью (макс 1280px, JPEG качество 85)
                img = Image.open(BytesIO(img_bytes))
                img.thumbnail((1280, 1280), Image.Resampling.LANCZOS)
                preview_buffer = BytesIO()
                img.save(preview_buffer, format='JPEG', quality=85)
                preview_bytes = preview_buffer.getvalue()

                # Отправляем превью (сжатое)
                await message.answer_photo(
                    BufferedInputFile(preview_bytes, filename=f"preview_{idx}.jpg"),
                    caption=f"Вариант {idx} (превью)"
                )

                # Отправляем оригинал (без сжатия)
                await message.answer_document(
                    BufferedInputFile(img_bytes, filename=f"result_{idx}.png"),
                    caption=f"Вариант {idx} (полное качество)"
                )

            if sent_count == 0:
                await processing_msg.edit_text(
                    "❌ Ошибка при обработке изображения. Попробуйте еще раз.",
                    reply_markup=get_main_menu()
                )
                return

            await processing_msg.edit_text(
                f"✅ Готово! Отправлено {sent_count} вариантов.",
                reply_markup=get_main_menu()
            )

        except Exception as e:
            logger.error(f"Ошибка при обработке фото: {e}")
            await message.answer(
                f"❌ Произошла ошибка: {str(e)}",
                reply_markup=get_main_menu()
            )

async def main():
    """Запуск бота"""
    logger.info("Бот запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
