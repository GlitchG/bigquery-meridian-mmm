import logging

from faster_whisper import WhisperModel

logger = logging.getLogger(__name__)


class Transcriber:
    def __init__(self, model: str, device: str, compute_type: str, language: str):
        self._language = language
        logger.info("Loading Whisper model '%s' on %s…", model, device)
        self._model = WhisperModel(model, device=device, compute_type=compute_type)
        logger.info("Whisper model ready.")

    def transcribe(self, audio_path: str) -> str:
        segments, info = self._model.transcribe(
            audio_path,
            beam_size=5,
            language=self._language,
            vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 500},
        )
        logger.info(
            "Language detected: %s (%.0f%%)",
            info.language,
            info.language_probability * 100,
        )
        text = " ".join(seg.text.strip() for seg in segments)
        logger.info("Transcript: %d chars", len(text))
        return text
