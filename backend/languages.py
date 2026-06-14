"""ISO 639 language data and filename-based language detection.

`LANGUAGES` is the canonical list of human-language entries — used in the
admin language dropdown and as the lookup table for filename-based
auto-detection of subtitle language codes.

`detect_language_from_filename(name)` inspects a subtitle filename
(e.g. `Episode01.ja-jp.srt`, `[ROM]subtitle.srt`, `Romanian.srt`) and
returns `{"language": <iso639-1>, "label": <human label>}`.  When no
language can be confidently identified it falls back to
`{"language": "und", "label": "Unknown"}`.
"""
from __future__ import annotations

import re
from typing import Dict, List


# ---------------------------------------------------------------------------
# Languages (≥190 entries).  iso639-1 where it exists, else iso639-2/T.
# Keep this exhaustive enough that the EditVideo dropdown can show "all the
# Languages from the world" the user asked for.  Native name shown in
# parentheses helps users pick the right entry even when their UI is in
# another language.
# ---------------------------------------------------------------------------
LANGUAGES: List[Dict[str, str]] = [
    {"code": "ab", "label": "Abkhazian (аҧсуа)"},
    {"code": "aa", "label": "Afar (Afaraf)"},
    {"code": "af", "label": "Afrikaans"},
    {"code": "ak", "label": "Akan"},
    {"code": "sq", "label": "Albanian (Shqip)"},
    {"code": "am", "label": "Amharic (አማርኛ)"},
    {"code": "ar", "label": "Arabic (العربية)"},
    {"code": "an", "label": "Aragonese"},
    {"code": "hy", "label": "Armenian (Հայերեն)"},
    {"code": "as", "label": "Assamese (অসমীয়া)"},
    {"code": "av", "label": "Avaric"},
    {"code": "ae", "label": "Avestan"},
    {"code": "ay", "label": "Aymara"},
    {"code": "az", "label": "Azerbaijani (Azərbaycan dili)"},
    {"code": "bm", "label": "Bambara"},
    {"code": "ba", "label": "Bashkir"},
    {"code": "eu", "label": "Basque (Euskara)"},
    {"code": "be", "label": "Belarusian (Беларуская)"},
    {"code": "bn", "label": "Bengali (বাংলা)"},
    {"code": "bh", "label": "Bihari"},
    {"code": "bi", "label": "Bislama"},
    {"code": "bs", "label": "Bosnian"},
    {"code": "br", "label": "Breton"},
    {"code": "bg", "label": "Bulgarian (Български)"},
    {"code": "my", "label": "Burmese (မြန်မာစာ)"},
    {"code": "ca", "label": "Catalan (Català)"},
    {"code": "ch", "label": "Chamorro"},
    {"code": "ce", "label": "Chechen"},
    {"code": "ny", "label": "Chichewa"},
    {"code": "zh", "label": "Chinese (中文)"},
    {"code": "zh-Hans", "label": "Chinese Simplified (简体中文)"},
    {"code": "zh-Hant", "label": "Chinese Traditional (繁體中文)"},
    {"code": "cv", "label": "Chuvash"},
    {"code": "kw", "label": "Cornish"},
    {"code": "co", "label": "Corsican"},
    {"code": "cr", "label": "Cree"},
    {"code": "hr", "label": "Croatian (Hrvatski)"},
    {"code": "cs", "label": "Czech (Čeština)"},
    {"code": "da", "label": "Danish (Dansk)"},
    {"code": "dv", "label": "Divehi"},
    {"code": "nl", "label": "Dutch (Nederlands)"},
    {"code": "dz", "label": "Dzongkha"},
    {"code": "en", "label": "English"},
    {"code": "en-US", "label": "English (US)"},
    {"code": "en-GB", "label": "English (UK)"},
    {"code": "eo", "label": "Esperanto"},
    {"code": "et", "label": "Estonian (Eesti)"},
    {"code": "ee", "label": "Ewe"},
    {"code": "fo", "label": "Faroese"},
    {"code": "fj", "label": "Fijian"},
    {"code": "fi", "label": "Finnish (Suomi)"},
    {"code": "fr", "label": "French (Français)"},
    {"code": "ff", "label": "Fula"},
    {"code": "gl", "label": "Galician"},
    {"code": "ka", "label": "Georgian (ქართული)"},
    {"code": "de", "label": "German (Deutsch)"},
    {"code": "el", "label": "Greek (Ελληνικά)"},
    {"code": "gn", "label": "Guaraní"},
    {"code": "gu", "label": "Gujarati"},
    {"code": "ht", "label": "Haitian Creole"},
    {"code": "ha", "label": "Hausa"},
    {"code": "he", "label": "Hebrew (עברית)"},
    {"code": "hz", "label": "Herero"},
    {"code": "hi", "label": "Hindi (हिन्दी)"},
    {"code": "ho", "label": "Hiri Motu"},
    {"code": "hu", "label": "Hungarian (Magyar)"},
    {"code": "ia", "label": "Interlingua"},
    {"code": "id", "label": "Indonesian (Bahasa Indonesia)"},
    {"code": "ie", "label": "Interlingue"},
    {"code": "ga", "label": "Irish (Gaeilge)"},
    {"code": "ig", "label": "Igbo"},
    {"code": "ik", "label": "Inupiaq"},
    {"code": "io", "label": "Ido"},
    {"code": "is", "label": "Icelandic (Íslenska)"},
    {"code": "it", "label": "Italian (Italiano)"},
    {"code": "iu", "label": "Inuktitut"},
    {"code": "ja", "label": "Japanese (日本語)"},
    {"code": "jv", "label": "Javanese"},
    {"code": "kl", "label": "Kalaallisut"},
    {"code": "kn", "label": "Kannada (ಕನ್ನಡ)"},
    {"code": "kr", "label": "Kanuri"},
    {"code": "ks", "label": "Kashmiri"},
    {"code": "kk", "label": "Kazakh (Қазақ тілі)"},
    {"code": "km", "label": "Khmer (ភាសាខ្មែរ)"},
    {"code": "ki", "label": "Kikuyu"},
    {"code": "rw", "label": "Kinyarwanda"},
    {"code": "ky", "label": "Kyrgyz (Кыргызча)"},
    {"code": "kv", "label": "Komi"},
    {"code": "kg", "label": "Kongo"},
    {"code": "ko", "label": "Korean (한국어)"},
    {"code": "ku", "label": "Kurdish (Kurdî)"},
    {"code": "kj", "label": "Kuanyama"},
    {"code": "la", "label": "Latin"},
    {"code": "lb", "label": "Luxembourgish"},
    {"code": "lg", "label": "Ganda"},
    {"code": "li", "label": "Limburgish"},
    {"code": "ln", "label": "Lingala"},
    {"code": "lo", "label": "Lao (ລາວ)"},
    {"code": "lt", "label": "Lithuanian (Lietuvių)"},
    {"code": "lu", "label": "Luba-Katanga"},
    {"code": "lv", "label": "Latvian (Latviešu)"},
    {"code": "gv", "label": "Manx"},
    {"code": "mk", "label": "Macedonian (Македонски)"},
    {"code": "mg", "label": "Malagasy"},
    {"code": "ms", "label": "Malay (Bahasa Melayu)"},
    {"code": "ml", "label": "Malayalam (മലയാളം)"},
    {"code": "mt", "label": "Maltese (Malti)"},
    {"code": "mi", "label": "Māori"},
    {"code": "mr", "label": "Marathi (मराठी)"},
    {"code": "mh", "label": "Marshallese"},
    {"code": "mn", "label": "Mongolian (Монгол)"},
    {"code": "na", "label": "Nauru"},
    {"code": "nv", "label": "Navajo"},
    {"code": "nb", "label": "Norwegian Bokmål"},
    {"code": "nd", "label": "North Ndebele"},
    {"code": "ne", "label": "Nepali (नेपाली)"},
    {"code": "ng", "label": "Ndonga"},
    {"code": "nn", "label": "Norwegian Nynorsk"},
    {"code": "no", "label": "Norwegian (Norsk)"},
    {"code": "ii", "label": "Nuosu"},
    {"code": "nr", "label": "South Ndebele"},
    {"code": "oc", "label": "Occitan"},
    {"code": "oj", "label": "Ojibwe"},
    {"code": "cu", "label": "Old Church Slavonic"},
    {"code": "om", "label": "Oromo"},
    {"code": "or", "label": "Oriya"},
    {"code": "os", "label": "Ossetian"},
    {"code": "pa", "label": "Punjabi (ਪੰਜਾਬੀ)"},
    {"code": "pi", "label": "Pāli"},
    {"code": "fa", "label": "Persian (فارسی)"},
    {"code": "pl", "label": "Polish (Polski)"},
    {"code": "ps", "label": "Pashto"},
    {"code": "pt", "label": "Portuguese (Português)"},
    {"code": "pt-BR", "label": "Portuguese (Brazil)"},
    {"code": "pt-PT", "label": "Portuguese (Portugal)"},
    {"code": "qu", "label": "Quechua"},
    {"code": "rm", "label": "Romansh"},
    {"code": "rn", "label": "Kirundi"},
    {"code": "ro", "label": "Romanian (Română)"},
    {"code": "ru", "label": "Russian (Русский)"},
    {"code": "sa", "label": "Sanskrit"},
    {"code": "sc", "label": "Sardinian"},
    {"code": "sd", "label": "Sindhi"},
    {"code": "se", "label": "Northern Sami"},
    {"code": "sm", "label": "Samoan"},
    {"code": "sg", "label": "Sango"},
    {"code": "sr", "label": "Serbian (Српски)"},
    {"code": "gd", "label": "Scottish Gaelic"},
    {"code": "sn", "label": "Shona"},
    {"code": "si", "label": "Sinhala (සිංහල)"},
    {"code": "sk", "label": "Slovak (Slovenčina)"},
    {"code": "sl", "label": "Slovenian (Slovenščina)"},
    {"code": "so", "label": "Somali"},
    {"code": "st", "label": "Southern Sotho"},
    {"code": "es", "label": "Spanish (Español)"},
    {"code": "es-MX", "label": "Spanish (Mexico)"},
    {"code": "es-AR", "label": "Spanish (Argentina)"},
    {"code": "su", "label": "Sundanese"},
    {"code": "sw", "label": "Swahili (Kiswahili)"},
    {"code": "ss", "label": "Swati"},
    {"code": "sv", "label": "Swedish (Svenska)"},
    {"code": "ta", "label": "Tamil (தமிழ்)"},
    {"code": "te", "label": "Telugu (తెలుగు)"},
    {"code": "tg", "label": "Tajik (Тоҷикӣ)"},
    {"code": "th", "label": "Thai (ภาษาไทย)"},
    {"code": "ti", "label": "Tigrinya"},
    {"code": "bo", "label": "Tibetan (བོད་ཡིག)"},
    {"code": "tk", "label": "Turkmen"},
    {"code": "tl", "label": "Tagalog"},
    {"code": "tn", "label": "Tswana"},
    {"code": "to", "label": "Tongan"},
    {"code": "tr", "label": "Turkish (Türkçe)"},
    {"code": "ts", "label": "Tsonga"},
    {"code": "tt", "label": "Tatar"},
    {"code": "tw", "label": "Twi"},
    {"code": "ty", "label": "Tahitian"},
    {"code": "ug", "label": "Uyghur"},
    {"code": "uk", "label": "Ukrainian (Українська)"},
    {"code": "ur", "label": "Urdu (اردو)"},
    {"code": "uz", "label": "Uzbek (Oʻzbekcha)"},
    {"code": "ve", "label": "Venda"},
    {"code": "vi", "label": "Vietnamese (Tiếng Việt)"},
    {"code": "vo", "label": "Volapük"},
    {"code": "wa", "label": "Walloon"},
    {"code": "cy", "label": "Welsh (Cymraeg)"},
    {"code": "wo", "label": "Wolof"},
    {"code": "fy", "label": "Western Frisian"},
    {"code": "xh", "label": "Xhosa"},
    {"code": "yi", "label": "Yiddish"},
    {"code": "yo", "label": "Yoruba"},
    {"code": "za", "label": "Zhuang"},
    {"code": "zu", "label": "Zulu"},
]

