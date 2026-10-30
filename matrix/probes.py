"""The 20 probe texts of the offset-convention matrix. Each probe has one target span (the first
occurrence of `target` after `after`, if given). Sentences are original; names are places,
organisations or public figures."""

H = "ٔ"
PROBES = [
    ("p01", "plain Arabic", "زار الوفد مدينة الرياض", "الرياض", ""),
    ("p02", "harakat", "سافرَ الوفدُ إلى دِمَشْقَ أمسِ", "دِمَشْقَ", ""),
    ("p03", "tatweel", "تقع مدينة الريـــاض في الوسط", "الريـــاض", ""),
    ("p04", "astral emoji before the span", "وصلنا \U0001F600 إلى جدة", "جدة", ""),
    ("p05", "emoji ZWJ sequence before the span", "\U0001F468‍\U0001F469‍\U0001F467 عائلة من القاهرة", "القاهرة", ""),
    ("p06", "ZWNJ before the span", "قال‌ الدليل إن صلالة جميلة", "صلالة", ""),
    ("p07", "RLM before the span", "انتقل المقر إلى ‏الرياض", "الرياض", ""),
    ("p08", "ALM before the span", "سافر الفريق إلى ؜تونس", "تونس", ""),
    ("p09", "CRLF line break before the span", "سطر أول\r\nزار الوفد عمّان", "عمّان", ""),
    ("p10", "lam-alef ligature U+FEFB before the span", "ﻻ يزال المتحف في الشارقة", "الشارقة", ""),
    ("p11", "ligature U+FDF2 before the span", "كتب الخطاط ﷲ في الدوحة", "الدوحة", ""),
    ("p12", "alef + combining hamza (U+0627 U+0654) before the span", "س" + "ا" + H + "ل الباحث عن القاهرة", "القاهرة", ""),
    ("p13", "Arabic-Indic digits as the span", "افتتح المعرض عام ٢٠٢٦ في مسقط", "٢٠٢٦", ""),
    ("p14", "English name inside Arabic text", "أعلنت شركة Microsoft عن مركز في دبي", "Microsoft", ""),
    ("p15", "LRM marks around a Latin name", "تعاونت الجامعة مع ‎MIT‎ في مشروع", "MIT", ""),
    ("p16", "U+FEFF at the start of the text", "﻿يزور السياح الأقصر", "الأقصر", ""),
    ("p17", "shadda before fatha (not in canonical order)", "زار الوفد مكَّة", "مكَّة", ""),
    ("p18", "conjunction attached to the name", "زرنا جدة والرياض", "الرياض", ""),
    ("p19", "Arabic comma after the name", "زرنا الرياض، ثم جدة", "الرياض", ""),
    ("p20", "emoji, CRLF and harakat together", "\U0001F30D مرحبًا\r\nمن مَكَّةَ", "مَكَّةَ", ""),
]


def target_cp(text, target, after=""):
    i = text.index(target, text.index(after) + len(after) if after else 0)
    return i, i + len(target)
