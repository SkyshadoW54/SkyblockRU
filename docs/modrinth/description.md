# SkyblockRU — Russian translation for Hypixel SkyBlock

**Client-side Fabric mod that translates Hypixel SkyBlock into Russian.**
It rewrites chat, item descriptions, menus, the sidebar and tooltips — and nothing else.

> ⚠️ **BETA. The translation is incomplete and will never be 100% complete.**
> Hypixel constantly adds and rewrites text, so you *will* run into untranslated
> descriptions and dialogue. That is expected, not a bug.

### 📺 [Video: how to install it, and how it looks in game](https://www.youtube.com/watch?v=lGsedIysk44)

Step-by-step installation walkthrough (in Russian) plus the translation in action.

---

## Data collection

The mod sends data to the author's server. It is **on by default**, the mod tells you
about it in chat the first time you join SkyBlock, and you can turn it off at any time
with `/skyblockru telemetry off`.

**What is sent:**

| what | details |
|---|---|
| untranslated text | interface text the mod could **not** translate: item descriptions, menus, server messages, NPC dialogue |
| item tooltips | the original English text of item tooltips you opened (item name and lines in order), so sentences split across lines can be put back together for translation |
| versions | mod version and Minecraft version, e.g. `0.2.31+26.2` and `26.2` |
| installation ID | a random ID the mod generates on your computer and keeps in its config. It is not linked to your Minecraft account and is used only to count how many people use the mod |

**What is not sent:** your username, UUID or profile; other players' chat; party,
guild, co-op and private messages; messages you type. Player names found
inside game text are replaced with a placeholder or the line is dropped — first
in the mod, then again on the server.

**When:** only while you are in SkyBlock — when you leave a server or close the game,
at most once every 30 minutes, plus a short ping (versions and installation ID only)
when you join SkyBlock, at most once every 20 hours. Each line and tooltip is sent once.

**Who sees it:** only the mod's author. It is stored on the project's server, used
only to extend the translation and never shared. IP addresses are not stored —
only a temporary hash used for rate limiting.

* Privacy policy: https://skyblockru.duckdns.org/privacy
* Endpoint: `https://skyblockru.duckdns.org/submit`

Translations are also **downloaded** from cloud storage (Yandex Cloud) when you join
Hypixel, so the wording improves without reinstalling the mod. Only dictionary files
(JSON) are downloaded — never code.

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
* Minecraft **26.1 / 26.1.1 / 26.1.2 / 26.2 / 26.3**
* Client-side only — the server never knows the mod is there
* No `@Overwrite`: the mod only adds Mixin injection hooks, so it coexists with other mods
* Does not affect gameplay and gives no advantage: it changes text and nothing else

⚠️ Hypixel only allows SkyBlock on recent Minecraft versions; 1.21.11 and older
no longer work there, and the mod is no longer updated for them.

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

## Credits

The in-game reference (Shift / Alt) is based on information from the
[Hypixel SkyBlock Wiki](https://hypixel-skyblock.fandom.com), licensed CC BY-SA.
Thanks to its editors.

Not affiliated with Hypixel or Mojang.

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

Мод отправляет данные на сервер автора. Отправка **включена по умолчанию**, мод
сообщает о ней в чате при первом заходе в SkyBlock, а выключить её можно в любой момент:
`/skyblockru telemetry off`.

**Что уходит:**

| что | подробности |
|---|---|
| непереведённый текст | надписи, которые мод **не смог** перевести: описания предметов, меню, сообщения сервера, реплики NPC |
| подсказки предметов | английский текст подсказок предметов, которые вы открывали (имя и строки по порядку): из них собираются фразы, разрезанные переносом строк |
| версии | версия мода и версия игры, например `0.2.31+26.2` и `26.2` |
| метка установки | случайное число, которое мод придумывает на вашем компьютере и хранит в своих настройках. С аккаунтом Minecraft оно не связано; по нему видно только, сколькими людьми мод пользуется |

**Что не уходит:** ваш ник, UUID и данные профиля; чат других игроков; сообщения
пати, гильдии, кооператива и личные сообщения; то, что вы пишете в чат. Ники,
найденные в тексте игры, заменяются пустым местом, либо строка не отправляется
вовсе — сначала в самом моде, потом ещё раз на сервере.

**Когда:** только из SkyBlock — при выходе с сервера или из игры, не чаще раза
в 30 минут, плюс короткая отметка (версии и метка установки) при входе в SkyBlock,
не чаще раза в 20 часов. Каждая строка и подсказка уходит один раз.

**Кто видит:** только автор мода. Данные лежат на сервере проекта, используются
только для пополнения перевода и никому не передаются. IP-адреса не записываются —
хранится только временный отпечаток для защиты от потока запросов.

Политика: https://skyblockru.duckdns.org/privacy

Словари при этом **скачиваются** из облачного хранилища (Yandex Cloud) при заходе
на Hypixel — перевод пополняется без переустановки мода. Скачиваются только
словари (JSON), код — никогда.

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
* Minecraft **26.1 / 26.1.1 / 26.1.2 / 26.2 / 26.3**
* мод клиентский: сервер о нём не знает
* в игру не вмешивается и преимуществ не даёт — меняет только текст

⚠️ Hypixel пускает в SkyBlock только с новых версий игры: на 1.21.11 и ниже
SkyBlock не работает, и мод для них больше не обновляется.

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

## Благодарности

Справка в игре (Shift / Alt) составлена по материалам
[Hypixel SkyBlock Wiki](https://hypixel-skyblock.fandom.com) (лицензия CC BY-SA).
Спасибо её редакторам.

Мод не связан с Hypixel и Mojang.

## Лицензия и исходники

MIT. Исходный код: https://github.com/SkyshadoW54/SkyblockRU
