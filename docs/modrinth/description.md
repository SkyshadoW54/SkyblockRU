# SkyblockRU — Russian translation for Hypixel SkyBlock

**Client-side Fabric mod that translates Hypixel SkyBlock into Russian.**
It rewrites chat, item descriptions, menus, the sidebar and tooltips — and nothing else.

> ⚠️ **BETA. The translation is incomplete and will never be 100% complete.**
> Hypixel constantly adds and rewrites text, so you *will* run into untranslated
> descriptions and dialogue. That is expected, not a bug.

### 📺 [Video: how to install it, and how it looks in game](https://www.youtube.com/watch?v=lGsedIysk44)

Step-by-step installation walkthrough (in Russian) plus the translation in action.

---

## Data collection disclosure

This mod sends data to a server. Read this before installing.

**What is sent** — three things, and nothing else:

| field | value |
|---|---|
| `mod` | mod version, e.g. `0.2.0+26.2` |
| `game` | Minecraft version, e.g. `26.2` |
| `lines` | interface strings the mod could **not** translate |

**What is never sent:** your username, your UUID, your profile, your IP beyond the
plain HTTP request, chat from other players, party/guild/co-op messages, private
messages, or anything you type. Player chat is filtered out before sending.

**Why:** the mod is built from strings that were actually seen in game. Lines it
cannot translate are exactly the ones that still need work, so they are collected
to extend the translation.

**When:** at most once every 30 minutes, when you leave a server or close the game.
Each unique line is sent only once, ever.

**How to turn it off:** `/skyblockru telemetry off` — in game, at any time.
The mod tells you about this collection in chat on first launch.

* Endpoint: `https://skyblockru.duckdns.org/submit`
* Privacy policy: `https://skyblockru.duckdns.org/privacy`

Translations are also **downloaded** from cloud storage when you join Hypixel, so
the wording improves without reinstalling the mod. Only dictionary files (JSON) are
downloaded — never code.

---

## What it translates

* item descriptions (lore), abilities, enchantment descriptions
* chat, NPC dialogue, quest text
* menus, the sidebar, the tab list, the bar above the hotbar
* an in-game reference: hold **Shift** on an item for an explanation of a stat,
  **Alt** for enchantments, **V** to see the original English tooltip

## What it deliberately leaves in English

This is a design decision, not an omission:

* **item names** — you search for them on the Auction House
* **NPC names and location names** — so guides and the wiki still match
* **stat jargon** (`Mining Fortune`, `Magic Find`, `Pristine`) — a one-word
  translation would not explain the mechanic; press **Shift** for a Russian
  explanation instead

## Compatibility

* **Fabric** only. **Fabric API is required.**
* Minecraft **1.21.11** and **26.1 / 26.1.1 / 26.1.2 / 26.2**
* Client-side only — the server never knows the mod is there
* Uses `@Inject` hooks only, no `@Overwrite`, so it coexists with other mods
* Does not affect gameplay and gives no advantage: it changes text and nothing else

⚠️ Hypixel does not allow SkyBlock below Minecraft 1.21.11. Older builds will not
connect, no matter what the mod supports.

## Installation

1. Install **Fabric Loader**
2. Put **Fabric API** and **SkyblockRU** into your `mods` folder
3. Launch the game and join Hypixel

## Commands

| command | what it does |
|---|---|
| `/skyblockru` | version, build, status |
| `/skyblockru on` / `off` | turn translation on or off |
| `/skyblockru telemetry on` / `off` | turn data collection on or off |
| `/skyblockru update` | check for translation updates now |

## License and source

MIT. Source code: https://github.com/SkyshadoW54/SkyblockRU

---

# SkyblockRU — русификатор Hypixel SkyBlock

**Клиентский Fabric-мод: переводит Hypixel SkyBlock на русский** — чат, описания
предметов, меню, боковую панель и подсказки.

> ⚠️ **МОД В БЕТЕ. Перевод неполный и полным не будет.**
> Hypixel постоянно добавляет и переписывает тексты, поэтому непереведённые
> описания и диалоги вы встретите обязательно. Это ожидаемо, а не поломка.

### 📺 [Видеоинструкция: как установить мод и как он выглядит в игре](https://www.youtube.com/watch?v=lGsedIysk44)

Если ставите моды впервые — посмотрите видео, там показан весь порядок действий.

## Что отправляется разработчику

Мод отправляет **версию мода, версию игры и строки интерфейса, которые не смог
перевести** — больше ничего. Ники, чат игроков, личные сообщения, сообщения гильдии
и группы, UUID и данные профиля не отправляются никогда: чат игроков отсекается
до отправки.

Зачем: непереведённые строки — это и есть список работы, из них пополняется перевод.

Отключить: `/skyblockru telemetry off`. Политика: `https://skyblockru.duckdns.org/privacy`

Словари при этом **скачиваются** с сервера при заходе на Hypixel — перевод
пополняется без переустановки мода. Скачиваются только словари (JSON), код — никогда.

## Что переводится

* описания предметов, способности, описания зачарований
* чат, реплики NPC, задания
* меню, боковая панель, список игроков, полоса над хотбаром
* справка в игре: **Shift** — пояснение характеристики, **Alt** — зачарования,
  **V** — показать оригинал на английском

## Что намеренно оставлено английским

* **названия предметов** — по ним ищут на аукционе
* **имена NPC и названия локаций** — чтобы сходилось с гайдами и вики
* **жаргон характеристик** (`Mining Fortune`, `Magic Find`, `Pristine`) — одним
  словом механику не объяснить, поэтому под них написана справка по **Shift**

## Совместимость

* только **Fabric**, **нужен Fabric API**
* Minecraft **1.21.11** и **26.1 / 26.1.1 / 26.1.2 / 26.2**
* мод клиентский: сервер о нём не знает
* в игру не вмешивается и преимуществ не даёт — меняет только текст

⚠️ Hypixel не пускает в SkyBlock на версиях ниже 1.21.11.

## Установка

📺 **Показано на видео:** [пошаговая установка](https://www.youtube.com/watch?v=lGsedIysk44)

1. Поставить **Fabric Loader**
2. Положить **Fabric API** и **SkyblockRU** в папку `mods`
3. Запустить игру и зайти на Hypixel

## Команды

| команда | что делает |
|---|---|
| `/skyblockru` | версия, сборка, состояние |
| `/skyblockru on` / `off` | включить или выключить перевод |
| `/skyblockru telemetry on` / `off` | включить или выключить отправку строк |
| `/skyblockru update` | проверить обновление перевода сейчас |

## Лицензия и исходники

MIT. Исходный код: https://github.com/SkyshadoW54/SkyblockRU
