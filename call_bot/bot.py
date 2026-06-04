"""
Telegram bot: audio → Whisper → Hermes → Asana.

Flow:
  1. User sends voice / audio file / audio document
  2. Bot transcribes with faster-whisper
  3. Hermes (via Ollama) extracts summary + tasks
  4. Bot shows results in chat
  5. User sends /asana → tasks are created in Asana
"""

import html
import logging
import os
import tempfile
from pathlib import Path

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from asana_client import AsanaClient
from config import settings
from llm import HermesClient
from transcriber import Transcriber

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(name)-20s  %(levelname)s  %(message)s",
)
logger = logging.getLogger(__name__)

# --- singletons loaded once at startup ---
transcriber = Transcriber(
    model=settings.WHISPER_MODEL,
    device=settings.WHISPER_DEVICE,
    compute_type=settings.WHISPER_COMPUTE_TYPE,
    language=settings.WHISPER_LANGUAGE,
)
hermes = HermesClient(base_url=settings.OLLAMA_BASE_URL, model=settings.OLLAMA_MODEL)
asana = AsanaClient(
    token=settings.ASANA_ACCESS_TOKEN,
    workspace_gid=settings.ASANA_WORKSPACE_GID,
    default_project_gid=settings.ASANA_PROJECT_GID,
)

# pending tasks per chat_id — survives until /asana is called
_pending: dict[int, list[dict]] = {}


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _format_task_list(tasks: list[dict]) -> str:
    lines = []
    for i, t in enumerate(tasks, 1):
        due = f" — до {t['due_date']}" if t.get("due_date") else ""
        lines.append(f"{i}. {html.escape(t['title'])}{due}")
    return "\n".join(lines)


async def _get_audio_file(message):
    """Return (TelegramFile, suffix) for any audio-type message, or None."""
    if message.voice:
        return await message.voice.get_file(), ".ogg"
    if message.audio:
        suffix = Path(message.audio.file_name or "audio.mp3").suffix or ".mp3"
        return await message.audio.get_file(), suffix
    if message.document:
        mime = message.document.mime_type or ""
        if mime.startswith("audio/"):
            suffix = Path(message.document.file_name or "audio.bin").suffix or ".bin"
            return await message.document.get_file(), suffix
    return None, None


# ---------------------------------------------------------------------------
# handlers
# ---------------------------------------------------------------------------

async def cmd_start(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text(
        "Привет! Отправь мне запись звонка — голосовое сообщение или аудиофайл.\n\n"
        "Я расшифрую речь, извлеку задачи и покажу тебе.\n"
        "Потом отправь /asana — и задачи появятся в Asana.\n\n"
        "/status — показать текущие задачи в очереди\n"
        "/clear  — сбросить очередь"
    )


async def cmd_status(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    tasks = _pending.get(update.effective_chat.id)
    if not tasks:
        await update.effective_message.reply_text("Очередь пуста. Отправь аудио.")
        return
    text = f"<b>Задачи в очереди ({len(tasks)}):</b>\n" + _format_task_list(tasks)
    await update.effective_message.reply_text(text, parse_mode="HTML")


async def cmd_clear(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    _pending.pop(update.effective_chat.id, None)
    await update.effective_message.reply_text("Очередь сброшена.")


async def handle_audio(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    tg_file, suffix = await _get_audio_file(message)
    if tg_file is None:
        return

    # Check file size
    if tg_file.file_size and tg_file.file_size > settings.AUDIO_MAX_SIZE_MB * 1024 * 1024:
        await message.reply_text(
            f"Файл слишком большой (лимит {settings.AUDIO_MAX_SIZE_MB} МБ)."
        )
        return

    status = await message.reply_text("🎙 Получил, расшифровываю…")
    tmp_path = None

    try:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp_path = tmp.name
        await tg_file.download_to_drive(tmp_path)

        transcript = transcriber.transcribe(tmp_path)
        if not transcript.strip():
            await status.edit_text("Ничего не удалось расшифровать — файл тихий или пустой.")
            return

        await status.edit_text("🤖 Анализирую разговор…")
        result = await hermes.extract_tasks(transcript)

        tasks = result["tasks"]
        _pending[update.effective_chat.id] = tasks

        summary = html.escape(result["summary"])
        task_block = _format_task_list(tasks) if tasks else "Задач не найдено."

        text = (
            f"<b>Краткое содержание</b>\n{summary}\n\n"
            f"<b>Задачи ({len(tasks)})</b>\n{task_block}\n\n"
            f"Отправь /asana чтобы создать задачи в Asana."
        )
        await status.edit_text(text, parse_mode="HTML")

    except Exception as exc:
        logger.exception("Error processing audio")
        await status.edit_text(f"❌ Ошибка: {html.escape(str(exc))}", parse_mode="HTML")
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)


async def cmd_asana(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    tasks = _pending.get(chat_id)

    if not tasks:
        await update.effective_message.reply_text(
            "Нечего отправлять. Сначала пришли аудиозапись."
        )
        return

    msg = await update.effective_message.reply_text(
        f"⏳ Создаю {len(tasks)} задач(и) в Asana…"
    )

    created, errors = [], []
    for task in tasks:
        try:
            data = await asana.create_task(
                name=task["title"],
                notes=task.get("description", ""),
                due_on=task.get("due_date") or None,
            )
            created.append(data)
        except Exception as exc:
            logger.exception("Failed to create task: %s", task["title"])
            errors.append(f"❌ {html.escape(task['title'])}: {html.escape(str(exc))}")

    _pending.pop(chat_id, None)

    lines = [f"✅ Создано задач: <b>{len(created)}</b>"]
    for t in created:
        url = t.get("permalink_url", "")
        name = html.escape(t["name"])
        lines.append(f"• {name}" + (f'\n  <a href="{url}">открыть</a>' if url else ""))
    lines.extend(errors)

    await msg.edit_text("\n".join(lines), parse_mode="HTML")


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> None:
    app = Application.builder().token(settings.TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("clear", cmd_clear))
    app.add_handler(CommandHandler("asana", cmd_asana))
    app.add_handler(
        MessageHandler(
            filters.VOICE | filters.AUDIO | filters.Document.ALL,
            handle_audio,
        )
    )

    logger.info("Bot is running. Ctrl+C to stop.")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
