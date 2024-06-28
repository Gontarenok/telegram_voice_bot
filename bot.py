import os
import io
from openai import OpenAI
from aiogram import Bot, Dispatcher, types, F
from aiogram.types import InputFile, ContentType, FSInputFile
from aiogram.utils.chat_action import ChatActionSender
import aiofiles
import asyncio
from config import settings
from pathlib import Path

# Инициализация бота и диспетчера
bot = Bot(token=settings.telegram_token)
dp = Dispatcher()

# Инициализация клиента OpenAI
client = OpenAI(api_key=settings.openai_api_key)

# Создание помощника (Assistant)
async def create_assistant():
    assistant = client.beta.assistants.create(
        name="Telegram voice bot",
        instructions="You are a personal assistant answering voice messages in a telegram bot",
        model="gpt-4o",
    )
    return assistant


# Обработчик для голосовых сообщений
@dp.message(F.content_type == ContentType.VOICE)
async def handle_voice(message: types.Message, bot: Bot):
    global client
    voice = message.voice
    voice_path = f"voice/{voice.file_id}.oga"
    await bot.download(file=voice.file_id, destination=voice_path)

    async with aiofiles.open(voice_path, 'rb') as audio_file:
        audio_content = await audio_file.read()

    buffer = io.BytesIO(audio_content)
    buffer.name = "voice.oga"

    # Конвертация голосового сообщения в текст с помощью Whisper
    transcription = client.audio.transcriptions.create(
        model="whisper-1",
        file=buffer
    )
    question_text = transcription.text

    # Создание потока (Thread) для общения с ассистентом
    thread = client.beta.threads.create()

    # Добавление сообщения пользователя в поток
    client_message = client.beta.threads.messages.create(
        thread_id=thread.id,
        role="user",
        content=question_text
    )

    # Создание и выполнение запуска (Run) для получения ответа от ассистента
    assistant = await create_assistant()
    run = client.beta.threads.runs.create_and_poll(
        thread_id=thread.id,
        assistant_id=assistant.id,
    )

    if run.status == 'completed':
        messages = client.beta.threads.messages.list(thread_id=thread.id)
        answer_text = ''
        for msg in messages.data:
            if msg.role == 'assistant':
                for content_block in msg.content:
                    answer_text += content_block.text.value
                break
        print(answer_text)
    else:
        answer_text = "Sorry, I couldn't process your request."

    # Озвучивание ответа с помощью TTS API
    audio_path = Path(f"audio/{voice.file_id}_response.opus")
    tts_response = client.audio.speech.create(
        model="tts-1",
        voice="alloy",
        input=answer_text
    )

    # with open(audio_path, 'wb') as f:
    #     f.write(tts_response.content)

    tts_response.stream_to_file(audio_path)

    # response_voice = FSInputFile(path=f"audio/{voice.file_id}_response.ogg")
    # await bot.send_audio(chat_id=message.chat.id, audio=response_voice)

    async with ChatActionSender.record_voice(message.chat.id, bot):
        response_voice = FSInputFile(path=f"audio/{voice.file_id}_response.opus")
        await bot.send_voice(chat_id=message.chat.id, voice=response_voice)


    # Удаление временных файлов
    os.remove(voice_path)
    os.remove(audio_path)

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())