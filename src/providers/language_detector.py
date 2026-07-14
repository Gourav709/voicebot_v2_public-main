from lingua import Language, LanguageDetectorBuilder


class LanguageDetector:

    def __init__(self):

        self.detector = LanguageDetectorBuilder.from_languages(
            Language.ENGLISH,
            Language.HINDI,
            Language.TAMIL,
            Language.TELUGU,
            Language.BENGALI,
            Language.GUJARATI,
            Language.MARATHI,
            Language.PUNJABI,
            Language.URDU,
        ).build()

    def detect(self, text: str) -> str:

        if not text.strip():
            return "en-IN"

        language = self.detector.detect_language_of(text)

        mapping = {
            Language.ENGLISH: "en-IN",
            Language.HINDI: "hi-IN",
            Language.TAMIL: "ta-IN",
            Language.TELUGU: "te-IN",
            Language.BENGALI: "bn-IN",
            Language.GUJARATI: "gu-IN",
            Language.MARATHI: "mr-IN",
            Language.PUNJABI: "pa-IN",
            Language.URDU: "ur-IN",
        }

        return mapping.get(language, "en-IN")