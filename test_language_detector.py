from src.providers.language_detector import LanguageDetector

detector = LanguageDetector()

tests = [
    "Hello",
    "How are you?",
    "नमस्ते",
    "मेरी SIP बंद करनी है",
    "என் SIP ஐ நிறுத்த வேண்டும்",
    "నా SIP ఆపాలి",
    "মার SIP বন্ধ করতে চাই",
    "મારી SIP બંધ કરવી છે",
    "माझी SIP बंद करा",
]

for t in tests:
    print(f"{t} ---> {detector.detect(t)}")