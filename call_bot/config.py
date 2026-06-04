from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # Telegram
    TELEGRAM_BOT_TOKEN: str

    # Asana
    ASANA_ACCESS_TOKEN: str
    ASANA_WORKSPACE_GID: str
    ASANA_PROJECT_GID: str  # default project for new tasks

    # Ollama / Hermes
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "hermes3"

    # Whisper (faster-whisper)
    WHISPER_MODEL: str = "large-v3-turbo"
    WHISPER_DEVICE: str = "cuda"          # "cuda" or "cpu"
    WHISPER_COMPUTE_TYPE: str = "float16" # "float16" on GPU, "int8" on CPU
    WHISPER_LANGUAGE: str = "ru"

    # Max audio file size the bot will accept (MB)
    AUDIO_MAX_SIZE_MB: int = 200


settings = Settings()
