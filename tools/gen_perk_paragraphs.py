# -*- coding: utf-8 -*-
"""
СЕМЬЯ ПЕРКОВ И ОСКОЛКОВ: «X (Skill) Grants … TERM.» — механически.

Рамка у них одна на сотни записей, меняются имя перка и ХАРАКТЕРИСТИКА
в хвосте. Имя перка не переводим (оно же стоит заголовком), а термин
берём по таблице:

  * ЖАРГОН (`terms.STAT_JARGON`) остаётся английским — решение проекта;
  * базовая характеристика ставится в РОДИТЕЛЬНЫЙ падеж: управляющее
    слово «Даёт» требует именно его («Даёт +5 Здоровья», «+5 защиты»).

⚠️ Термина нет ни в жаргоне, ни в таблице — абзац уходит на ручной
перевод. Иначе в описание уехала бы английская характеристика посреди
русской фразы, а это худший вид ошибки.

⚠️ Хвост совпадает ЦЕЛИКОМ (^…$), поэтому непереведённого куска
остаться не может по построению.
"""
import json, io, re, sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, 'tools')
import terms as _terms

JARGON = set(_terms.STAT_JARGON)

# ⚠️ Родительный падеж — потому что управляющее слово «Даёт».
GEN = {
    'Health': 'Здоровья',
    'Strength': 'Силы',
    'Defense': 'защиты',
    'True Defense': 'истинной защиты',
    'Speed': 'Скорости',
    'Intelligence': 'Интеллекта',
    'Damage': 'урона',
    'Ability Damage': 'Урона способностей',
    'Crit Damage': 'Урона крита',
    'Crit Chance': 'Шанса крита',
    'Attack Speed': 'Скорости атаки',
    'Mana': 'маны',
    'Mining Fortune': 'Mining Fortune',
}


def term_ru(name):
    name = name.strip()
    if name in GEN:
        return GEN[name]
    if name in JARGON:
        return name
    return None


HEAD = re.compile(r"^(?P<head>(?:[A-Za-z'’\- ]+?(?: [IVXLC]+)?(?: \((?:Global|\w+)\))? )?)"
                  r"(?P<tail>(?:Grants|Gain|Increase|Increases|You have|Your |Trophy).*)$")