# Quick lookup tables
LABEL_BY_CODE: Dict[str, str] = {x["code"]: x["label"] for x in LANGUAGES}
# Map every ISO 639-2 (3-letter) code commonly emitted by ffprobe → iso 639-1
ISO_639_2_TO_1: Dict[str, str] = {
    "alb": "sq", "sqi": "sq",
    "ara": "ar",
    "arm": "hy", "hye": "hy",
    "aze": "az",
    "bel": "be",
    "ben": "bn",
    "bos": "bs",
    "bul": "bg",
    "bur": "my", "mya": "my",
    "cat": "ca",
    "ces": "cs", "cze": "cs",
    "chi": "zh", "zho": "zh",
    "wel": "cy", "cym": "cy",
    "dan": "da",
    "deu": "de", "ger": "de",
    "dut": "nl", "nld": "nl",
    "ell": "el", "gre": "el",
    "eng": "en",
    "epo": "eo",
    "est": "et",
    "eus": "eu", "baq": "eu",
    "fas": "fa", "per": "fa",
    "fin": "fi",
    "fra": "fr", "fre": "fr",
    "geo": "ka", "kat": "ka",
    "gle": "ga",
    "glg": "gl",
    "guj": "gu",
    "heb": "he",
    "hin": "hi",
    "hrv": "hr",
    "hun": "hu",
    "ice": "is", "isl": "is",
    "ind": "id",
    "ita": "it",
    "jpn": "ja",
    "kan": "kn",
    "kaz": "kk",
    "khm": "km",
    "kor": "ko",
    "lao": "lo",
    "lat": "la",
    "lav": "lv",
    "lit": "lt",
    "mac": "mk", "mkd": "mk",
    "mal": "ml",
    "may": "ms", "msa": "ms",
    "mar": "mr",
    "mlt": "mt",
    "nor": "no",
    "nob": "nb",
    "nno": "nn",
    "nep": "ne",
    "ori": "or",
    "pan": "pa",
    "pol": "pl",
    "por": "pt",
    "que": "qu",
    "rum": "ro", "ron": "ro",
    "rus": "ru",
    "san": "sa",
    "sin": "si",
    "slk": "sk", "slo": "sk",
    "slv": "sl",
    "som": "so",
    "spa": "es",
    "srp": "sr",
    "swa": "sw",
    "swe": "sv",
    "tam": "ta",
    "tel": "te",
    "tgl": "tl",
    "tha": "th",
    "tib": "bo", "bod": "bo",
    "tur": "tr",
    "ukr": "uk",
    "urd": "ur",
    "uzb": "uz",
    "vie": "vi",
    "yid": "yi",
    "yor": "yo",
    "zul": "zu",
}

