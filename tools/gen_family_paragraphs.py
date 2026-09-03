# -*- coding: utf-8 -*-
"""
СЕМЬИ АБЗАЦЕВ — механический перевод по рамке.

Все формы взяты из УЖЕ КУПЛЕННЫХ переводов (образцы найдены в корпусе),
а не придуманы: «Улучшает вещь до X! Это даёт ещё +{n}% к характеристикам.»,
«Шлем: … Кираса: … Поножи: … Ботинки: …», «Обычная добыча …» и т. д.

⚠️ ПЕРЕВОДИТСЯ ТОЛЬКО РАМКА. Захват — это имя предмета или список имён,
и в обычном режиме он остаётся английским по решению проекта.

⚠️ ЗАЩИТА ОТ ПРОЗЫ В ЗАХВАТЕ: если внутри захвата встретилось служебное
английское слово («you», «and», «with»), это не список имён, а фраза —
такой абзац уходит на ручной перевод. Без этого «Instantly sell all X»
затянуло бы в рамку целые предложения.

⚠️ Проверка та же, что у ручного прогона: число дырок {n}/{s} и набор
масок {iN} обязаны совпасть с оригиналом.
"""
import json, io, re, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PROSE = re.compile(r'\b(?:you|your|and|with|when|the|from|for|that|this|will|are|is|'
                   r'to|of|in|on|by|be|can|it|its|have|has|more|than|while|per|'
                   r'gain|grants|increase|increases|reduce|reduces|click|right|left)\b',
                   re.I)


def clean(part):
    """Захват годится, только если это имена, а не проза."""
    return not PROSE.search(part)


def slot(value):
    v = value.strip()
    if v == 'None':
        return 'нет'
    if v == 'Empty':
        return 'пусто'
    return value