# (шаблон хвоста, сборщик перевода). Формы взяты из купленных образцов.
TAILS = [
    (re.compile(r'^Grants \{n\}(\{i\d+\})\+\{n\} (\{i\d+\}) ([A-Za-z \'’]+)\.$'),
     lambda m, t: 'Даёт {n}%s+{n} %s %s.' % (m.group(1), m.group(2), t)),

    (re.compile(r'^Grants \+\{n\} (\{i\d+\}) ([A-Za-z \'’]+)\.$'),
     lambda m, t: 'Даёт +{n} %s %s.' % (m.group(1), t)),

    (re.compile(r'^Grants \{n\}%(\{i\d+\})\+\{n\}% more (\{i\d+\}) Damage against '
                r'(\{i\d+\}) ([A-Za-z]+) mobs\.$'),
     lambda m, t: 'Даёт на {n}%%%s+{n}%% больше %s урона против %s %s мобов.'
                  % (m.group(1), m.group(2), m.group(3), m.group(4))),

    (re.compile(r'^Grants \{n\}(\{i\d+\})\+\{n\} (\{i\d+\}) Defense against '
                r'(\{i\d+\}) ([A-Za-z]+) mobs\.$'),
     lambda m, t: 'Даёт {n}%s+{n} %s защиты против %s %s мобов.'
                  % (m.group(1), m.group(2), m.group(3), m.group(4))),

    (re.compile(r'^Grants \+\{n\} (\{i\d+\}) Defense against (\{i\d+\}) ([A-Za-z]+) mobs\.$'),
     lambda m, t: 'Даёт +{n} %s защиты против %s %s мобов.'
                  % (m.group(1), m.group(2), m.group(3))),

    (re.compile(r'^Increase damage to (\{i\d+\}) ([A-Za-z]+) mobs by '
                r'\{n\}%(\{i\d+\})\+\{n\}%\.$'),
     lambda m, t: 'Повышает урон по %s %s мобам на {n}%%%s+{n}%%.'
                  % (m.group(1), m.group(2), m.group(3))),

    (re.compile(r'^Grants \{n\}%(\{i\d+\})\+\{n\}% more experience orbs from '
                r'killing mobs\.$'),
     lambda m, t: 'Даёт на {n}%%%s+{n}%% больше сфер опыта за убийство мобов.' % m.group(1)),

    (re.compile(r'^Gain \{n\}%(\{i\d+\})\+\{n\}% more Coins from fishing treasures\.$'),
     lambda m, t: 'Даёт на {n}%%%s+{n}%% больше монет с рыбацких сокровищ.' % m.group(1)),

    (re.compile(r'^Grants \{n\}(\{i\d+\})\+\{n\} (\{i\d+\}) Sweep during the night\.$'),
     lambda m, t: 'Даёт {n}%s+{n} %s Sweep ночью.' % (m.group(1), m.group(2))),

    (re.compile(r'^Grants \{n\}(\{i\d+\})\+\{n\} (\{i\d+\}) Sweep for each unique '
                r'Common Attribute you own\.$'),
     lambda m, t: 'Даёт {n}%s+{n} %s Sweep за каждый уникальный Common Attribute у тебя.'
                  % (m.group(1), m.group(2))),

    (re.compile(r'^Grants \{n\}(\{i\d+\})\+\{n\} (\{i\d+\}) ([A-Za-z \'’]+) while on '
                r'(Mining|Foraging|Fishing|Farming) Islands\.$'),
     lambda m, t: 'Даёт {n}%s+{n} %s %s на %s Islands.'
                  % (m.group(1), m.group(2), t, m.group(4))),

    (re.compile(r'^You have a \{n\}%(\{i\d+\})\+\{n\}% chance to gain extra Chums\.$'),
     lambda m, t: 'У тебя {n}%%%s+{n}%% шанс получить дополнительные Chums.' % m.group(1)),

    (re.compile(r'^Grants a \{n\}%(\{i\d+\})\+\{n\}% chance to drop double Berries '
                r'and Sea Lumies\.$'),
     lambda m, t: 'Даёт {n}%%%s+{n}%% шанс выбить вдвое больше Berries и Sea Lumies.'
                  % m.group(1)),

    (re.compile(r'^Grants \{n\}(\{i\d+\})\+\{n\} (\{i\d+\}) Fig Fortune and '
                r'\{n\}(\{i\d+\})\+\{n\} (\{i\d+\}) Mangrove Fortune\.$'),
     lambda m, t: 'Даёт {n}%s+{n} %s Fig Fortune и {n}%s+{n} %s Mangrove Fortune.'
                  % (m.group(1), m.group(2), m.group(3), m.group(4))),

    (re.compile(r'^Your Dragon Shortbow gains \{n\}%(\{i\d+\})\+\{n\}% more '
                r'(\{i\d+\}) Damage while in The End\.$'),
     lambda m, t: 'Твой Dragon Shortbow наносит на {n}%%%s+{n}%% больше %s урона в The End.'
                  % (m.group(1), m.group(2))),

    (re.compile(r'^Your Dragon Shortbow gains \+\{n\}% more (\{i\d+\}) Damage '
                r'while in The End\.$'),
     lambda m, t: 'Твой Dragon Shortbow наносит на +{n}%% больше %s урона в The End.'
                  % m.group(1)),

    (re.compile(r'^Increases the odds of finding monsters from Tree Gifts by '
                r'\{n\}%(\{i\d+\})\+\{n\}%\.$'),
     lambda m, t: 'Повышает шанс найти монстров в Tree Gifts на {n}%%%s+{n}%%.' % m.group(1)),

    # «Gain X% more <что-то>» — общая форма прибавки, захват это ИМЯ
    # ресурса или опыта и остаётся английским.
    (re.compile(r'^Gain \{n\}%(\{i\d+\})\+\{n\}% more ([A-Za-z \'’]+)\.$'),
     lambda m, t: 'Даёт на {n}%%%s+{n}%% больше %s.' % (m.group(1), m.group(2))),

    (re.compile(r'^Gain \+\{n\}% more ([A-Za-z \'’]+)\.$'),
     lambda m, t: 'Даёт на +{n}%% больше %s.' % m.group(1)),

    (re.compile(r'^Trophy Frogs are \{n\}(\{i\d+\})\+\{n\}% more likely to be GOLD\.$'),
     lambda m, t: 'Trophy Frogs на {n}%s+{n}%% чаще попадаются GOLD.' % m.group(1)),
]

