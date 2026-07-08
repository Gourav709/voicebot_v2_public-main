"""
Lightweight Devanagari → Roman transliterator for FAQ matching.
Converts Hindi script to approximate Roman so it can be matched against
Hinglish examples like "sip pause kya hota hai".

Only used for FAQ scoring — NOT for display or TTS.
"""

# Devanagari character → Roman approximation
_CHAR_MAP = {
    # Vowels
    'अ': 'a',  'आ': 'aa', 'इ': 'i',  'ई': 'ee', 'उ': 'u',
    'ऊ': 'oo', 'ए': 'e',  'ऐ': 'ai', 'ओ': 'o',  'औ': 'au',
    'अं': 'an','अः': 'ah',
    # Vowel signs (matras)
    'ा': 'aa', 'ि': 'i',  'ी': 'ee', 'ु': 'u',  'ू': 'oo',
    'े': 'e',  'ै': 'ai', 'ो': 'o',  'ौ': 'au',
    'ं': 'n',  'ः': 'h',  '्': '',   'ँ': 'n',
    # Consonants
    'क': 'k',  'ख': 'kh', 'ग': 'g',  'घ': 'gh', 'ङ': 'n',
    'च': 'ch', 'छ': 'chh','ज': 'j',  'झ': 'jh', 'ञ': 'n',
    'ट': 't',  'ठ': 'th', 'ड': 'd',  'ढ': 'dh', 'ण': 'n',
    'त': 't',  'थ': 'th', 'द': 'd',  'ध': 'dh', 'न': 'n',
    'प': 'p',  'फ': 'ph', 'ब': 'b',  'भ': 'bh', 'म': 'm',
    'य': 'y',  'र': 'r',  'ल': 'l',  'व': 'v',  'व': 'w',
    'श': 'sh', 'ष': 'sh', 'स': 's',  'ह': 'h',
    'क्ष': 'ksh','त्र': 'tr','ज्ञ': 'gn',
    # Nukta variants (borrowed sounds)
    'क़': 'q',  'ख़': 'kh', 'ग़': 'gh', 'ज़': 'z',  'ड़': 'r',
    'ढ़': 'rh', 'फ़': 'f',  'य़': 'y',
    # Numerals
    '०': '0',  '१': '1',  '२': '2',  '३': '3',  '४': '4',
    '५': '5',  '६': '6',  '७': '7',  '८': '8',  '९': '9',
}

def devanagari_to_roman(text: str) -> str:
    """
    Convert Devanagari script in text to Roman approximation.
    Non-Devanagari characters (English, punctuation, spaces) pass through unchanged.
    
    Example:
        "मेरा SIP pause करना है" → "mera SIP pause karana hai"
    """
    if not text:
        return text

    result = []
    i = 0
    while i < len(text):
        # Try 2-char sequence first (conjuncts, nukta)
        if i + 1 < len(text) and text[i:i+2] in _CHAR_MAP:
            mapped = _CHAR_MAP[text[i:i+2]]
            # Add implicit 'a' after consonant if not followed by matra or halant
            result.append(mapped)
            i += 2
        elif text[i] in _CHAR_MAP:
            mapped = _CHAR_MAP[text[i]]
            result.append(mapped)
            i += 1
        else:
            # Non-Devanagari — pass through as-is
            result.append(text[i])
            i += 1

    return ''.join(result)


def normalize_for_matching(text: str) -> str:
    """
    Normalize text for FAQ matching:
    1. Transliterate any Devanagari to Roman
    2. Lowercase
    3. Strip extra spaces
    
    Use this on user_text before passing to FAQRouter.
    """
    return devanagari_to_roman(text).lower().strip()