# ----- Filename → ISO 639-1 detection -----------------------------------------------------
# Each entry: (canonical iso 639-1 code, regex pattern matched against
# lowercased filename WITHOUT extension, with word-boundary guards).
_FILENAME_HINTS: List[tuple] = [
    # Romanian
    ("ro", r"\b(ro|rom|ron|romanian|romana|română)\b"),
    # English variants
    ("en", r"\b(en|eng|english|en[-_]us|en[-_]gb)\b"),
    # Japanese
    ("ja", r"\b(ja|jp|jpn|japanese|nihongo|日本語)\b"),
    # Chinese (defaults to simplified)
    ("zh-Hant", r"\b(zh[-_]hant|chs[-_]?tw|chinese[-_]?traditional|繁體)\b"),
    ("zh-Hans", r"\b(zh[-_]hans|chs|simplified|chinese[-_]?simplified|简体)\b"),
    ("zh",     r"\b(zh|cmn|chi|chinese|mandarin|中文)\b"),
    # Korean
    ("ko", r"\b(ko|kor|korean|한국어)\b"),
    # European
    ("es", r"\b(es|esp|spa|spanish|español|espanol)\b"),
    ("fr", r"\b(fr|fra|fre|french|francais|français)\b"),
    ("de", r"\b(de|deu|ger|german|deutsch)\b"),
    ("it", r"\b(it|ita|italian|italiano)\b"),
    ("pt-BR", r"\b(pt[-_]br|ptbr|portuguese[-_]?brazil)\b"),
    ("pt", r"\b(pt|por|portuguese|portugues|português)\b"),
    ("ru", r"\b(ru|rus|russian|русский|русск)\b"),
    ("uk", r"\b(uk|ukr|ukrainian|українська)\b"),
    ("pl", r"\b(pl|pol|polish|polski)\b"),
    ("nl", r"\b(nl|nld|dut|dutch|nederlands)\b"),
    ("sv", r"\b(sv|swe|swedish|svenska)\b"),
    ("no", r"\b(no|nor|norwegian|norsk)\b"),
    ("nb", r"\b(nb|nob|bokmal|bokmål)\b"),
    ("nn", r"\b(nn|nno|nynorsk)\b"),
    ("da", r"\b(da|dan|danish|dansk)\b"),
    ("fi", r"\b(fi|fin|finnish|suomi)\b"),
    ("cs", r"\b(cs|cze|ces|czech|čeština|cestina)\b"),
    ("sk", r"\b(sk|slo|slk|slovak|slovenčina|slovencina)\b"),
    ("hu", r"\b(hu|hun|hungarian|magyar)\b"),
    ("el", r"\b(el|gre|ell|greek|ελληνικά)\b"),
    ("tr", r"\b(tr|tur|turkish|türkçe|turkce)\b"),
    ("ar", r"\b(ar|ara|arabic|عربي|العربية)\b"),
    ("he", r"\b(he|heb|hebrew|עברית)\b"),
    ("hi", r"\b(hi|hin|hindi|हिन्दी)\b"),
    ("th", r"\b(th|tha|thai|ภาษาไทย)\b"),
    ("vi", r"\b(vi|vie|vietnamese|tiếng[ _-]?việt|tieng[ _-]?viet)\b"),
    ("id", r"\b(id|ind|indonesian|bahasa[ _-]?indonesia)\b"),
    ("ms", r"\b(ms|may|msa|malay)\b"),
    ("bg", r"\b(bg|bul|bulgarian|български)\b"),
    ("sr", r"\b(sr|srp|serbian|српски)\b"),
    ("hr", r"\b(hr|hrv|croatian|hrvatski)\b"),
    ("bs", r"\b(bs|bos|bosnian)\b"),
    ("sl", r"\b(sl|slv|slovenian|slovenščina|slovenscina)\b"),
    ("ca", r"\b(ca|cat|catalan|català)\b"),
    ("eu", r"\b(eu|eus|baq|basque|euskara)\b"),
    ("gl", r"\b(gl|glg|galician|galego)\b"),
    ("et", r"\b(et|est|estonian|eesti)\b"),
    ("lv", r"\b(lv|lav|latvian|latviešu|latviesu)\b"),
    ("lt", r"\b(lt|lit|lithuanian|lietuvių|lietuviu)\b"),
    ("is", r"\b(is|isl|ice|icelandic|íslenska|islenska)\b"),
    ("ga", r"\b(ga|gle|irish|gaeilge)\b"),
    ("mt", r"\b(mt|mlt|maltese|malti)\b"),
    ("sq", r"\b(sq|alb|sqi|albanian|shqip)\b"),
    ("mk", r"\b(mk|mac|mkd|macedonian|македонски)\b"),
    ("hy", r"\b(hy|arm|hye|armenian|հայերեն)\b"),
    ("ka", r"\b(ka|geo|kat|georgian|ქართული)\b"),
    ("az", r"\b(az|aze|azerbaijani|azərbaycan)\b"),
    ("be", r"\b(be|bel|belarusian|беларуская)\b"),
    ("kk", r"\b(kk|kaz|kazakh|қазақ)\b"),
    ("uz", r"\b(uz|uzb|uzbek|oʻzbekcha|ozbekcha)\b"),
    ("mn", r"\b(mn|mon|mongolian|монгол)\b"),
    ("my", r"\b(my|bur|mya|burmese|မြန်မာ)\b"),
    ("km", r"\b(km|khm|khmer|ខ្មែរ)\b"),
    ("lo", r"\b(lo|lao|laotian|ລາວ)\b"),
    ("si", r"\b(si|sin|sinhala|සිංහල)\b"),
    ("ta", r"\b(ta|tam|tamil|தமிழ்)\b"),
    ("te", r"\b(te|tel|telugu|తెలుగు)\b"),
    ("ml", r"\b(ml|mal|malayalam|മലയാളം)\b"),
    ("kn", r"\b(kn|kan|kannada|ಕನ್ನಡ)\b"),
    ("mr", r"\b(mr|mar|marathi|मराठी)\b"),
    ("gu", r"\b(gu|guj|gujarati|ગુજરાતી)\b"),
    ("pa", r"\b(pa|pan|punjabi|ਪੰਜਾਬੀ)\b"),
    ("bn", r"\b(bn|ben|bengali|বাংলা)\b"),
    ("ne", r"\b(ne|nep|nepali|नेपाली)\b"),
    ("ur", r"\b(ur|urd|urdu|اردو)\b"),
    ("fa", r"\b(fa|fas|per|persian|farsi|فارسی)\b"),
    ("ps", r"\b(ps|pus|pashto|پشتو)\b"),
    ("sw", r"\b(sw|swa|swahili|kiswahili)\b"),
    ("am", r"\b(am|amh|amharic|አማርኛ)\b"),
    ("af", r"\b(af|afr|afrikaans)\b"),
    ("zu", r"\b(zu|zul|zulu)\b"),
    ("xh", r"\b(xh|xho|xhosa)\b"),
    ("yo", r"\b(yo|yor|yoruba)\b"),
    ("ig", r"\b(ig|ibo|igbo)\b"),
    ("ha", r"\b(ha|hau|hausa)\b"),
    ("eo", r"\b(eo|epo|esperanto)\b"),
    ("la", r"\b(la|lat|latin)\b"),
    ("cy", r"\b(cy|wel|cym|welsh|cymraeg)\b"),
]


