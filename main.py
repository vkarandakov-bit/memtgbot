import os
import io
import random
import textwrap
import asyncio
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from PIL import Image, ImageDraw, ImageFont

from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID")
CAPTIONS_FILE = os.getenv("CAPTIONS_FILE", "captions.txt")
SAVE_DIR = os.getenv("SAVE_DIR", "./saved_images")
FONT_PATH = os.getenv("FONT_PATH", "fonts/Lobster-Regular.ttf")
FONT_SIZE = int(os.getenv("FONT_SIZE", "48"))

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

user_mems: dict[int, bytes] = {}


def get_random_caption(filepath: str) -> str:
    """Берет рандомную подпись"""
    with open(filepath, "r", encoding="utf-8") as f:
        lines = [line.strip() for line in f if line.strip()]
    return random.choice(lines) if lines else ""


def add_caption_to_image(img_bytes: bytes, caption: str) -> bytes:
    """Рисует подпись на картинке."""
    img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
    draw = ImageDraw.Draw(img)

    # Загрузка шрифта
    try:
        font = ImageFont.truetype(FONT_PATH, FONT_SIZE)
    except (IOError, OSError):
        font = ImageFont.load_default()

    max_width = int(img.width * 0.8)
    words = caption.split()
    lines = []
    current_line = []

    for word in words:
        test_line = " ".join(current_line + [word])
        bbox = draw.textbbox((0, 0), test_line, font=font)
        if bbox[2] - bbox[0] <= max_width:
            current_line.append(word)
        else:
            if current_line:
                lines.append(" ".join(current_line))
            current_line = [word]
    if current_line:
        lines.append(" ".join(current_line))

    if not lines:
        return img_bytes

    total_text_height = 0
    line_heights = []

    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        h = bbox[3] - bbox[1]
        line_heights.append(h)
        total_text_height += h + 10

        y_start = img.height - 20 - total_text_height

    for i, line in enumerate(lines):
        bbox = draw.textbbox((0, 0), line, font=font)
        line_width = bbox[2] - bbox[0]
        x_start = (img.width - line_width) // 2
        draw.text((x_start + 2, y_start + 2), line, fill="black", font=font)
        draw.text((x_start, y_start), line, fill="white", font=font)

        y_start += line_heights[i] + 10

    buffer = io.BytesIO()
    img.save(buffer, format="JPEG")
    buffer.seek(0)
    return buffer.getvalue()


@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    await message.reply("Пришли мне картинку и получишь ее обратно с подписью!")


@dp.message(F.photo)
async def handle_photo(message: types.Message):
    user_id = message.from_user.id
    photo = message.photo[-1]

    file = await bot.get_file(photo.file_id)
    img_bytes = await bot.download_file(file.file_path)

    os.makedirs(SAVE_DIR, exist_ok=True)
    now = datetime.now()
    filename = f"{now.strftime('%Y-%m-%d_%H-%M')}_{user_id}.jpg"
    save_path = os.path.join(SAVE_DIR, filename)
    with open(save_path, "wb") as f:
        f.write(img_bytes)

    caption = get_random_caption(CAPTIONS_FILE)
    mem_bytes = add_caption_to_image(img_bytes, caption)

    user_mems[user_id] = mem_bytes

    buttons = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Поделиться в канале", callback_data="share")],
        [InlineKeyboardButton(text="Не буду делиться", callback_data="skip")]
    ])
    await message.answer_photo(
        photo=io.BytesIO(mem_bytes),
        caption="Готово! Отправить в канал?",
        reply_markup=buttons
    )


@dp.callback_query(F.data == "share")
async def callback_share(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    mem_bytes = user_mems.pop(user_id, None)

    if mem_bytes and CHANNEL_ID:
        await bot.send_photo(
            chat_id=CHANNEL_ID,
            photo=io.BytesIO(mem_bytes),
            caption=f"Мем от @{callback.from_user.username or 'анонима'}"
        )
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.answer("Мем опубликован в канале!")
    else:
        await callback.answer("Не удалось отправить.", show_alert=True)


@dp.callback_query(F.data == "skip")
async def callback_skip(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    user_mems.pop(user_id, None)  # очищаем память
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer("👍 Ок, отправляй ещё!")


if __name__ == "__main__":
    asyncio.run(dp.start_polling(bot))
