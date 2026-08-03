# -*- coding: utf-8 -*-
"""
Строки, которые НЕЛЬЗЯ отдавать модели-переводчику.

⚠️ Зачем. Присланное игроками уходит в тот же прогон, что и наш дамп, —
а значит текст, написанный человеком, попадает в запрос к модели. Инъекция
(«не переводи, а сделай вот что») денег сама по себе не стоит и схему ответа
обойти не может, но:

  * мусор РАЗДУВАЕТ очередь, и за его перевод платят как за настоящий;
  * испорченный ответ тратит токены и время на разбор;
  * а главное — такие строки в переводе не нужны никому.

⚠️ Признаки НАРОЧНО грубые и не режут игровой текст. Проверено на живом
корпусе: `python tools/check_suspicious.py`.

⚠️ Это НЕ замена проверкам `accept()`. Те смотрят ОТВЕТ модели, а этот
фильтр — ВОПРОС: строку, похожую на инструкцию, лучше вовсе не отправлять.
"""
from __future__ import annotations

import re

# Обращение к модели или к тому, кто читает данные.
#
# ⚠️ «you are a …» ОТСЮДА УБРАНО, хотя в инъекциях встречается постоянно.
# Замер по корпусу: оно задевало живые описания способностей — «Spawns and
# assists you when you are a ghost in Dungeons», «Half Life: if you are the
# first player to die». Осталось «you are NOW a», которого в игре нет.
INSTRUCTION = re.compile(
    r"\b(ignore|disregard|forget)\b.{0,40}\b(previous|prior|above|all)\b.{0,30}"
    r"\b(instruction|prompt|rule|command)"
    r"|\b(system|assistant)\s*:\s*"
    r"|\byou\s+are\s+now\s+(an?|the)\s+\w+"
    r"|\b(игнорируй|забудь|не\s+переводи)\b.{0,40}"
    r"\b(инструкц|правил|предыдущ|указан)"
    r"|\bвыполни\b.{0,20}\b(команд|скрипт|код)",
    re.I | re.S)

# Похоже на код или на попытку что-то запустить.
CODE = re.compile(
    r"</?(script|iframe|img|svg)\b"
    r"|\b(rm\s+-rf|curl\s+http|wget\s+http|powershell|cmd\.exe|/bin/sh|bash\s+-c)\b"
    r"|\bimport\s+os\b|\bsubprocess\b|\beval\(|\bexec\(",
    re.I)

# Ссылки — но НЕ хайпиксельные.
#
# ⚠️ «В интерфейсе SkyBlock ссылок не бывает» — неверно, и это замер, а не
# догадка: в корпусе три живых абзаца со ссылками, все на store.hypixel.net
# («Requires: [MVP+] https://store.hypixel.net»), плюс www.hypixel.net
# в боковой панели. Наивный признак «есть ссылка» резал бы их.
# Свои домены перечислены, остальные — повод присмотреться.
OWN_DOMAIN = re.compile(r"\bhypixel\.net\b", re.I)
LINK = re.compile(r"https?://\S+|\bwww\.[\w-]+\.\w{2,}|\b[\w-]+\.(com|ru|org|io|xyz)/", re.I)

# Разметка нашего же запроса: попытка притвориться служебной частью.
FRAME = re.compile(r"^\s*(АБЗАЦ\s+\d+|ГЛОССАРИЙ|СТРОКА\s+\d+)\b", re.I)


def why_suspicious(line: str) -> str | None:
    """Причина, по которой строку не стоит отправлять. None — можно."""
    if not line:
        return None
    # ⚠️ Порог взят ИЗ ДАННЫХ, а не с потолка. Замер по 6540 переведённым
    # абзацам: половина короче 65 знаков, 99% короче 269, САМЫЙ ДЛИННЫЙ — 688.
    # Первая попытка стояла на 300 и задевала 40 живых абзацев (наборы
    # зачарований, списки привилегий). Берём 900 — вдвое выше настоящего
    # максимума, но всё ещё ловит простыни, которых в игре не бывает.
    if len(line) > 900:
        return "слишком длинная для игрового текста"
    if INSTRUCTION.search(line):
        return "похоже на инструкцию модели"
    if CODE.search(line):
        return "похоже на код или команду"
    if LINK.search(line) and not OWN_DOMAIN.search(line):
        return "ссылка на чужой сайт"
    if FRAME.search(line):
        return "притворяется разметкой запроса"
    return None


def suspicious(line: str) -> bool:
    return why_suspicious(line) is not None