def normalize_language_code(code: str) -> str:
    """Map an iso 639-2 (3-letter) code coming from ffprobe to iso 639-1.
    Unknown / empty / "und" → "und"."""
    code = (code or "").strip().lower()
    if not code or code == "und":
        return "und"
    if len(code) == 2 and code in LABEL_BY_CODE:
        return code
    if code in ISO_639_2_TO_1:
        return ISO_639_2_TO_1[code]
    # Locale form like "ja-JP" or "pt-BR" — try the prefix and the full code
    if "-" in code or "_" in code:
        full = code.replace("_", "-")
        if full in LABEL_BY_CODE:
            return full
        prefix = full.split("-")[0]
        if prefix in LABEL_BY_CODE:
            return prefix
    return code if code in LABEL_BY_CODE else "und"


def detect_language_from_filename(filename: str) -> Dict[str, str]:
    """Heuristically infer (language_code, human_label) from a subtitle file's
    name.  Falls back to ``{"language": "und", "label": "Unknown"}``.
    """
    if not filename:
        return {"language": "und", "label": "Unknown"}
    # Strip path & extension
    name = filename.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    base = re.sub(r"\.[^.]+$", "", name).lower()
    # Replace separators with spaces so \b can match around codes
    norm = re.sub(r"[._\-\[\]\(\)\{\}]+", " ", base)
    for code, pat in _FILENAME_HINTS:
        if re.search(pat, norm, re.IGNORECASE | re.UNICODE):
            return {"language": code, "label": LABEL_BY_CODE.get(code, code.upper())}
    # Last-resort: detect concatenated language hints inside a word
    # (e.g. "epizod-rosub", "spanishlatam", "episode-japsub").  Search the
    # un-normalised lowercase base so we don't burn cycles on the rare
    # language names that themselves contain other lang substrings.
    SUB_HINTS = [
        ("ro", "rosub"), ("ro", "romsub"),
        ("ja", "jpsub"), ("ja", "japsub"), ("ja", "jasub"),
        ("en", "engsub"), ("en", "ensub"),
        ("es", "spasub"), ("es", "esp sub"),
        ("fr", "frasub"), ("fr", "fre sub"),
        ("de", "gersub"), ("de", "dehsub"),
        ("ko", "korsub"),
        ("zh", "chisub"), ("zh", "chnsub"),
        ("pt", "porsub"), ("pt-BR", "ptbrsub"),
        ("ru", "russub"),
        ("ar", "arasub"),
    ]
    for code, hint in SUB_HINTS:
        if hint in base:
            return {"language": code, "label": LABEL_BY_CODE.get(code, code.upper())}
    return {"language": "und", "label": "Unknown"}