# хвост, где термин стоит в захвате: у этих правил берём его из группы 3
TERM_AT = {0: 3, 1: 2, 10: 3}

HOLE = re.compile(r'\{[ns]\}')
MASK = re.compile(r'\{i\d+\}')


ATTR = re.compile(r'^(?P<body>.*?) Your Attribute: Level \{n\} '
                  r'\(\{n\} more stacks to Level \{n\}\)$')
ATTR_RU = ' Твой Attribute: уровень {n} (ещё {n} стопок до уровня {n})'


def translate(text):
    # ⚠️ У перков бывает ХВОСТ со счётчиком стопок. Он одинаков у всех,
    # поэтому отрезаем его, переводим тело обычным порядком и приклеиваем
    # готовый перевод хвоста — иначе каждая рамка удваивалась бы.
    tail = ATTR.match(text)
    if tail:
        body = translate(tail.group('body'))
        return body + ATTR_RU if body else None
    m = HEAD.match(text)
    if not m:
        return None
    head, tail = m.group('head'), m.group('tail')
    for k, (rx, make) in enumerate(TAILS):
        tm = rx.match(tail)
        if not tm:
            continue
        t = None
        if k in TERM_AT:
            t = term_ru(tm.group(TERM_AT[k]))
            if t is None:
                # ⚠️ Не выходим, а пробуем ОСТАЛЬНЫЕ правила: широкий шаблон
                # «Grants … TERM.» съедает и «Sweep during the night», где
                # термин на самом деле короче, а хвост — обстоятельство.
                continue
        return head + make(tm, t)
    return None


def main():
    # ⚠️ В КОРПУСЕ значки лежат НАСТОЯЩИЕ (приватная зона), а маски {iN}
    # появляются только в выгрузке задания. Поэтому правила писаны по
    # маскированному виду, а перед записью значки возвращаются на место —
    # тем же механизмом, что у ручного прогона.
    import translate_tooltips as tt

    dry = '--yes' not in sys.argv
    path = 'data/work/paragraphs.json'
    d = json.load(io.open(path, encoding='utf-8'))
    rows = d[list(d)[0]]
    done = shown = 0
    out = []
    for r in rows:
        text = (r.get('text') or '').strip()
        if r.get('ru') or r.get('nothing') or not text:
            continue
        masked, icons = tt.mask_icons(text)
        ru = translate(masked)
        if not ru:
            continue
        for mark, char in icons.items():
            ru = ru.replace(mark, char)
        text = masked
        for mark, char in icons.items():
            text = text.replace(mark, char)
        if (len(HOLE.findall(text)) != len(HOLE.findall(ru))
                or MASK.findall(text) != MASK.findall(ru)):
            continue
        if shown < 8:
            out.append('   ' + text[:88])
            out.append('-> ' + ru[:88])
            shown += 1
        done += 1
        if not dry:
            r['ru'] = ru
    out.append('')
    out.append('переведено рамкой: %d' % done)
    if not dry:
        json.dump(d, io.open(path, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        out.append('записано')
    else:
        out.append('сухой прогон. Применить: --yes')
    print(chr(10).join(out))


if __name__ == '__main__':
    main()
