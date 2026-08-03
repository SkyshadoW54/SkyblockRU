"""
Чтение NBT — бинарного формата, в котором Minecraft хранит данные предмета.

Зачем свой ридер. Официальный API аукциона отдаёт предмет полем `item_bytes`:
base64 + gzip + NBT. Внутри лежит то, что мы годами добывали разбором готового
текста — идентификатор предмета, зачарования с уровнями, самоцветы, перековка.
Сторонней библиотеки в проекте нет, а формат простой и стабильный с 2011 года:
тег = байт типа, имя со счётчиком длины, значение.

⚠️ Структура в аукционе ГИБРИДНАЯ, и это видно только по живым данным:
рядом лежат `components` (новый формат 1.20.5+) и `tag` со старыми
`display.Lore` и `ExtraAttributes`. Поэтому читатель не делает предположений
о раскладке — он просто разбирает дерево, а искать в нём умеет `find`.

⚠️ Строки в NBT — «модифицированный UTF-8»: почти обычный, но кодирует NUL
двумя байтами и суррогатные пары по отдельности. Для наших данных разница
не проявляется, поэтому декодируем обычным UTF-8 с заменой сбойных байт —
падать из-за одного экзотического символа тут нечего.

Использование:
    from nbt import read_item_bytes, find
    root = read_item_bytes(lot["item_bytes"])
    extra = find(root, "ExtraAttributes") or {}
    item_id = extra.get("id")
"""
from __future__ import annotations

import base64
import gzip
import struct

END = 0
BYTE = 1
SHORT = 2
INT = 3
LONG = 4
FLOAT = 5
DOUBLE = 6
BYTE_ARRAY = 7
STRING = 8
LIST = 9
COMPOUND = 10
INT_ARRAY = 11
LONG_ARRAY = 12


class Reader:
    def __init__(self, data: bytes) -> None:
        self.data = data
        self.at = 0

    def take(self, count: int) -> bytes:
        if self.at + count > len(self.data):
            raise ValueError("NBT кончился раньше времени")
        piece = self.data[self.at:self.at + count]
        self.at += count
        return piece

    def number(self, form: str, size: int):
        return struct.unpack(">" + form, self.take(size))[0]

    def string(self) -> str:
        length = self.number("H", 2)
        return self.take(length).decode("utf-8", errors="replace")

    def payload(self, kind: int):
        if kind == BYTE:
            return self.number("b", 1)
        if kind == SHORT:
            return self.number("h", 2)
        if kind == INT:
            return self.number("i", 4)
        if kind == LONG:
            return self.number("q", 8)
        if kind == FLOAT:
            return self.number("f", 4)
        if kind == DOUBLE:
            return self.number("d", 8)
        if kind == BYTE_ARRAY:
            return self.take(self.number("i", 4))
        if kind == STRING:
            return self.string()
        if kind == LIST:
            inner = self.number("b", 1)
            count = self.number("i", 4)
            # ⚠️ Пустой список помечен типом END — это законно, и без проверки
            # разбор уходит в мусор.
            if inner == END or count <= 0:
                return []
            return [self.payload(inner) for _ in range(count)]
        if kind == COMPOUND:
            out: dict = {}
            while True:
                kind_inner = self.number("b", 1)
                if kind_inner == END:
                    return out
                name = self.string()
                out[name] = self.payload(kind_inner)
        if kind == INT_ARRAY:
            return [self.number("i", 4) for _ in range(self.number("i", 4))]
        if kind == LONG_ARRAY:
            return [self.number("q", 8) for _ in range(self.number("i", 4))]
        raise ValueError(f"неизвестный тег NBT: {kind}")


def read(data: bytes) -> dict:
    """Разбирает распакованный NBT: корневой тег -> словарь."""
    reader = Reader(data)
    kind = reader.number("b", 1)
    if kind != COMPOUND:
        raise ValueError(f"корень NBT не compound, а {kind}")
    reader.string()  # имя корня, обычно пустое
    return reader.payload(COMPOUND)


def read_item_bytes(encoded: str) -> dict:
    """`item_bytes` из API аукциона: base64 -> gzip -> NBT."""
    return read(gzip.decompress(base64.b64decode(encoded)))


def find(node, name: str):
    """
    Первое значение с таким именем на любой глубине.

    Нужно ровно потому, что раскладка гибридная: `ExtraAttributes` лежит
    внутри `tag`, а `tag` — внутри элемента списка `i`. Ходить по этому пути
    руками значит закрепить в коде предположение, которое сервер однажды
    поменяет молча.
    """
    if isinstance(node, dict):
        if name in node:
            return node[name]
        for value in node.values():
            found = find(value, name)
            if found is not None:
                return found
    elif isinstance(node, list):
        for value in node:
            found = find(value, name)
            if found is not None:
                return found
    return None
