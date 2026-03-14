"""
Модуль для загрузки и поиска аятов Корана.
Загружает арабский текст и транскрипцию (латиницу) из API.
Поддерживает поиск по арабскому тексту, латинской транскрипции
и русской транскрипции с нечётким сравнением.
"""

import json
import os
import re
import aiohttp
from rapidfuzz import fuzz

QURAN_CACHE_FILE = os.path.join(os.path.dirname(__file__), "quran_cache.json")

# Названия сур на русском
SURAH_NAMES_RU = {
    1: "Аль-Фатиха (Открывающая)",
    2: "Аль-Бакара (Корова)",
    3: "Алю Имран (Семейство Имрана)",
    4: "Ан-Ниса (Женщины)",
    5: "Аль-Маида (Трапеза)",
    6: "Аль-Анам (Скот)",
    7: "Аль-Араф (Преграды)",
    8: "Аль-Анфаль (Трофеи)",
    9: "Ат-Тауба (Покаяние)",
    10: "Юнус (Иона)",
    11: "Худ",
    12: "Юсуф (Иосиф)",
    13: "Ар-Раад (Гром)",
    14: "Ибрахим (Авраам)",
    15: "Аль-Хиджр (Хиджр)",
    16: "Ан-Нахль (Пчёлы)",
    17: "Аль-Исра (Ночной перенос)",
    18: "Аль-Кахф (Пещера)",
    19: "Марьям (Мария)",
    20: "Та Ха",
    21: "Аль-Анбия (Пророки)",
    22: "Аль-Хадж (Паломничество)",
    23: "Аль-Муминун (Верующие)",
    24: "Ан-Нур (Свет)",
    25: "Аль-Фуркан (Различение)",
    26: "Аш-Шуара (Поэты)",
    27: "Ан-Намль (Муравьи)",
    28: "Аль-Касас (Рассказы)",
    29: "Аль-Анкабут (Паук)",
    30: "Ар-Рум (Римляне)",
    31: "Лукман",
    32: "Ас-Саджда (Поклон)",
    33: "Аль-Ахзаб (Союзники)",
    34: "Саба (Сава)",
    35: "Фатыр (Творец)",
    36: "Ясин",
    37: "Ас-Саффат (Выстроившиеся в ряды)",
    38: "Сад",
    39: "Аз-Зумар (Толпы)",
    40: "Гафир (Прощающий)",
    41: "Фуссилят (Разъяснены)",
    42: "Аш-Шура (Совет)",
    43: "Аз-Зухруф (Украшения)",
    44: "Ад-Духан (Дым)",
    45: "Аль-Джасия (Коленопреклонённая)",
    46: "Аль-Ахкаф (Барханы)",
    47: "Мухаммад",
    48: "Аль-Фатх (Победа)",
    49: "Аль-Худжурат (Комнаты)",
    50: "Каф",
    51: "Аз-Зарият (Рассеивающие)",
    52: "Ат-Тур (Гора)",
    53: "Ан-Наджм (Звезда)",
    54: "Аль-Камар (Луна)",
    55: "Ар-Рахман (Милостивый)",
    56: "Аль-Вакиа (Событие)",
    57: "Аль-Хадид (Железо)",
    58: "Аль-Муджадала (Препирательство)",
    59: "Аль-Хашр (Сбор)",
    60: "Аль-Мумтахана (Испытуемая)",
    61: "Ас-Сафф (Ряды)",
    62: "Аль-Джумуа (Пятница)",
    63: "Аль-Мунафикун (Лицемеры)",
    64: "Ат-Тагабун (Взаимное обманывание)",
    65: "Ат-Таляк (Развод)",
    66: "Ат-Тахрим (Запрещение)",
    67: "Аль-Мульк (Власть)",
    68: "Аль-Калям (Перо)",
    69: "Аль-Хакка (Неизбежное)",
    70: "Аль-Мааридж (Ступени)",
    71: "Нух (Ной)",
    72: "Аль-Джинн (Джинны)",
    73: "Аль-Муззаммиль (Закутавшийся)",
    74: "Аль-Муддассир (Завернувшийся)",
    75: "Аль-Кияма (Воскресение)",
    76: "Аль-Инсан (Человек)",
    77: "Аль-Мурсалят (Посылаемые)",
    78: "Ан-Наба (Весть)",
    79: "Ан-Назиат (Вырывающие)",
    80: "Абаса (Нахмурился)",
    81: "Ат-Таквир (Скручивание)",
    82: "Аль-Инфитар (Раскалывание)",
    83: "Аль-Мутаффифин (Обвешивающие)",
    84: "Аль-Иншикак (Разверзнётся)",
    85: "Аль-Бурудж (Созвездия)",
    86: "Ат-Тарик (Ночной путник)",
    87: "Аль-Аля (Всевышний)",
    88: "Аль-Гашия (Покрывающее)",
    89: "Аль-Фаджр (Заря)",
    90: "Аль-Балад (Город)",
    91: "Аш-Шамс (Солнце)",
    92: "Аль-Лейль (Ночь)",
    93: "Ад-Духа (Утро)",
    94: "Аш-Шарх (Раскрытие)",
    95: "Ат-Тин (Смоковница)",
    96: "Аль-Аляк (Сгусток)",
    97: "Аль-Кадр (Предопределение)",
    98: "Аль-Баййина (Ясное знамение)",
    99: "Аз-Зальзаля (Землетрясение)",
    100: "Аль-Адият (Мчащиеся)",
    101: "Аль-Кариа (Великое бедствие)",
    102: "Ат-Такасур (Страсть к приумножению)",
    103: "Аль-Аср (Время)",
    104: "Аль-Хумаза (Хулитель)",
    105: "Аль-Филь (Слон)",
    106: "Курайш",
    107: "Аль-Маун (Мелочь)",
    108: "Аль-Каусар (Изобилие)",
    109: "Аль-Кяфирун (Неверующие)",
    110: "Ан-Наср (Помощь)",
    111: "Аль-Масад (Пальмовые волокна)",
    112: "Аль-Ихляс (Искренность)",
    113: "Аль-Фаляк (Рассвет)",
    114: "Ан-Нас (Люди)",
}