RULES = [
    (re.compile(r'^Upgrades the item to an? (.+)! This grants an additional \{n\}% '
                r'stat bonus\.$'),
     lambda m: 'Улучшает вещь до %s! Это даёт ещё +{n}%% к характеристикам.' % m.group(1)),

    (re.compile(r'^Helmet: (.*?) Chestplate: (.*?) Leggings: (.*?) Boots: (.*)$'),
     lambda m: 'Шлем: %s Кираса: %s Поножи: %s Ботинки: %s'
               % tuple(slot(m.group(i)) for i in (1, 2, 3, 4))),

    (re.compile(r'^Necklace: (.*?) Cloak: (.*?) Belt: (.*?) Gloves/Bracelet: (.*)$'),
     lambda m: 'Ожерелье: %s Плащ: %s Пояс: %s Перчатки/браслет: %s'
               % tuple(slot(m.group(i)) for i in (1, 2, 3, 4))),

    (re.compile(r'^Contents (.+)$'), lambda m: 'Содержимое ' + m.group(1)),
    (re.compile(r'^Items Returned (.+)$'), lambda m: 'Возвращено предметов ' + m.group(1)),
    (re.compile(r'^Items Required:? (.+)$'), lambda m: 'Нужны предметы: ' + m.group(1)),

    (re.compile(r'^Common Loot (.+)$'), lambda m: 'Обычная добыча ' + m.group(1)),
    (re.compile(r'^Uncommon Loot (.+)$'), lambda m: 'Необычная добыча ' + m.group(1)),
    (re.compile(r'^Rare Loot (.+)$'), lambda m: 'Редкая добыча ' + m.group(1)),
    (re.compile(r'^RNGesus Loot (.+)$'), lambda m: 'Добыча RNGesus ' + m.group(1)),

    (re.compile(r'^Sources: (.+)$'), lambda m: 'Источники: ' + m.group(1)),
    (re.compile(r'^Conflicts: (.+)$'), lambda m: 'Не сочетается с: ' + m.group(1)),
    (re.compile(r'^Applied To: (.+)$'), lambda m: 'Ставится на: ' + m.group(1)),

    (re.compile(r'^Located in (.+) at (.+)\.$'),
     lambda m: 'Находится в %s на %s.' % (m.group(1), m.group(2))),

    (re.compile(r'^(?:Right-Click to set amount! )?Recipe not unlocked! '
                r'(\{i\d+\} )?Requires (.+) Collection ([IVXLC]+)\.$'),
     lambda m: ('ПКМ — задать количество! ' if m.string.startswith('Right-Click')
                else '') + 'Рецепт не открыт! ' + (m.group(1) or '')
               + 'Нужна коллекция %s %s.' % (m.group(2), m.group(3))),

    (re.compile(r'^(.+) will leave your Garden and maybe come back later\.$'),
     lambda m: '%s уйдёт из твоего Garden и, может быть, вернётся позже.' % m.group(1)),

    (re.compile(r'^Source: (.+) Rarity: (\w+) Enabled: Yes$'),
     lambda m: 'Источник: %s Редкость: %s Включено: да' % (m.group(1), m.group(2))),
    (re.compile(r'^Source: (.+) Rarity: (\w+) Enabled: No$'),
     lambda m: 'Источник: %s Редкость: %s Включено: нет' % (m.group(1), m.group(2))),

    (re.compile(r'^Appears In: (.+) Odds: (.+)$'),
     lambda m: 'Встречается в: %s Шансы: %s' % (m.group(1), m.group(2))),
    (re.compile(r'^Minimum: Tier ([IVXLC]+) Odds: (.+)$'),
     lambda m: 'Минимум: ступень %s Шансы: %s' % (m.group(1), m.group(2))),

    (re.compile(r'^Manage the Tablist Widgets you see when in (?:the )?(.+)\.$'),
     lambda m: 'Настрой виджеты таба, которые видно в %s.' % m.group(1)),
    (re.compile(r'^Manage the Tablist Widgets you see when on (?:the |a )?(.+)\.$'),
     lambda m: 'Настрой виджеты таба, которые видно на %s.' % m.group(1)),

    (re.compile(r'^Opened Chest: (\S+) Chests expire in (.+)!$'),
     lambda m: 'Открыт сундук: %s Сундуки исчезнут через %s!'
               % (m.group(1), m.group(2).replace('{n}d', '{n} д')
                  .replace('{n}h', '{n} ч').replace('{n}m', '{n} м'))),

    (re.compile(r'^You need \{n\} more (.+)\.$'),
     lambda m: 'Нужно ещё {n} %s.' % m.group(1)),

    (re.compile(r'^To rank on the (.+) Family leaderboard, you must have at least '
                r'\{n\} kill!$'),
     lambda m: 'Чтобы попасть в таблицу лидеров семейства %s, нужно хотя бы {n} убийство!'
               % m.group(1)),

    (re.compile(r'^View all your (.+) Collection progress and rewards!$'),
     lambda m: 'Посмотри весь прогресс и награды коллекции %s!' % m.group(1)),

    (re.compile(r'^(Rabbit [A-Za-z]+) is a Board Member\. They are on the Board of '
                r'Rabbits and produce \+\{n\} Chocolate per second!$'),
     lambda m: '%s — член совета. Заседает в Board of Rabbits и даёт '
               '+{n} Chocolate в секунду!' % m.group(1)),

    (re.compile(r'^(Rabbit [A-Za-z]+) is an Executive\. They are kind of a big deal, '
                r'and produce \+\{n\} Chocolate per second!$'),
     lambda m: '%s — начальство. Птица важная и даёт +{n} Chocolate '
               'в секунду!' % m.group(1)),

    (re.compile(r'^(Rabbit [A-Za-z]+) is a Director\. They are now in charge of all the '
                r'rabbits that produce \+\{n\} Chocolate per second!$'),
     lambda m: '%s — директор. Теперь под его началом все кролики, что дают '
               '+{n} Chocolate в секунду!' % m.group(1)),

    (re.compile(r'^Current account: (.+) Co-op bank limit: \{n\}$'),
     lambda m: 'Текущий аккаунт: %s Предел банка кооператива: {n}' % m.group(1)),

    (re.compile(r'^Redeem \{n\} more (.+) Chips to upgrade this chip to EPIC!$'),
     lambda m: 'Сдай ещё {n} %s Chips, чтобы поднять этот чип до EPIC!' % m.group(1)),

    (re.compile(r'^Progress to (.+): \{n\}% (.+)$'),
     lambda m: 'Прогресс до %s: {n}%% %s' % (m.group(1), m.group(2))),

    (re.compile(r'^Donating an? (.+) will count as donating this item\.$'),
     lambda m: 'Пожертвование %s зачтётся как пожертвование этого предмета.' % m.group(1)),

    # ⚠️ Кролики Chocolate Factory: форма БЕЗ РОДА, у Hypixel там «They».
    (re.compile(r'^(Rabbit [A-Za-z]+) is an Assistant to the regional manager\. '
                r'They are now able to produce \+\{n\} Chocolate per second!$'),
     lambda m: '%s — помощник регионального управляющего. '
               'Даёт +{n} Chocolate в секунду!' % m.group(1)),

    (re.compile(r'^(Rabbit [A-Za-z]+) is a Manager\. They now manage a team of rabbits '
                r'that produce \+\{n\} Chocolate per second!$'),
     lambda m: '%s — управляющий. Теперь целая команда кроликов даёт '
               '+{n} Chocolate в секунду!' % m.group(1)),

    (re.compile(r'^(Rabbit [A-Za-z]+) has climbed as far as the corporate ladder '
                r'will allow!$'),
     lambda m: '%s — выше по служебной лестнице уже некуда!' % m.group(1)),

    (re.compile(r'^Your Rabbit Barn is full, so (.+) was crushed into '
                r'\{n\} Chocolate!$'),
     lambda m: 'Твой Rabbit Barn переполнен, так что %s превратился '
               'в {n} Chocolate!' % m.group(1)),

    (re.compile(r'^Set the biome of your entire island to (.+)!$'),
     lambda m: 'Сделать биом всего твоего острова %s!' % m.group(1)),

    (re.compile(r'^Click on an? (.+) Biome Stick in your inventory to unlock!$'),
     lambda m: 'Нажми на %s Biome Stick в инвентаре, чтобы открыть!' % m.group(1)),

    (re.compile(r'^(.+) Slayer XP to LVL \{n\}: (.+)$'),
     lambda m: 'Опыт %s Slayer до уровня {n}: %s' % (m.group(1), m.group(2))),

    # ⚠️ Без рода: X — это жаргонная характеристика, она остаётся английской,
    # и «твой/твою» пришлось бы гадать.
    (re.compile(r'^Shows your (.+) if the widget is enabled when in a Garden\.$'),
     lambda m: 'Показывает %s, если виджет включён, когда ты в Garden.' % m.group(1)),

    (re.compile(r'^Modify your (\{i\d+\}) Speed Cap when harvesting (.+)\.$'),
     lambda m: 'Меняет твой %s предел скорости при сборе %s.' % (m.group(1), m.group(2))),

    # ⚠️ Род местоимения задаётся ЧАСТЬЮ удочки, а не гаданием:
    # Hook и Sinker мужского рода, Line женского.
    (re.compile(r'^Your (.+?) does not have an? (Hook|Sinker|Line)\. '
                r'Click on an? \2 in your inventory to apply it to the rod!$'),
     lambda m: 'На твоей %s нет %s. Нажми на %s в инвентаре, чтобы поставить %s '
               'на удочку!' % (m.group(1), m.group(2), m.group(2),
                               'её' if m.group(2) == 'Line' else 'его')),

    (re.compile(r'^Your (.+?) does not have an? (.+)!$'),
     lambda m: 'На твоей %s нет %s!' % (m.group(1), m.group(2))),

    (re.compile(r'^You have already found (.+), so you received \{n\} Chocolate!$'),
     lambda m: 'Ты уже нашёл %s, так что тебе досталось {n} Chocolate!' % m.group(1)),

    (re.compile(r'^Currently making: (.+) Time Remaining: Completed!$'),
     lambda m: 'Сейчас делается: %s Осталось времени: Готово!' % m.group(1)),

    # ⚠️ «X derivatives» сведено к одной форме 25.08: X бывает ИМЕНЕМ
    # (Gemstones, Revenant Horror, Dwarven Mines), и переводить его нельзя.
    (re.compile(r'^Instantly sell all (.+?) derivatives in your inventory\.$'),
     lambda m: 'Мгновенно продать все производные %s из твоего инвентаря.' % m.group(1)),

    (re.compile(r'^Upgrade Cost: (.+)$'),
     lambda m: 'Стоимость улучшения: ' + m.group(1).replace(' Coins', ' монет')),

    (re.compile(r'^Your order: SELL \{n\}x (.+) for \{n\} each$'),
     lambda m: 'Твой заказ: ПРОДАТЬ {n}x %s по {n} за штуку' % m.group(1)),

    (re.compile(r'^Your order: BUY \{n\}x (.+) for \{n\} each$'),
     lambda m: 'Твой заказ: КУПИТЬ {n}x %s по {n} за штуку' % m.group(1)),

    (re.compile(r'^Legendary Loot (.+)$'), lambda m: 'Легендарная добыча ' + m.group(1)),

    # ⚠️ «Coins» в ценнике переводим: замер по корпусу — «монет» стоит везде,
    # а форма «Стоит» побеждает «Стоимость» 122:47.
    (re.compile(r'^Cost (.+)$'),
     lambda m: 'Стоит ' + m.group(1).replace(' Coins', ' монет')),
]

HOLE = re.compile(r'\{[ns]\}')
MASK = re.compile(r'\{i\d+\}')

DRY = '--yes' not in sys.argv
path = 'data/work/paragraphs.json'
d = json.load(io.open(path, encoding='utf-8'))
rows = d[list(d)[0]]

done = skipped = shown = 0
for r in rows:
    text = (r.get('text') or '').strip()
    if r.get('ru') or r.get('nothing') or not text:
        continue
    for rx, make in RULES:
        m = rx.match(text)
        if not m:
            continue
        if not all(clean(g) for g in m.groups() if g):
            skipped += 1
            break
        ru = make(m)
        if (len(HOLE.findall(text)) != len(HOLE.findall(ru))
                or MASK.findall(text) != MASK.findall(ru)):
            skipped += 1
            break
        if shown < 6:
            print('   ' + text[:84])
            print('-> ' + ru[:84])
            shown += 1
        done += 1
        if not DRY:
            r['ru'] = ru
        break

print()
print('переведено рамкой: %d | на руки: %d' % (done, skipped))
if not DRY:
    json.dump(d, io.open(path, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print('записано')
else:
    print('сухой прогон. Применить: --yes')
