from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # Telegram
    TELEGRAM_BOT_TOKEN: str

    # ClickUp
    CLICKUP_API_TOKEN: str
    CLICKUP_LIST_ID: str  # ID списка, куда падают задачи

    # Ollama / Hermes
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "hermes3"

    # Whisper (faster-whisper)
    WHISPER_MODEL: str = "large-v3-turbo"
    WHISPER_DEVICE: str = "cuda"          # "cuda" или "cpu"
    WHISPER_COMPUTE_TYPE: str = "float16" # "float16" на GPU, "int8" на CPU
    WHISPER_LANGUAGE: str = "ru"

    # Максимальный размер аудиофайла (МБ)
    AUDIO_MAX_SIZE_MB: int = 200


settings = Settings()