async def download_quran_data():
    """Скачивает полный текст Корана на арабском + транскрипцию через API."""
    if os.path.exists(QURAN_CACHE_FILE):
        with open(QURAN_CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)

    print("Загрузка данных Корана...")
    arabic_data = {}
    transliteration_data = {}

    async with aiohttp.ClientSession() as session:
        # Загружаем арабский текст
        url_ar = "https://api.alquran.cloud/v1/quran/quran-simple"
        async with session.get(url_ar) as resp:
            if resp.status == 200:
                data = await resp.json()
                for surah in data["data"]["surahs"]:
                    for ayah in surah["ayahs"]:
                        arabic_data[ayah["number"]] = {
                            "surah": surah["number"],
                            "surah_name": surah["name"],
                            "surah_english": surah["englishName"],
                            "ayah": ayah["numberInSurah"],
                            "text": ayah["text"],
                        }

        # Загружаем транскрипцию (латиницу)
        url_tr = "https://api.alquran.cloud/v1/quran/en.transliteration"
        async with session.get(url_tr) as resp:
            if resp.status == 200:
                data = await resp.json()
                for surah in data["data"]["surahs"]:
                    for ayah in surah["ayahs"]:
                        transliteration_data[ayah["number"]] = ayah["text"]

    # Объединяем
    quran_data = []
    for num, ar in arabic_data.items():
        entry = {**ar}
        entry["transliteration"] = transliteration_data.get(num, "")
        quran_data.append(entry)

    with open(QURAN_CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(quran_data, f, ensure_ascii=False, indent=2)

    print(f"Загружено {len(quran_data)} аятов")
    return quran_data


def normalize_arabic(text: str) -> str:
    """Нормализует арабский текст для лучшего сравнения."""
    diacritics = [
        '\u064B', '\u064C', '\u064D', '\u064E', '\u064F',
        '\u0650', '\u0651', '\u0652', '\u0670', '\u0640',
    ]
    for d in diacritics:
        text = text.replace(d, '')

    text = text.replace('إ', 'ا').replace('أ', 'ا').replace('آ', 'ا').replace('ٱ', 'ا')
    text = text.replace('ة', 'ه')
    text = text.replace('ى', 'ي')
    text = ' '.join(text.split())
    return text.strip()


def normalize_translit(text: str) -> str:
    """Нормализует транскрипцию (латиница или русская) для сравнения."""
    text = text.lower().strip()
    # Убираем знаки препинания и спецсимволы
    text = re.sub(r'[^\w\s]', '', text)
    text = ' '.join(text.split())
    return text


# Русский -> латинская транскрипция (для сравнения с en.transliteration)
RUSSIAN_TO_LATIN = {
    'бисмилля': 'bismillah',
    'аллах': 'allah',
    'рахман': 'rahman',
    'рахим': 'raheem',
    'альхамдулилля': 'alhamdu lillahi',
    'хамд': 'hamd',
    'рабб': 'rabb',
    'аламин': 'alamin',
    'малик': 'maliki',
    'йаум': 'yawmi',
    'дин': 'deen',
    'иййака': 'iyyaka',
    'набуду': 'nabudu',
    'настаин': 'nastaeen',
    'ихдина': 'ihdina',
    'сырат': 'sirat',
    'мустаким': 'mustaqeem',
    'куль': 'qul',
    'хува': 'huwa',
    'ахад': 'ahad',
    'самад': 'samad',
    'лям': 'lam',
    'йалид': 'yalid',
    'юлад': 'yulad',
    'куфуван': 'kufuwan',
    'фаляк': 'falaq',
    'аузу': 'aoothu',
    'шарр': 'sharri',
    'халяк': 'khalaqa',
    'гасик': 'ghasiqin',
    'вакаб': 'waqab',
    'наффасат': 'naffathati',
    'укад': 'uqad',
    'хасид': 'hasid',
    'нас': 'nas',
    'малик': 'maliki',
    'илях': 'ilahi',
    'васвас': 'waswas',
    'ханнас': 'khannas',
    'джинна': 'jinnati',
    'ихляс': 'ikhlas',
    'таббат': 'tabbat',
    'масад': 'masad',
    'идха': 'itha',
    'джаа': 'jaa',
    'наср': 'nasru',
    'фатх': 'fath',
    'кяфирун': 'kafirun',
    'кяусар': 'kawthar',
    'маун': 'maun',
    'курайш': 'quraysh',
    'филь': 'feel',
    'хумаза': 'humazah',
    'аср': 'asr',
    'такасур': 'takathur',
    'кариа': 'qariah',
    'адият': 'adiyat',
    'зальзаля': 'zalzalah',
    'баййина': 'bayyinah',
    'кадр': 'qadr',
    'аляк': 'alaq',
    'тин': 'teen',
    'шарх': 'sharh',
    'духа': 'duha',
    'лейль': 'layl',
    'шамс': 'shams',
    'балад': 'balad',
    'фаджр': 'fajr',
    'гашия': 'ghashiyah',
    # Общие слова
    'ва': 'wa',
    'ля': 'la',
    'мин': 'min',
    'фи': 'fee',
    'ан': 'an',
    'ма': 'ma',
    'инна': 'inna',
    'аллязи': 'allatheena',
    'каля': 'qala',
    'ляху': 'lahu',
    'илля': 'illa',
    'аля': 'ala',
    'хум': 'hum',
    'кяна': 'kana',
    'бихи': 'bihi',
    'раббика': 'rabbika',
}


def russian_to_latin(text: str) -> str:
    """Конвертирует русскую транскрипцию в латинскую для сравнения."""
    text_lower = text.lower()

    # Сначала заменяем известные слова/фразы (длинные первыми)
    sorted_keys = sorted(RUSSIAN_TO_LATIN.keys(), key=len, reverse=True)
    for ru, lat in ((k, RUSSIAN_TO_LATIN[k]) for k in sorted_keys):
        text_lower = text_lower.replace(ru, lat)

    # Базовая побуквенная транслитерация для оставшихся символов
    char_map = {
        'а': 'a', 'б': 'b', 'в': 'w', 'г': 'gh', 'д': 'd',
        'е': 'e', 'ё': 'yo', 'ж': 'zh', 'з': 'z', 'и': 'i',
        'й': 'y', 'к': 'k', 'л': 'l', 'м': 'm', 'н': 'n',
        'о': 'o', 'п': 'p', 'р': 'r', 'с': 's', 'т': 't',
        'у': 'u', 'ф': 'f', 'х': 'h', 'ц': 'ts', 'ч': 'ch',
        'ш': 'sh', 'щ': 'sh', 'ъ': '', 'ы': 'y', 'ь': '',
        'э': 'e', 'ю': 'yu', 'я': 'ya',
    }
    result = []
    for ch in text_lower:
        if ch in char_map:
            result.append(char_map[ch])
        else:
            result.append(ch)

    return ''.join(result)


def is_arabic(text: str) -> bool:
    """Проверяет, содержит ли текст арабские символы."""
    return any('\u0600' <= ch <= '\u06FF' or '\u0750' <= ch <= '\u077F' for ch in text)


def is_russian(text: str) -> bool:
    """Проверяет, содержит ли текст русские символы."""
    return any('\u0400' <= ch <= '\u04FF' for ch in text)


def search_ayah(quran_data: list, query: str, top_n: int = 5) -> list:
    """
    Ищет аят по тексту. ВСЕГДА возвращает топ результатов с процентом.
    Поддерживает: арабский текст, латинскую транскрипцию, русскую транскрипцию.
    """
    results = []

    if is_arabic(query):
        # Поиск по арабскому тексту
        query_norm = normalize_arabic(query)
        for ayah_data in quran_data:
            ayah_norm = normalize_arabic(ayah_data["text"])

            if query_norm in ayah_norm:
                score = 100
            else:
                # Используем несколько методов и берём лучший
                score1 = fuzz.partial_ratio(query_norm, ayah_norm)
                score2 = fuzz.token_sort_ratio(query_norm, ayah_norm)
                score3 = fuzz.token_set_ratio(query_norm, ayah_norm)
                score = max(score1, score2, score3)

            results.append({**ayah_data, "score": score})

    elif is_russian(query):
        # Русская транскрипция -> латинская -> сравниваем с transliteration
        query_latin = russian_to_latin(query)
        query_norm = normalize_translit(query_latin)
        query_ru_norm = normalize_translit(query)

        for ayah_data in quran_data:
            translit = ayah_data.get("transliteration", "")
            translit_norm = normalize_translit(translit)

            if not translit_norm:
                continue

            # Сравниваем латинизированный русский с транскрипцией
            score1 = fuzz.partial_ratio(query_norm, translit_norm)
            score2 = fuzz.token_sort_ratio(query_norm, translit_norm)
            score3 = fuzz.token_set_ratio(query_norm, translit_norm)

            # Также пробуем прямое сравнение русского текста
            # (на случай если кто-то пишет близко к латинской транскрипции)
            score4 = fuzz.partial_ratio(query_ru_norm, translit_norm)

            score = max(score1, score2, score3, score4)
            results.append({**ayah_data, "score": score})

    else:
        # Латинская транскрипция
        query_norm = normalize_translit(query)
        for ayah_data in quran_data:
            translit = ayah_data.get("transliteration", "")
            translit_norm = normalize_translit(translit)

            if not translit_norm:
                continue

            if query_norm in translit_norm:
                score = 100
            else:
                score1 = fuzz.partial_ratio(query_norm, translit_norm)
                score2 = fuzz.token_sort_ratio(query_norm, translit_norm)
                score3 = fuzz.token_set_ratio(query_norm, translit_norm)
                score = max(score1, score2, score3)

            results.append({**ayah_data, "score": score})

    # Сортируем и берём топ
    results.sort(key=lambda x: x["score"], reverse=True)

    # Убираем дубликаты (один аят может попасть несколько раз)
    seen = set()
    unique = []
    for r in results:
        key = (r["surah"], r["ayah"])
        if key not in seen:
            seen.add(key)
            unique.append(r)
        if len(unique) >= top_n:
            break

    return unique
