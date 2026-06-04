# Call Recording → ClickUp Automation

Ты обрабатываешь записи звонков и создаёшь задачи в ClickUp.

Когда пользователь кидает аудиофайл — запускай полный пайплайн ниже.
Не жди дополнительных команд, делай всё сам от начала до конца.

---

## Что нужно сделать с каждым файлом

### 1. Расшифровка

Запусти faster-whisper. Модель уже загружена локально.

```python
from faster_whisper import WhisperModel

model = WhisperModel("large-v3-turbo", device="cuda", compute_type="float16")
segments, info = model.transcribe(
    "путь/к/файлу.ogg",
    beam_size=5,
    language="ru",
    vad_filter=True,
)
transcript = " ".join(seg.text.strip() for seg in segments)
```

Если `device="cuda"` не работает — переключись на `device="cpu", compute_type="int8"`.

---

### 2. Анализ через Hermes (Ollama)

Ollama крутится локально на `http://localhost:11434`.
Модель: `hermes3` (или та, что указана в `.env` как `OLLAMA_MODEL`).

Отправь расшифровку с этим промптом:

**System:**
```
Ты ассистент по анализу деловых звонков. Извлекаешь структурированные данные из расшифровок переговоров.
Отвечай строго в формате JSON — никакого лишнего текста.
```

**User:**
```
Проанализируй расшифровку звонка и извлеки задачи и договорённости.

Сегодня: {YYYY-MM-DD}

Расшифровка:
{transcript}

Верни JSON в ТОЧНО таком формате:
{
  "summary": "краткое содержание звонка — 2-3 предложения",
  "participants": ["имя или роль 1", "имя или роль 2"],
  "tasks": [
    {
      "title": "конкретное название задачи для трекера",
      "description": "подробности или пустая строка",
      "due_date": "YYYY-MM-DD или null"
    }
  ]
}

Включай только МОИ задачи (задачи говорящего, от первого лица).
Относительные дедлайны («к четвергу», «до конца недели») переводи в точные даты.
Если дедлайна нет — null.
```

Вызов через httpx:
```python
import httpx, json
from datetime import date

resp = httpx.post(
    "http://localhost:11434/api/chat",
    json={
        "model": "hermes3",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "stream": False,
        "format": "json",
    },
    timeout=300,
)
result = json.loads(resp.json()["message"]["content"])
```

---

### 3. Создание задач в ClickUp

Токен и List ID лежат в `.env` (`CLICKUP_API_TOKEN`, `CLICKUP_LIST_ID`).

```python
import httpx
from datetime import datetime

headers = {
    "Authorization": clickup_token,
    "Content-Type": "application/json",
}

for task in result["tasks"]:
    body = {
        "name": task["title"],
        "description": task.get("description", ""),
    }
    if task.get("due_date"):
        dt = datetime.strptime(task["due_date"], "%Y-%m-%d")
        body["due_date"] = int(dt.timestamp() * 1000)

    resp = httpx.post(
        f"https://api.clickup.com/api/v2/list/{list_id}/task",
        headers=headers,
        json=body,
    )
    resp.raise_for_status()
```

---

### 4. Вывод результата

После обработки покажи пользователю:

```
✅ Звонок обработан

👥 Участники: Имя1, Имя2

📋 Краткое содержание:
<summary>

✅ Создано задач в ClickUp: N
1. Название задачи — до YYYY-MM-DD
2. Название задачи
...
```

---

## Конфиг (.env)

Все секреты в `.env` в корне этого проекта:

```
TELEGRAM_BOT_TOKEN=...
CLICKUP_API_TOKEN=pk_...
CLICKUP_LIST_ID=...
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=hermes3
WHISPER_MODEL=large-v3-turbo
WHISPER_DEVICE=cuda
WHISPER_COMPUTE_TYPE=float16
WHISPER_LANGUAGE=ru
```

Читай через `python-dotenv`:
```python
from dotenv import load_dotenv
import os
load_dotenv()
token = os.getenv("CLICKUP_API_TOKEN")
```

---

## Поддерживаемые форматы аудио

`.ogg`, `.mp3`, `.m4a`, `.wav`, `.flac`, `.opus` — faster-whisper умеет все.

---

## Если что-то пошло не так

- Ollama не отвечает → проверь `ollama serve` и `ollama list`
- CUDA недоступна → поменяй на `device="cpu", compute_type="int8"`
- JSON от Hermes кривой → вытащи первый `{...}` блок через `re.search(r'\{.*\}', text, re.DOTALL)`
- ClickUp 401 → токен протух, обнови на https://app.clickup.com/settings/apps
