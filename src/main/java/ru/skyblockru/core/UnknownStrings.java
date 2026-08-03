package ru.skyblockru.core;

import com.google.gson.GsonBuilder;
import com.google.gson.JsonObject;
import net.minecraft.ChatFormatting;
import net.minecraft.client.Minecraft;
import net.minecraft.network.chat.Component;
import ru.skyblockru.SkyblockRuClient;
import ru.skyblockru.config.RuConfig;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;

/**
 * Сборщик непереведённых строк.
 *
 * <p>Полного дампа текстов SkyBlock нигде не существует: почти всё, кроме предметов,
 * живёт только на сервере и приходит пакетами по ходу игры. Поэтому мод сам
 * записывает всё, чему не нашёл перевода, — играешь, а список работы пополняется.
 *
 * <p>Файлы кладутся в config/skyblockru/dump/:
 * <ul>
 *   <li>untranslated.json — заготовка словаря, можно сразу переводить и класть в packs/;</li>
 *   <li>untranslated.txt — то же, но с частотой: сверху то, что мозолит глаза чаще всего.</li>
 * </ul>
 */
public final class UnknownStrings {

	/** Где встретилась строка: чат, описание предмета, сайдбар и т.д. */
	private static final Map<String, Map<String, AtomicInteger>> BY_SOURCE = new ConcurrentHashMap<>();

	/**
	 * Откуда взялась строка: имя предмета, чью подсказку читали, и т.п.
	 * Без этого переводчик видит «Storage unlocked at tier VIII» в вакууме и не знает,
	 * что речь о миньоне. С контекстом он переводит осмысленно.
	 */
	private static final Map<String, String> CONTEXTS = new ConcurrentHashMap<>();

	/** Порядок первой встречи — чтобы строки одной подсказки остались рядом. */
	private static final Map<String, Integer> ORDER = new ConcurrentHashMap<>();
	private static final AtomicInteger SEQ = new AtomicInteger();

	private static volatile boolean dirty;
	private static volatile long lastWrite;
	private static Path dumpDir;

	/** Копим новые строки и сообщаем пачкой: иначе большое меню зальёт чат. */
	private static final AtomicInteger pendingNotice = new AtomicInteger();
	private static volatile long lastNotice;
	private static final long NOTICE_INTERVAL_MS = 15_000L;

	/** Не чаще раза в 20 секунд — чтобы не дёргать диск в бою. */
	private static final long WRITE_INTERVAL_MS = 20_000L;

	/**
	 * Защита от утечки памяти, если попадётся поток мусорных строк.
	 *
	 * <p>⚠️ Поднят с 20 000 после того, как источник {@code item_lore} дошёл
	 * до 16785 — то есть до молчаливой остановки сбора оставалось несколько
	 * вечеров. Файл накопительный, и упор в потолок здесь не «защита сработала»,
	 * а «мы перестали видеть новые строки, не заметив этого».
	 */
	private static final int MAX_PER_SOURCE = 60_000;

	/** Источники, по которым уже сказали об упоре: жалуемся один раз на каждый. */
	private static final java.util.Set<String> fullSources =
			java.util.concurrent.ConcurrentHashMap.newKeySet();

	/**
	 * Источники, которые опрашиваются на каждом кадре отрисовки.
	 * Для них считаем строку один раз: иначе название предмета под курсором
	 * набьёт 60 «встреч» в секунду и утопит в списке реальные сообщения чата.
	 */
	private static final java.util.Set<String> RENDERED_EVERY_FRAME = java.util.Set.of(
			"item_name", "item_lore", "scoreboard", "tab", "boss_bar", "name_tag", "screen");

	private UnknownStrings() {
	}

	/**
	 * Подсказки предметов целиком, а не построчно.
	 *
	 * <p>Обрывок фразы («Bag.», «each.») в отрыве от соседей перевести нельзя,
	 * а одна и та же строка у разных предметов может продолжать разные фразы.
	 * Поэтому запоминаем подсказку блоком: мод и так получает весь её список
	 * разом, надо просто не разбирать его на отдельные строки.
	 */
	private static final Map<String, String[]> TOOLTIPS = new ConcurrentHashMap<>();

	/** Имя предмета для каждого блока — тем же ключом. */
	private static final Map<String, String> TOOLTIP_ITEM = new ConcurrentHashMap<>();

	/**
	 * ИДЕНТИФИКАТОР предмета из NBT — то, чего у нас никогда не было.
	 *
	 * <p><b>Зачем.</b> Весь перевод в этом проекте привязан к ТЕКСТУ: ключом
	 * служит сама строка, обобщённая по числам, очищенная от цветов и склеенная
	 * из кусков, которые сервер разрезал по ширине окна ИГРОКА. Каждое звено —
	 * место, где стороны могут разойтись, и почти все грабли проекта оттуда:
	 * имя предмета вклеилось в ключ, ширину выбирает игрок, обобщение
	 * применили к одной стороне из двух.
	 *
	 * <p>А у предмета есть настоящий идентификатор: Hypixel кладёт его в NBT
	 * (исторически {@code ExtraAttributes.id}, в компонентах 1.20.5+ он живёт
	 * внутри {@code minecraft:custom_data}). Он не зависит ни от ширины окна,
	 * ни от цветов, ни от прокачки.
	 *
	 * <p>⚠️ Пока это РАЗВЕДКА, а не механизм перевода. Мы не знаем наверняка,
	 * что именно Hypixel кладёт и всем ли предметам: гадать об этом нельзя,
	 * надо посмотреть. Поэтому мод просто записывает, что нашёл, — какие ключи
	 * лежат в custom_data и какой у предмета id. Дальше решаем по фактам.
	 *
	 * <p>Файл НАКОПИТЕЛЬНЫЙ: это данные от сервера, а не отчёт о поведении мода
	 * (см. check_dump_persistence.py). От версии jar они не зависят.
	 */
	private static final Map<String, String> ITEM_IDS = new ConcurrentHashMap<>();

	/** Какие вообще ключи встречаются в custom_data — со счётчиком. */
	private static final Map<String, Integer> NBT_KEYS = new ConcurrentHashMap<>();

	private static final int MAX_ITEM_IDS = 30_000;

	/**
	 * Запоминает связку «id предмета -> его отображаемое имя».
	 *
	 * @param id   идентификатор из NBT; пустой — значит его там не оказалось
	 * @param name имя, которое видит игрок (по нему сейчас и живёт весь перевод)
	 * @param keys ключи верхнего уровня custom_data — чтобы видеть, что вообще есть
	 */
	public static void recordItemId(String id, String name, java.util.Set<String> keys) {
		if (!RuConfig.get().dumpUntranslated || !Hypixel.isActive()) {
			return;
		}
		if (keys != null) {
			for (String key : keys) {
				NBT_KEYS.merge(key, 1, Integer::sum);
			}
		}
		if (id == null || id.isBlank() || ITEM_IDS.size() >= MAX_ITEM_IDS) {
			return;
		}
		ITEM_IDS.put(id, name == null ? "" : name);
	}

	/**
	 * Образцы сырого NBT — по одному на вид предмета.
	 *
	 * <p>Список ключей говорит, ЧТО есть, но не говорит, в каком виде.
	 * А там лежат зачарования, самоцветы и перековка — то, что мы сейчас
	 * добываем разбором готового текста. Если они приходят структурой, строку
	 * можно СОБИРАТЬ из данных, а не разбирать обратно, и целый класс наших
	 * догадок исчезает.
	 *
	 * <p>Держим немного и по одному на id: нужна СТРУКТУРА, а не архив чужих
	 * предметов. Тысяча одинаковых дрелей ничего не добавит.
	 */
	private static final Map<String, String> NBT_SAMPLES = new ConcurrentHashMap<>();

	private static final int MAX_NBT_SAMPLES = 400;

	public static void recordNbtSample(String id, String raw) {
		if (!RuConfig.get().dumpUntranslated || !Hypixel.isActive()
				|| id == null || id.isBlank() || raw == null
				|| NBT_SAMPLES.size() >= MAX_NBT_SAMPLES) {
			return;
		}
		// ⚠️ Обрезаем: у предмета с полным набором самоцветов NBT огромен,
		// а структура видна и по началу. Файл дампа не должен пухнуть.
		NBT_SAMPLES.putIfAbsent(id, raw.length() > 2000 ? raw.substring(0, 2000) : raw);
	}

	/**
	 * Потолок сбора подсказок.
	 *
	 * <p>⚠️ Был 5000 — и упёрся: в живом дампе оказалось ровно 5000 блоков,
	 * то есть сбор давно остановлен, а новые подсказки не попадали в файл
	 * ВООБЩЕ. Узнать об этом было неоткуда: отказ молчаливый, счётчик просто
	 * перестаёт расти. Ровно та беда, ради которой в проекте заведён
	 * check_dump_persistence — только там про потерю при перезапуске,
	 * а здесь про тихий стоп.
	 *
	 * <p>Файл накопительный и переживает перезапуск, поэтому предел поднят
	 * по образцу {@code MAX_PARAGRAPH_COLORS}: копить есть смысл долго.
	 */
	private static final int MAX_TOOLTIPS = 30_000;

	/** Сказали ли уже, что сбор подсказок остановлен: жалуемся ОДИН раз. */
	private static volatile boolean tooltipsFull;

	/**
	 * Запоминает подсказку целиком. Одинаковые блоки (после замены чисел)
	 * схлопываются, поэтому десять миньонов разных ступеней дадут один блок.
	 */
	public static void recordTooltip(String item, java.util.List<String> rawLines) {
		if (!RuConfig.get().dumpUntranslated || rawLines == null || rawLines.size() < 2) {
			return;
		}
		// ⚠️ Те же ворота, что у остального сбора. Их тут не было, и подсказки
		// собирались ВЕЗДЕ — включая лобби Hypixel, где меню и так на русском
		// (Hypixel сам переводит лобби по языку игрока). В корпус попадали
		// «Нажмите, чтобы играть» и «Безумно весёлые мини-игры», а за перевод
		// уже переведённого мы бы ещё и заплатили.
		if (!Hypixel.isActive()) {
			return;
		}
		if (TOOLTIPS.size() >= MAX_TOOLTIPS) {
			// ⚠️ Отказ должен быть ГРОМКИМ. Молчаливый стоп выглядит как
			// «новых подсказок больше не встречается», и на этом можно
			// потерять целое событие: игрок ходит по новой локации, а в дамп
			// не попадает ничего.
			if (!tooltipsFull) {
				tooltipsFull = true;
				SkyblockRuClient.LOG.warn(
						"[SkyblockRU] tooltip collection stopped: reached {} blocks. "
						+ "Raise MAX_TOOLTIPS or archive dump/tooltips.json", MAX_TOOLTIPS);
				noteProblem("tooltips", String.valueOf(MAX_TOOLTIPS));
			}
			return;
		}

		String[] lines = new String[rawLines.size()];
		int meaningful = 0;
		for (int i = 0; i < rawLines.size(); i++) {
			String clean = LegacyText.strip(rawLines.get(i)).trim();
			clean = RANKED_NAME.matcher(clean).replaceAll("{s}");
			clean = NUMBERS.matcher(clean).replaceAll("{n}");
			lines[i] = clean;
			if (!clean.isEmpty()) {
				meaningful++;
			}
		}
		if (meaningful < 2) {
			return;
		}

		String key = String.join("\n", lines);
		if (TOOLTIPS.putIfAbsent(key, lines) == null) {
			if (item != null && !item.isBlank()) {
				// ⚠️ ИМЯ ОБОБЩАЕМ ТАК ЖЕ, КАК СТРОКИ. Строки выше прошли через
				// RANKED_NAME и NUMBERS, а имя клалось СЫРЫМ — и стороны
				// переставали сходиться: в подсказке первой строкой лежит
				// «Potato Minion {n}», а в имени «Potato Minion VII».
				// Мод срезает имя сравнением сырого с сырым и справляется,
				// а make_paragraphs.without_name сравнивает обобщённую строку
				// с сырым именем — не срезает, и имя предмета вклеивается
				// в первый абзац корпуса. Это ровно та беда, ради которой
				// в проекте заведён check_contract: ключ у мода и у скриптов
				// обязан строиться одинаково.
				String name = LegacyText.strip(item).trim();
				name = RANKED_NAME.matcher(name).replaceAll("{s}");
				name = NUMBERS.matcher(name).replaceAll("{n}");
				TOOLTIP_ITEM.put(key, name);
			}
			dirty = true;
		}
	}

	/** Раскладки цветов, встреченные в игре: ключ -> строка отчёта. */
	private static final Map<String, String> COLOR_CASES = new ConcurrentHashMap<>();

	private static final int MAX_COLOR_CASES = 400;

	/**
	 * Запоминает, как был раскрашен кусок подсказки и что мы про него решили.
	 *
	 * <p>⚠️ Ради этого файла всё и затевалось. Решение «склеивать ли абзац»
	 * принимается по цветам, а цвета из дампа снимаются — проверить правило
	 * до сборки было НЕЧЕМ, и каждая правка уезжала к игроку вслепую. Дважды
	 * это кончалось поломкой на экране. Теперь раскладки копятся здесь,
	 * а tools/check_colors.py прогоняет по ним ту же логику без игры.
	 */
	public static void recordColors(java.util.List<String> colors,
	                                java.util.List<String> markers, boolean merged,
	                                String reason, String sample) {
		if (!RuConfig.get().dumpUntranslated || COLOR_CASES.size() >= MAX_COLOR_CASES) {
			return;
		}
		String key = String.join(",", colors);
		String marks = String.join(",", markers);
		COLOR_CASES.putIfAbsent(key + "|" + marks,
				key + "	" + marks + "	" + merged + "	" + reason + "	"
						+ sample.substring(0, Math.min(60, sample.length())));
		dirty = true;
	}

	/** Раскраска склеенных абзацев: ключ абзаца -> запись для проверки. */
	private static final Map<String, String> PARAGRAPH_COLORS = new ConcurrentHashMap<>();

	// ⚠️ Это не отладочный лог, а ИСТОЧНИК ДАННЫХ для разметки цветом: у 1005
	// переведённых абзацев цветов нет ни в NEU, ни где-либо ещё, и взять их
	// можно только отсюда. Триста записей закончились бы за один вечер игры.
	//
	// ⚠️ Предел поднят вместе с накоплением между сессиями: пока файл жил одну
	// сессию, двух тысяч хватало с запасом (за вечер набирается несколько сотен).
	// Теперь записи копятся, и прежний предел молча остановил бы сбор на середине
	// пути к 2329 неразмеченным абзацам — а тихий отказ здесь дороже всего:
	// разметка бы просто перестала пополняться, ничего об этом не сказав.
	// ⚠️ 10 000 УПЁРЛИСЬ 29.07 — в файле оказалось РОВНО 10000 записей, то есть
	// сбор цветов стоял неизвестно сколько. Поймал это игрок по счётчику в чате,
	// а не мод: у ЭТОГО потолка, в отличие от MAX_TOOLTIPS, голоса не было.
	// Ровно та грабля, что уже записана («у любого потолка должен быть голос»),
	// просто применили её тогда к одному счётчику из семи.
	//
	// Цена молчания здесь высшая: живые цвета — единственный источник разметки
	// для абзацев меню и экранов, которых нет ни в NEU, ни на аукционе.
	private static final int MAX_PARAGRAPH_COLORS = 60_000;

	/** Сказали ли уже, что сбор цветов остановлен: жалуемся ОДИН раз. */
	private static volatile boolean colorsFull;

	/**
	 * Ключи, поднятые с диска, — их живая запись имеет право ПЕРЕЗАПИСАТЬ.
	 *
	 * <p>Цвета кусков приходят от Hypixel и от версии мода не зависят, а вот
	 * перевод рядом с ними — наш, и он мог с прошлой сессии измениться.
	 * {@link #recordParagraphColors} обычно бережёт первую запись
	 * ({@code putIfAbsent}), иначе восстановленная старая заслоняла бы свежую
	 * и {@code check_paragraph_colors.py} проверял бы раскраску против
	 * вчерашнего перевода.
	 */
	private static final java.util.Set<String> RESTORED_PARAGRAPHS =
			java.util.concurrent.ConcurrentHashMap.newKeySet();

	/**
	 * Разделители внутри записи: кусок от куска и цвет от текста.
	 *
	 * <p>⚠️ Собраны ЧИСЛОМ, а не написаны в исходнике: управляющий символ в коде
	 * невидим, и следующий читатель увидит пустое место и «поправит» его. Тот же
	 * приём, что у иконок в SelfTest.
	 */
	private static final char PIECE_SEP = (char) 0x02;
	private static final char FIELD_SEP = (char) 0x01;

	/**
	 * Запоминает КУСКИ склеенного абзаца с их цветами и готовый перевод.
	 *
	 * <p>⚠️ Отдельно от {@link #recordColors}, и вот почему. Тот файл дедупит
	 * по РАСКЛАДКЕ (набору цветов), и 90 записей покрывают всю игру — для
	 * решения «склеивать ли» этого хватает, потому что решение зависит только
	 * от цветов. А раскраске перевода нужен ТЕКСТ: какие куски уцелели в нём
	 * дословно, знает лишь сам перевод. Поэтому здесь ключом идёт абзац.
	 *
	 * <p>Читает это {@code tools/check_paragraph_colors.py}: он прогоняет
	 * {@link ParagraphColors} на записанном и показывает, сколько подсветки
	 * вернулось, — не заходя в игру.
	 */
	public static void recordParagraphColors(String key, java.util.List<String> colors,
	                                         java.util.List<String> texts, String translated,
	                                         String item) {
		if (!RuConfig.get().dumpUntranslated) {
			return;
		}
		if (PARAGRAPH_COLORS.size() >= MAX_PARAGRAPH_COLORS) {
			// ⚠️ Отказ обязан быть ГРОМКИМ. Молчаливый читается как «новых цветов
			// больше не встречается», и разметка просто перестаёт пополняться —
			// именно так этот счётчик и простоял на 10000.
			if (!colorsFull) {
				colorsFull = true;
				SkyblockRuClient.LOG.warn(
						"[SkyblockRU] paragraph color collection stopped: reached {} entries. "
						+ "Raise MAX_PARAGRAPH_COLORS or archive dump/paragraph-colors.json",
						MAX_PARAGRAPH_COLORS);
				noteProblem("colors", String.valueOf(MAX_PARAGRAPH_COLORS));
			}
			return;
		}
		StringBuilder pieces = new StringBuilder();
		for (int i = 0; i < colors.size() && i < texts.size(); i++) {
			if (pieces.length() > 0) {
				pieces.append(PIECE_SEP);
			}
			pieces.append(colors.get(i)).append(FIELD_SEP).append(texts.get(i));
		}
		String row = pieces + "\t" + translated + "\t" + (item == null ? "" : item);
		if (RESTORED_PARAGRAPHS.remove(key)) {
			PARAGRAPH_COLORS.put(key, row); // увиденное сейчас вытесняет вчерашнее
		} else {
			PARAGRAPH_COLORS.putIfAbsent(key, row);
		}
		dirty = true;
	}

	/**
	 * Поднимает цвета абзацев, собранные в прошлые запуски.
	 *
	 * <p>⚠️ Без этого файл жил ровно ОДНУ игровую сессию: коллекция пуста,
	 * а первая же автозапись подменяла файл на диске. Беда тихая — ошибок нет,
	 * просто счёт каждый раз начинается с нуля. А цикл работы над модом требует
	 * перезапуска игры после каждой сборки, то есть данные стирались как раз тем
	 * действием, ради которого их собирали.
	 *
	 * <p>Ту же граблю в этом файле уже наступали на {@code collected.json} —
	 * см. {@link #load()}. Здесь она обошлась дороже: цвета живой игры это
	 * ЕДИНСТВЕННЫЙ оставшийся источник разметки для 2329 абзацев, потому что
	 * в репозитории NEU лежат одни предметы, а меню и экраны есть только в игре.
	 *
	 * <p>Накопительными делаем ТОЛЬКО эти данные, но не {@code color-cases.json}
	 * и не {@code preview.json}: там записано, что мод РЕШИЛ и как выглядит
	 * экран, — история прошлого jar, которая заставила бы чинить давно
	 * починенное. Цвета же приходят от сервера и от версии мода не зависят.
	 */
	private static void loadParagraphColors() {
		Path file = dumpDir.resolve("paragraph-colors.json");
		if (!Files.exists(file)) {
			return;
		}
		try {
			JsonObject root = new com.google.gson.Gson()
					.fromJson(Files.readString(file, StandardCharsets.UTF_8), JsonObject.class);
			com.google.gson.JsonArray cases = root == null ? null : root.getAsJsonArray("cases");
			if (cases == null) {
				return;
			}
			int broken = 0;
			for (com.google.gson.JsonElement element : cases) {
				if (PARAGRAPH_COLORS.size() >= MAX_PARAGRAPH_COLORS) {
					break;
				}
				// ⚠️ Разбираем ПОКАЗАПИСНО: файл переживает смену версий мода,
				// и одна запись старого образца не должна отменять восстановление
				// всех остальных. Терять здесь дороже, чем пропустить строку.
				try {
					JsonObject one = element.getAsJsonObject();
					if (!one.has("key")) {
						continue; // запись без ключа не с чем связать
					}
					String key = one.get("key").getAsString();
					StringBuilder pieces = new StringBuilder();
					com.google.gson.JsonArray saved = one.getAsJsonArray("pieces");
					if (saved != null) {
						for (com.google.gson.JsonElement pieceElement : saved) {
							com.google.gson.JsonArray pair = pieceElement.getAsJsonArray();
							if (pair.isEmpty()) {
								continue;
							}
							if (pieces.length() > 0) {
								pieces.append(PIECE_SEP);
							}
							pieces.append(pair.get(0).getAsString()).append(FIELD_SEP)
									.append(pair.size() > 1 ? pair.get(1).getAsString() : "");
						}
					}
					String ru = one.has("ru") ? one.get("ru").getAsString() : "";
					// «name» при записи подменяется обрезком ключа, если имени
					// не было; такой обрезок именем предмета не является.
					String name = one.has("name") ? one.get("name").getAsString() : "";
					if (!name.isEmpty() && key.startsWith(name)) {
						name = "";
					}
					PARAGRAPH_COLORS.put(key, pieces + "\t" + ru + "\t" + name);
					RESTORED_PARAGRAPHS.add(key);
				} catch (RuntimeException ignored) {
					broken++;
				}
			}
			SkyblockRuClient.LOG.info("[SkyblockRU] restored paragraph colors: {} paragraphs{}",
					PARAGRAPH_COLORS.size(), broken == 0 ? "" : " (" + broken + " unreadable)");
		} catch (IOException | RuntimeException exception) {
			SkyblockRuClient.LOG.warn("[SkyblockRU] could not read paragraph-colors.json: {}",
					exception.toString());
		}
	}

	/** Подсказки целиком: как выглядели ДО перевода и как стали ПОСЛЕ. */
	private static final Map<String, String> PREVIEW = new ConcurrentHashMap<>();

	private static final int MAX_PREVIEW = 200;

	/** Разделитель строк внутри снимка. */
	private static final char LINE_SEP = (char) 0x03;

	/**
	 * Снимок подсказки: каждая строка разобрана на цветные куски.
	 *
	 * <p>⚠️ Обходим {@code visit}, а не берём {@code getString()}: цвет живёт
	 * в кусках компонента, а не в его корне. На этом уже обожглись — куски
	 * собирались из корня, и целые описания уезжали в чужой цвет.
	 */
	public static String snapshot(java.util.List<Component> lines) {
		StringBuilder out = new StringBuilder();
		for (Component line : lines) {
			if (out.length() > 0) {
				out.append(LINE_SEP);
			}
			StringBuilder row = new StringBuilder();
			line.visit((style, text) -> {
				if (text.isEmpty()) {
					return java.util.Optional.empty();
				}
				LegacyText.parse(text, style).visit((inner, part) -> {
					if (part.isEmpty()) {
						return java.util.Optional.empty();
					}
					if (row.length() > 0) {
						row.append(PIECE_SEP);
					}
					// Пишем ВСЁ, что несёт стиль, а не только цвет: жирный и курсив
					// тоже видны на экране, и без них снимок не равен подсказке.
					StringBuilder color = new StringBuilder(
							inner.getColor() == null ? "" : inner.getColor().serialize());
					if (inner.isBold()) {
						color.append("+b");
					}
					if (inner.isItalic()) {
						color.append("+i");
					}
					if (inner.isUnderlined()) {
						color.append("+u");
					}
					if (inner.isStrikethrough()) {
						color.append("+s");
					}
					row.append(color).append(FIELD_SEP).append(part);
					return java.util.Optional.empty();
				}, style);
				return java.util.Optional.empty();
			}, net.minecraft.network.chat.Style.EMPTY);
			out.append(row);
		}
		return out.toString();
	}

	/**
	 * Запоминает подсказку ДО и ПОСЛЕ перевода — чтобы её можно было посмотреть
	 * вне игры, вместе с цветами.
	 *
	 * <p>⚠️ Ради этого файла стоит вся возня. Пока проверять приходилось
	 * скриншотами, цикл был такой: игрок увидел, прислал картинку, я угадал
	 * причину, собрал, он проверил. Один заход — минуты. А тут игрок открывает
	 * пару меню, и весь его экран лежит на диске вместе с цветами:
	 * {@code python tools/preview.py} рисует подсказку прямо в терминале.
	 */
	public static void recordPreview(String item, String before, String after) {
		if (!RuConfig.get().dumpUntranslated || PREVIEW.size() >= MAX_PREVIEW) {
			return;
		}
		if (before.isEmpty() || before.equals(after)) {
			return; // ничего не изменилось — смотреть нечего
		}
		String name = item == null ? "" : LegacyText.strip(item).trim();
		PREVIEW.putIfAbsent(name + FIELD_SEP + before, before + "\t" + after);
		dirty = true;
	}

	/** Снимок подсказки -> json: массив строк, каждая строка — массив кусков [цвет, текст]. */
	private static com.google.gson.JsonArray previewLines(String snapshot) {
		com.google.gson.JsonArray rows = new com.google.gson.JsonArray();
		if (snapshot.isEmpty()) {
			return rows;
		}
		for (String line : snapshot.split(String.valueOf(LINE_SEP), -1)) {
			com.google.gson.JsonArray pieces = new com.google.gson.JsonArray();
			for (String piece : line.split(String.valueOf(PIECE_SEP), -1)) {
				if (piece.isEmpty()) {
					continue;
				}
				String[] pair = piece.split(String.valueOf(FIELD_SEP), 2);
				com.google.gson.JsonArray one = new com.google.gson.JsonArray();
				one.add(pair[0]);
				one.add(pair.length > 1 ? pair[1] : "");
				pieces.add(one);
			}
			rows.add(pieces);
		}
		return rows;
	}

	/** Строки, где на экране оказалась СМЕСЬ языков: оригинал -> результат. */
	private static final Map<String, String> MIXED = new ConcurrentHashMap<>();

	private static final int MAX_MIXED = 500;

	/**
	 * Замечает смесь языков в СВОЁМ ЖЕ выводе.
	 *
	 * <p>⚠️ Весь день такие строки находил игрок и присылал скриншотами — то есть
	 * ошибки ловились случайно и с задержкой. А признак механический: в исходной
	 * строке кириллицы не было, а в переводе есть и она, и латиница.
	 *
	 * <p>Имена предметов и NPC мы нарочно оставляем английскими, и списка их
	 * в моде нет — он живёт в инструментах. Но различить их можно и без списка:
	 * Hypixel пишет имена с ЗАГЛАВНОЙ буквы, а строчное английское слово среди
	 * русской фразы именем не бывает. По этому признаку и считаем.
	 */
	/** Команда игры: «/warp», «/coopadd &lt;ник&gt;». Её латиница законна. */
	private static final java.util.regex.Pattern COMMAND =
			java.util.regex.Pattern.compile("/[A-Za-z][A-Za-z0-9_]*");

	/**
	 * «Подпись: значение», где значение — латиница без русских слов.
	 * Так выглядят ник продавца, номер сервера и прочие имена: «Продавец: walizy».
	 */
	private static final java.util.regex.Pattern VALUE_AFTER_COLON =
			java.util.regex.Pattern.compile("[^:]{2,}:\\s*[^\\p{IsCyrillic}]{1,40}");

	/** Латинское ли это слово — сосед, по которому судим о недопереводе. */
	private static boolean isLatinWord(String word) {
		if (word.length() < 2) {
			return false;
		}
		char first = word.charAt(0);
		return (first >= 'a' && first <= 'z') || (first >= 'A' && first <= 'Z');
	}

	public static void noteMixed(String source, String result) {
		if (!RuConfig.get().dumpUntranslated || MIXED.size() >= MAX_MIXED) {
			return;
		}
		if (hasCyrillic(source) || !hasCyrillic(result)) {
			return;
		}
		// ⚠️ Считаем только слова со СТРОЧНОЙ буквы.
		//
		// Имена Hypixel пишет с Заглавной, и мы их нарочно не переводим:
		// «Добро пожаловать в Hypixel SkyBlock!» — правильный перевод, а не
		// смесь. Прежний счёт брал любые латинские слова, и жалоба уходила
		// на КАЖДОЕ упоминание имени. Пока находки просто копились в файл,
		// это было терпимо (их отсеивал report.py, у которого есть список
		// защищённых). Но мод теперь пишет в чат, и ложную жалобу читает игрок.
		//
		// Строчное же английское слово посреди русской фразы именем не бывает —
		// это недоперевод: «Пусть blaze и эфемерные создания», «Increases
		// ◇ Защита by +5». Тот же признак работает в check_translation.py,
		// где он дал 5 находок и ни одной ложной.
		// ⚠️ …и только если СОСЕДИ у слова не латинские.
		//
		// «Нужна ступень Heart of the Mountain 7» — правильный перевод: «of»
		// и «the» строчные, но они внутри английского ИМЕНИ, а его мы не трогаем.
		// Значит смотреть надо не на само слово, а на его окружение: английское
		// слово между двумя русскими — недоперевод, а между английскими — часть
		// имени. Цена промаха несимметрична: пропустить смесь не страшно (её
		// поймает check_translation на корпусе), а ложная жалоба в чате
		// раздражает игрока и учит не доверять предупреждениям.
		String plain = LegacyText.strip(result);
		// ⚠️ КОМАНДА и НИК — законная латиница, и жаловаться на них нельзя.
		//
		// «Также доступно через /warp», «Продавец: zezoquinher», «Сервер: mini65W» —
		// всё это правильные переводы, но по буквам неотличимы от недоперевода.
		// На живом дампе такие давали 11 ложных жалоб из 27: чат пестрит
		// предупреждениями, чинить в них нечего, и доверие к ним пропадает.
		// Признаки данные, а не догадка: у команды впереди «/», а ник стоит
		// значением после двоеточия и других русских слов за собой не имеет.
		if (VALUE_AFTER_COLON.matcher(plain).matches()) {
			return;
		}
		String[] words = COMMAND.matcher(plain).replaceAll(" ").split("[^\\p{L}]+");
		int latin = 0;
		for (int i = 0; i < words.length; i++) {
			String word = words[i];
			if (word.length() < 2 || word.charAt(0) < 'a' || word.charAt(0) > 'z') {
				continue;
			}
			if (isLatinWord(i > 0 ? words[i - 1] : "")
					|| isLatinWord(i + 1 < words.length ? words[i + 1] : "")) {
				continue;
			}
			latin++;
		}
		if (latin >= 1) {
			String clean = LegacyText.strip(source);
			boolean fresh = !MIXED.containsKey(clean);
			MIXED.putIfAbsent(clean, LegacyText.strip(result));
			dirty = true;
			// Смесь языков — худший исход: хуже и английской строки, и отсутствия
			// перевода. О ней говорим в первую очередь.
			if (fresh) {
				noteProblem("mixed", LegacyText.strip(result));
			}
		}
	}

	private static boolean hasCyrillic(String text) {
		for (int i = 0; i < text.length(); i++) {
			char symbol = text.charAt(i);
			if (symbol >= 0x400 && symbol <= 0x4FF) {
				return true;
			}
		}
		return false;
	}

	public static int tooltipCount() {
		return TOOLTIPS.size();
	}

	public static void init(Path configDir) {
		dumpDir = configDir.resolve("dump");
		load();
	}

	/**
	 * Поднимает собранное за прошлые запуски.
	 *
	 * <p>Без этого всё жило только в памяти: при выходе из игры счётчик обнулялся,
	 * а первая же запись затирала файл. Накопленное за вечер пропадало
	 * при следующем запуске — так и потеряли первые несколько тысяч строк.
	 */
	/** Подсвеченные имена живут между сессиями так же, как и всё остальное. */
	private static void loadHighlights() {
		Path file = dumpDir.resolve("highlighted.json");
		if (!Files.exists(file)) {
			return;
		}
		try {
			JsonObject root = new com.google.gson.Gson()
					.fromJson(Files.readString(file, StandardCharsets.UTF_8), JsonObject.class);
			JsonObject names = root == null ? null : root.getAsJsonObject("names");
			if (names == null) {
				return;
			}
			java.util.Map<String, Integer> saved = new java.util.LinkedHashMap<>();
			names.entrySet().forEach(entry -> saved.put(entry.getKey(), entry.getValue().getAsInt()));
			Highlights.restore(saved);
		} catch (IOException | RuntimeException exception) {
			SkyblockRuClient.LOG.warn("[SkyblockRU] could not read highlighted.json: {}",
					exception.toString());
		}
	}

	/**
	 * Поднимает подсказки-блоки. ОТДЕЛЬНЫМ методом — и это важно.
	 *
	 * <p>⚠️ Раньше это лежало ВНУТРИ чтения collected.json, за двумя ранними
	 * выходами: нет файла — выход, не разобрался json — выход. То есть подсказки
	 * поднимались лишь как побочный эффект чужого чтения. Стоит collected.json
	 * пропасть или побиться — и 5000 накопленных подсказок не восстановятся,
	 * а первая же запись затрёт их на диске. Запись-то безусловная.
	 *
	 * <p>Та же грабля, что уже записана про цвета абзацев: данные от сервера
	 * обязаны подниматься при старте, иначе автосохранение подменяет файл.
	 */
	private static void loadTooltips() {
		Path tooltips = dumpDir.resolve("tooltips.json");
		if (!Files.exists(tooltips)) {
			return;
		}
		try {
			JsonObject saved = new com.google.gson.Gson()
					.fromJson(Files.readString(tooltips, StandardCharsets.UTF_8), JsonObject.class);
			com.google.gson.JsonArray blocks = saved != null ? saved.getAsJsonArray("tooltips") : null;
			if (blocks == null) {
				return;
			}
			blocks.forEach(element -> {
				JsonObject block = element.getAsJsonObject();
				com.google.gson.JsonArray array = block.getAsJsonArray("lines");
				String[] lines = new String[array.size()];
				for (int i = 0; i < array.size(); i++) {
					lines[i] = array.get(i).getAsString();
				}
				String key = String.join("\n", lines);
				TOOLTIPS.put(key, lines);
				String item = block.has("item") ? block.get("item").getAsString() : "";
				if (!item.isBlank()) {
					TOOLTIP_ITEM.put(key, item);
				}
			});
		} catch (IOException | RuntimeException exception) {
			SkyblockRuClient.LOG.warn("[SkyblockRU] could not read tooltips.json: {}",
					exception.toString());
		}
	}

	/**
	 * Поднимает собранные идентификаторы.
	 *
	 * <p>⚠️ Отдельным методом и обязательно — по той же грабле, что уже стоила
	 * проекту 62 КБ живых цветов: запись безусловна, и если коллекция при старте
	 * пуста, первое же автосохранение подменит файл. Собранное за прошлый вечер
	 * исчезнет молча — ни ошибки, ни строчки в логе.
	 */
	private static void loadItemIds() {
		Path file = dumpDir.resolve("item-ids.json");
		if (!Files.exists(file)) {
			return;
		}
		try {
			JsonObject root = new com.google.gson.Gson()
					.fromJson(Files.readString(file, StandardCharsets.UTF_8), JsonObject.class);
			if (root == null) {
				return;
			}
			JsonObject ids = root.getAsJsonObject("ids");
			if (ids != null) {
				ids.entrySet().forEach(entry ->
						ITEM_IDS.put(entry.getKey(), entry.getValue().getAsString()));
			}
			JsonObject keys = root.getAsJsonObject("nbt_keys");
			if (keys != null) {
				keys.entrySet().forEach(entry ->
						NBT_KEYS.put(entry.getKey(), entry.getValue().getAsInt()));
			}
			JsonObject samples = root.getAsJsonObject("samples");
			if (samples != null) {
				samples.entrySet().forEach(entry ->
						NBT_SAMPLES.put(entry.getKey(), entry.getValue().getAsString()));
			}
		} catch (IOException | RuntimeException exception) {
			SkyblockRuClient.LOG.warn("[SkyblockRU] could not read item-ids.json: {}",
					exception.toString());
		}
	}

	private static void load() {
		loadHighlights();
		loadParagraphColors();
		loadTooltips();
		loadItemIds();
		Path state = dumpDir.resolve("collected.json");
		if (!Files.exists(state)) {
			return;
		}
		try {
			JsonObject root = new com.google.gson.Gson()
					.fromJson(Files.readString(state, StandardCharsets.UTF_8), JsonObject.class);
			if (root == null) {
				return;
			}
			JsonObject sources = root.getAsJsonObject("sources");
			if (sources != null) {
				sources.entrySet().forEach(sourceEntry -> {
					Map<String, AtomicInteger> bucket =
							BY_SOURCE.computeIfAbsent(sourceEntry.getKey(), key -> new ConcurrentHashMap<>());
					sourceEntry.getValue().getAsJsonObject().entrySet().forEach(line ->
							bucket.put(line.getKey(), new AtomicInteger(line.getValue().getAsInt())));
				});
			}
			JsonObject contexts = root.getAsJsonObject("contexts");
			if (contexts != null) {
				contexts.entrySet().forEach(entry -> CONTEXTS.put(entry.getKey(), entry.getValue().getAsString()));
			}
			JsonObject order = root.getAsJsonObject("order");
			if (order != null) {
				order.entrySet().forEach(entry -> ORDER.put(entry.getKey(), entry.getValue().getAsInt()));
				SEQ.set(ORDER.values().stream().mapToInt(Integer::intValue).max().orElse(0) + 1);
			}
			SkyblockRuClient.LOG.info("[SkyblockRU] restored earlier collection: {} lines, {} tooltips",
					total(), tooltipCount());
		} catch (IOException | RuntimeException exception) {
			SkyblockRuClient.LOG.warn("[SkyblockRU] could not restore the earlier collection: {}", exception.toString());
		}
	}

	/**
	 * Строка панели или таба, в которой переводить нечего: ник, гильдия, дата.
	 *
	 * <p>⚠️ Замер 01.08 по живому дампу: в боковой панели 6188 строк, а годных
	 * для перевода — 160. Остальное «[123] RubyPeach», «{n}/{n}/{n} M{n}B»
	 * и прочие ники: каждый новый игрок плодит новую «уникальную» строку,
	 * файл пухнет, счётчик в чате растёт, а работы за этим нет. Игрок заметил
	 * это сам: «мы или копим одно и то же, или копим лишний мусор».
	 *
	 * <p>Признаки те же, что в `make_queue.worth_translating` — они выверены
	 * на данных и отсеивают ровно 6028 строк из 6188, не трогая полезные
	 * («Purse: {n}», «Bits: {n}»).
	 */
	private static boolean isNoise(String source, String clean) {
		boolean sidebar = TextTranslator.SRC_SCOREBOARD.equals(source);
		if (!sidebar && !TextTranslator.SRC_TAB.equals(source)) {
			return false;
		}
		if (PLAYER_ROW.matcher(clean).find() || SERVER_LINE.matcher(clean).matches()) {
			return true;
		}
		// ⚠️ Одно слово на боковой панели — это НИК. Проверено на сотне строк:
		// настоящего текста среди них нет, а названия мест мы и так не переводим.
		return sidebar && clean.indexOf(' ') < 0;
	}

	/** Строка игрока в панели: «[123] Ник», «Ник [GUILD]», «{s} [TROUPE]». */
	private static final java.util.regex.Pattern PLAYER_ROW =
			java.util.regex.Pattern.compile(
					"^(?:\\[\\{n\\}\\]|\\[\\d+\\])\\s*\\S+"
					+ "|^\\S+\\s+\\[[A-Z]{2,6}\\]$"
					+ "|^\\{s\\}\\s+\\[[^\\]]{1,12}\\]$");

	/** Дата и номер сервера в подвале панели: «{n}/{n}/{n} m{n}AB». */
	private static final java.util.regex.Pattern SERVER_LINE =
			java.util.regex.Pattern.compile(
					"^\\{n\\}/\\{n\\}/\\{n\\}\\s+[a-zA-Z]?\\{n\\}[A-Z]{0,3}$");

	public static void record(String source, String text) {
		record(source, text, null);
	}

	public static void record(String source, String text, String context) {
		if (!RuConfig.get().dumpUntranslated || text == null) {
			return;
		}
		String clean = LegacyText.strip(text).trim();
		if (!isWorthRecording(clean)) {
			return;
		}
		// Чужая переписка: не наше дело, и переводить там нечего.
		// Правило одно на перевод и на сбор — оно живёт в PlayerChat.
		if (TextTranslator.SRC_CHAT.equals(source) && PlayerChat.isPlayerMessage(clean)) {
			return;
		}
		if (TextTranslator.SRC_NAME_TAG.equals(source) && BARE_TOKEN.matcher(clean).matches()) {
			return; // одинокое слово над головой — ник игрока
		}
		// Ники обобщаем ПЕРВЫМИ: иначе цифра внутри ника («RealW0sh») сначала
		// станет {n}, и шаблон имени уже не совпадёт.
		clean = RANKED_NAME.matcher(clean).replaceAll("{s}");
		java.util.regex.Matcher labelled = NAME_LABEL.matcher(clean);
		if (labelled.matches()) {
			clean = labelled.group(1) + ": {s}";
		}
		// Числа обобщаем: «Time left: 2d 5h» и «Time left: 2d 4h» — одна строка,
		// а не две. Иначе список за вечер распухает до тысяч почти одинаковых записей.
		clean = NUMBERS.matcher(clean).replaceAll("{n}");
		// ⚠️ МУСОР НЕ КОПИМ. Проверять надо ПОСЛЕ обобщения: ник становится
		// «{s}», а число «{n}», и до этого шага признак их не узнаёт.
		if (isNoise(source, clean)) {
			return;
		}
		if (context != null && !context.isBlank()) {
			String hint = LegacyText.strip(context).trim();
			if (!hint.isEmpty() && !hint.equals(clean)) {
				CONTEXTS.putIfAbsent(clean, hint);
			}
		}
		ORDER.putIfAbsent(clean, SEQ.getAndIncrement());

		Map<String, AtomicInteger> bucket = BY_SOURCE.computeIfAbsent(source, key -> new ConcurrentHashMap<>());
		AtomicInteger counter = bucket.get(clean);
		if (counter != null) {
			if (RENDERED_EVERY_FRAME.contains(source)) {
				return; // уже записано, счётчик кадрами не накручиваем
			}
			counter.incrementAndGet();
			dirty = true;
			return;
		}
		if (bucket.size() >= MAX_PER_SOURCE) {
			// ⚠️ И этот отказ ГРОМКИЙ, по той же причине. На 29.07 источник
			// item_lore стоял на 16785 из 20000 — то есть до молчаливой
			// остановки сбора оставалось несколько вечеров игры.
			if (fullSources.add(source)) {
				SkyblockRuClient.LOG.warn(
						"[SkyblockRU] string collection stopped for source '{}': reached {}. "
						+ "Raise MAX_PER_SOURCE or archive dump/collected.json",
						source, MAX_PER_SOURCE);
				noteProblem("strings:" + source, String.valueOf(MAX_PER_SOURCE));
			}
			return;
		}
		bucket.computeIfAbsent(clean, key -> new AtomicInteger()).incrementAndGet();
		dirty = true;
		noticeNew();

		long now = System.currentTimeMillis();
		if (now - lastWrite > WRITE_INTERVAL_MS) {
			lastWrite = now;
			flushAsync();
		}
	}

	/**
	 * Строки вида «3. Ник [ТЕГ] - 770,682» — таблицы лидеров у голограмм.
	 * Переводить в них нечего (ники и числа), а место в дампе они занимают:
	 * в первом же тесте их набралось 29 из 69 собранных строк.
	 */
	private static final java.util.regex.Pattern LEADERBOARD =
			java.util.regex.Pattern.compile("^\\d+\\.\\s.*");

	/**
	 * Числа в строке. Заменяются на {n} ПЕРЕД записью, иначе одна и та же фраза
	 * с разными значениями попадает в список сотни раз: таймер над головой
	 * тикает каждую секунду и за один вечер дал 308 записей вместо одной.
	 * Заодно ключ сразу готов к шаблонному переводу — движок понимает {n}.
	 */
	private static final java.util.regex.Pattern NUMBERS =
			java.util.regex.Pattern.compile("\\d+(?:[.,]\\d+)*");

	/**
	 * Реплика живого игрока: «[VIP] Ник: текст». Чужую переписку не собираем.
	 *
	 * <p>⚠️ Проверять этим ТОЛЬКО чат. В описаниях предметов полно строк вида
	 * «Source:», «Requires:», «Seller:» — они подходят под тот же шаблон,
	 * и общий фильтр выбрасывал бы нормальные подписи.
	 */
	private static final java.util.regex.Pattern PLAYER_CHAT =
			java.util.regex.Pattern.compile("^(?:\\[[^\\]]{1,24}\\]\\s*)*[A-Za-z0-9_]{3,16}:\\s.*");

	/**
	 * Реплика NPC: «[NPC] Biblio: ...». Внешне неотличима от игроцкой,
	 * но это текст сервера, и переводить его как раз надо.
	 */
	private static final java.util.regex.Pattern NPC_LINE =
			java.util.regex.Pattern.compile("^\\[NPC\\]\\s.*");

	/** Одиночное слово без пробелов — в табличках над головой это почти всегда ник. */
	private static final java.util.regex.Pattern BARE_TOKEN =
			java.util.regex.Pattern.compile("^[A-Za-z0-9_]{3,16}$");

	/**
	 * Ник игрока с рангом: «[MVP+] Nickname». Заменяется на {s} ПЕРЕД записью.
	 *
	 * <p>Иначе на аукционе каждая строка «Seller: ...» уходит в список отдельно —
	 * за один заход набежало 482 записи вместо одной. Плюс не храним чужие ники:
	 * для перевода они бесполезны, а при сборе с других игроков были бы лишними.
	 */
	private static final java.util.regex.Pattern RANKED_NAME =
			// (?!NPC\]) — метка [NPC] это не ранг игрока, а признак реплики NPC.
			// Без этой оговорки «[NPC] Clerk Seraphine:» превращалось в «{s} Seraphine:»:
			// имя собеседника терялось, и перевести диалог было уже не по чему.
			java.util.regex.Pattern.compile("\\[(?!NPC\\])[A-Za-z+]{2,10}\\]\\s*[A-Za-z0-9_]{3,16}");

	/** Подписи, после которых всегда стоит ник — даже без ранга. */
	private static final java.util.regex.Pattern NAME_LABEL =
			java.util.regex.Pattern.compile("^(Seller|Buyer|Owner|Bidder|Highest Bidder|Bid by):\\s+\\S.*$");

	/**
	 * Отсеиваем то, что переводить бессмысленно: числа, ники, разделители.
	 * Иначе дамп забьётся мусором и в нём не найти настоящие строки.
	 */
	private static boolean isWorthRecording(String text) {
		if (text.length() < 2 || text.length() > 300) {
			return false;
		}
		if (LEADERBOARD.matcher(text).matches()) {
			return false;
		}
		boolean hasLetter = false;
		boolean hasCyrillic = false;
		for (int i = 0; i < text.length(); i++) {
			char c = text.charAt(i);
			if (Character.isLetter(c)) {
				hasLetter = true;
				if (Character.UnicodeBlock.of(c) == Character.UnicodeBlock.CYRILLIC) {
					hasCyrillic = true;
				}
			}
		}
		// уже по-русски — значит, перевод сработал
		return hasLetter && !hasCyrillic;
	}

	public static int total() {
		return BY_SOURCE.values().stream().mapToInt(Map::size).sum();
	}

	public static Map<String, Integer> countsBySource() {
		Map<String, Integer> out = new java.util.TreeMap<>();
		BY_SOURCE.forEach((source, bucket) -> out.put(source, bucket.size()));
		return out;
	}

	/**
	 * Снимок собранного: источник -> строки. Для отправки на сервер перевода.
	 *
	 * <p>⚠️ Отдаём КОПИЮ, а не живую карту: сбор идёт из игрового потока
	 * на каждом кадре, а отправка — из фонового. Обход живой карты во время
	 * записи — это либо мусор в данных, либо исключение посреди подсказки.
	 *
	 * <p>⚠️ Мусор (ники, номера серверов, даты панели) сюда не попадает
	 * по построению: его отсекает {@link #isNoise} ещё при сборе. Второй
	 * копии признака заводить не нужно — в этом проекте копии расходились.
	 */
	public static Map<String, java.util.List<String>> forTelemetry() {
		Map<String, java.util.List<String>> out = new java.util.TreeMap<>();
		BY_SOURCE.forEach((source, bucket) ->
				out.put(source, new java.util.ArrayList<>(bucket.keySet())));
		return out;
	}

	/** Промахи перевода, замеченные модом: вид -> сколько накопилось. */
	private static final Map<String, java.util.concurrent.atomic.AtomicInteger> PROBLEMS =
			new ConcurrentHashMap<>();

	/** Пример строки на каждый вид — чтобы в чате было видно, о чём речь. */
	private static final Map<String, String> PROBLEM_SAMPLE = new ConcurrentHashMap<>();

	private static volatile long lastProblemNotice;

	/** Реже, чем про новые строки: промахи важнее, но и раздражают сильнее. */
	private static final long PROBLEM_INTERVAL_MS = 15_000;

	/**
	 * Сообщает в чат о ПРОМАХЕ перевода, который мод заметил сам.
	 *
	 * <p>⚠️ Зачем. Мод знает про свои неудачи: смесь языков, погашенный
	 * защитой перевод, потерянный цвет. Всё это ложилось в счётчики, которые
	 * открывают раз в неделю, — а игрок тем временем видел испорченную
	 * подсказку и слал скриншот. За один вечер так прошло семь разбирательств.
	 *
	 * <p>Теперь мод говорит сразу и с примером: видно, ЧТО именно не удалось,
	 * и это уже записано в дамп — чинится следующим прогоном. Сообщения копятся
	 * и выдаются пачкой раз в {@link #PROBLEM_INTERVAL_MS}, иначе открытие
	 * большого меню зальёт чат.
	 *
	 * @param kind ключ вида промаха: mixed | guard | color
	 * @param sample строка-пример, по которой понятно, о чём речь
	 */
	public static void noteProblem(String kind, String sample) {
		if (!RuConfig.get().notifyProblems) {
			return;
		}
		PROBLEMS.computeIfAbsent(kind,
				key -> new java.util.concurrent.atomic.AtomicInteger()).incrementAndGet();
		PROBLEM_SAMPLE.putIfAbsent(kind, sample == null ? "" : sample);

		long now = System.currentTimeMillis();
		if (now - lastProblemNotice < PROBLEM_INTERVAL_MS) {
			return;
		}
		lastProblemNotice = now;

		Minecraft client = Minecraft.getInstance();
		if (client == null) {
			return;
		}
		Map<String, Integer> shot = new java.util.LinkedHashMap<>();
		PROBLEMS.forEach((key, value) -> {
			int taken = value.getAndSet(0);
			if (taken > 0) {
				shot.put(key, taken);
			}
		});
		if (shot.isEmpty()) {
			return;
		}
		client.execute(() -> {
			if (client.player == null) {
				return;
			}
			for (Map.Entry<String, Integer> entry : shot.entrySet()) {
				String sampleText = PROBLEM_SAMPLE.getOrDefault(entry.getKey(), "");
				if (sampleText.length() > 44) {
					sampleText = sampleText.substring(0, 44) + "…";
				}
				Chat.tell(client.player, Component.literal("[SkyblockRU] ")
						.append(Component.translatable(
								"skyblockru.problem." + entry.getKey(),
								entry.getValue(), sampleText))
						.withStyle(ChatFormatting.GOLD));
			}
			PROBLEM_SAMPLE.clear();
		});
	}

	/**
	 * Сообщает в чат, что попались новые строки.
	 *
	 * <p>Иначе непонятно, работает сбор или нет: новые строки появляются молча,
	 * а увидеть их можно только в файле. Сообщения копятся и выдаются пачкой
	 * раз в NOTICE_INTERVAL_MS — иначе при открытии большого меню чат зальёт.
	 */
	private static void noticeNew() {
		if (!RuConfig.get().notifyNewStrings) {
			return;
		}
		int count = pendingNotice.incrementAndGet();
		long now = System.currentTimeMillis();
		if (now - lastNotice < NOTICE_INTERVAL_MS) {
			return;
		}
		lastNotice = now;
		pendingNotice.set(0);

		Minecraft client = Minecraft.getInstance();
		if (client == null) {
			return;
		}
		client.execute(() -> {
			if (client.player != null) {
				Chat.tell(client.player, Component.literal("[SkyblockRU] ")
						.append(Component.translatable("skyblockru.collect.new", count, total()))
						.withStyle(ChatFormatting.DARK_GRAY));
			}
		});
	}

	private static void flushAsync() {
		Thread.ofVirtual().name("skyblockru-dump").start(UnknownStrings::flush);
	}

	/** Пишет дамп на диск. Вызывается по таймеру и вручную командой. */
	public static synchronized void flush() {
		if (!dirty || dumpDir == null) {
			return;
		}
		dirty = false;
		try {
			Files.createDirectories(dumpDir);

			JsonObject root = new JsonObject();
			root.addProperty("id", "dump");
			root.addProperty("priority", 10);
			root.addProperty("_comment", "Lines the mod found no translation for. "
					+ "Fill in the values, put the file in config/skyblockru/packs/<language>/, "
					+ "then run /skyblockru reload");

			JsonObject exact = new JsonObject();
			JsonObject contexts = new JsonObject();
			StringBuilder report = new StringBuilder();

			for (Map.Entry<String, Map<String, AtomicInteger>> sourceEntry : sortedSources()) {
				String source = sourceEntry.getKey();
				report.append("### ").append(source).append('\n');
				List<Map.Entry<String, AtomicInteger>> lines = new ArrayList<>(sourceEntry.getValue().entrySet());

				// Описания предметов раскладываем по предметам и в порядке появления:
				// соседние строки одной подсказки должны остаться рядом, иначе
				// разрезанную фразу потом не собрать. Остальное — по частоте.
				if ("item_lore".equals(source)) {
					lines.sort(Comparator
							.comparing((Map.Entry<String, AtomicInteger> e) -> CONTEXTS.getOrDefault(e.getKey(), ""))
							.thenComparingInt(e -> ORDER.getOrDefault(e.getKey(), 0)));
				} else {
					lines.sort(Comparator.comparingInt((Map.Entry<String, AtomicInteger> e) -> e.getValue().get())
							.reversed());
				}

				for (Map.Entry<String, AtomicInteger> line : lines) {
					exact.addProperty(line.getKey(), "");
					String hint = CONTEXTS.get(line.getKey());
					if (hint != null) {
						contexts.addProperty(line.getKey(), hint);
					}
					report.append(line.getValue().get()).append('\t');
					if (hint != null) {
						report.append('[').append(hint).append("] ");
					}
					report.append(line.getKey()).append('\n');
				}
				report.append('\n');
			}

			root.add("_contexts", contexts);
			root.add("exact", exact);

			// Состояние сбора — чтобы следующий запуск продолжил, а не начал с нуля
			JsonObject state = new JsonObject();
			JsonObject sources = new JsonObject();
			BY_SOURCE.forEach((source, bucket) -> {
				JsonObject lines = new JsonObject();
				bucket.forEach((line, count) -> lines.addProperty(line, count.get()));
				sources.add(source, lines);
			});
			state.add("sources", sources);
			JsonObject savedContexts = new JsonObject();
			CONTEXTS.forEach(savedContexts::addProperty);
			state.add("contexts", savedContexts);
			JsonObject savedOrder = new JsonObject();
			ORDER.forEach(savedOrder::addProperty);
			state.add("order", savedOrder);
			writeAtomic(dumpDir.resolve("collected.json"),
					new GsonBuilder().disableHtmlEscaping().create().toJson(state));

			// Имена собственные, которые Hypixel подсветил цветом. Отдельным
			// файлом: это не «непереведённое», а наоборот — список того,
			// что переводить НЕЛЬЗЯ. Его читает tools/protected.py.
			JsonObject highlighted = new JsonObject();
			highlighted.addProperty("_comment", "Proper names Hypixel highlights with its own "
					+ "color: places, NPCs, creature types. NEVER translate these - the color "
					+ "is data from the server, not a guess about the text. Read by "
					+ "tools/protected.py.");
			JsonObject names = new JsonObject();
			Highlights.collected().forEach(names::addProperty);
			highlighted.add("names", names);
			writeAtomic(dumpDir.resolve("highlighted.json"),
					new GsonBuilder().setPrettyPrinting().disableHtmlEscaping().create()
							.toJson(highlighted));

			// Раскладки цветов: набор случаев для tools/check_colors.py
			com.google.gson.JsonArray cases = new com.google.gson.JsonArray();
			COLOR_CASES.values().stream().sorted().forEach(row -> {
				String[] parts = row.split("	", -1);
				JsonObject one = new JsonObject();
				one.addProperty("colors", parts[0]);
				one.addProperty("markers", parts[1]);
				one.addProperty("merged", Boolean.parseBoolean(parts[2]));
				one.addProperty("reason", parts[3]);
				one.addProperty("sample", parts.length > 4 ? parts[4] : "");
				cases.add(one);
			});
			JsonObject colorFile = new JsonObject();
			colorFile.addProperty("_comment", "How each tooltip run was colored and what "
					+ "the mod decided about merging it into a paragraph. Recorded so the "
					+ "rule can be re-checked WITHOUT the game: tools/check_colors.py");
			colorFile.add("cases", cases);
			writeAtomic(dumpDir.resolve("color-cases.json"),
					new GsonBuilder().setPrettyPrinting().disableHtmlEscaping().create()
							.toJson(colorFile));

			// Раскраска абзацев: куски с цветами + готовый перевод. Нужна
			// tools/check_paragraph_colors.py, чтобы проверять раздачу цветов
			// без игры — по образцу color-cases.json, но с ТЕКСТОМ кусков:
			// какие из них уцелели в переводе дословно, видно только по нему.
			com.google.gson.JsonArray paragraphs = new com.google.gson.JsonArray();
			PARAGRAPH_COLORS.forEach((key, row) -> {
				String[] parts = row.split("\t", -1);
				com.google.gson.JsonArray pieces = new com.google.gson.JsonArray();
				for (String piece : parts[0].split(String.valueOf(PIECE_SEP), -1)) {
					if (piece.isEmpty()) {
						continue;
					}
					String[] pair = piece.split(String.valueOf(FIELD_SEP), 2);
					com.google.gson.JsonArray one = new com.google.gson.JsonArray();
					one.add(pair[0]);
					one.add(pair.length > 1 ? pair[1] : "");
					pieces.add(one);
				}
				JsonObject item = new JsonObject();
				item.addProperty("name", parts.length > 2 && !parts[2].isEmpty()
						? parts[2] : key.substring(0, Math.min(48, key.length())));
				// ⚠️ КЛЮЧ абзаца пишем целиком, а не только как запасное имя.
				// Без него цвета живой подсказки не связать с корпусом иначе
				// как угадыванием по началу текста, а это второй источник цветов
				// для разметки: в репозитории NEU лежат только ПРЕДМЕТЫ, поэтому
				// меню, экраны и чужие профили красить больше неоткуда.
				item.addProperty("key", key);
				item.add("pieces", pieces);
				item.addProperty("ru", parts.length > 1 ? parts[1] : "");
				paragraphs.add(item);
			});
			JsonObject paragraphFile = new JsonObject();
			paragraphFile.addProperty("_comment", "Colored pieces of every glued paragraph "
					+ "plus its translation. Lets tools/check_paragraph_colors.py replay the "
					+ "coloring WITHOUT the game and show how much highlighting survives.");
			paragraphFile.add("cases", paragraphs);
			writeAtomic(dumpDir.resolve("paragraph-colors.json"),
					new GsonBuilder().setPrettyPrinting().disableHtmlEscaping().create()
							.toJson(paragraphFile));

			// Подсказки целиком, до и после перевода: их рисует tools/preview.py
			com.google.gson.JsonArray previews = new com.google.gson.JsonArray();
			PREVIEW.forEach((key, row) -> {
				String[] parts = row.split("\t", -1);
				JsonObject one = new JsonObject();
				one.addProperty("item", key.substring(0, Math.max(0, key.indexOf(FIELD_SEP))));
				one.add("before", previewLines(parts[0]));
				one.add("after", previewLines(parts.length > 1 ? parts[1] : ""));
				previews.add(one);
			});
			JsonObject previewFile = new JsonObject();
			previewFile.addProperty("_comment", "Whole tooltips before and after translation, "
					+ "with colors. Lets tools/preview.py draw what the player actually sees - "
					+ "without asking for a screenshot.");
			previewFile.add("cases", previews);
			writeAtomic(dumpDir.resolve("preview.json"),
					new GsonBuilder().setPrettyPrinting().disableHtmlEscaping().create()
							.toJson(previewFile));

			// Смесь языков в собственном выводе — рабочий список для tools/report.py
			JsonObject mixed = new JsonObject();
			mixed.addProperty("_comment", "Lines where the mod produced a mix of Russian and "
					+ "English. Some are legitimate (item and NPC names stay English) - "
					+ "tools/report.py filters those out. The rest are bugs.");
			JsonObject mixedPairs = new JsonObject();
			MIXED.forEach(mixedPairs::addProperty);
			mixed.add("lines", mixedPairs);
			writeAtomic(dumpDir.resolve("mixed.json"),
					new GsonBuilder().setPrettyPrinting().disableHtmlEscaping().create()
							.toJson(mixed));

			writeAtomic(dumpDir.resolve("untranslated.json"),
					new GsonBuilder().setPrettyPrinting().disableHtmlEscaping().create().toJson(root));
			writeAtomic(dumpDir.resolve("untranslated.txt"), report.toString());


			// Подсказки целиком — в том же виде, что выгрузка из NEU,
			// чтобы обрабатывать их одним и тем же инструментом.
			com.google.gson.JsonArray blocks = new com.google.gson.JsonArray();
			TOOLTIPS.forEach((key, lines) -> {
				JsonObject block = new JsonObject();
				block.addProperty("item", TOOLTIP_ITEM.getOrDefault(key, ""));
				com.google.gson.JsonArray array = new com.google.gson.JsonArray();
				for (String line : lines) {
					array.add(line);
				}
				block.add("lines", array);
				block.add("ru", new com.google.gson.JsonArray());
				blocks.add(block);
			});
			JsonObject tooltipFile = new JsonObject();
			tooltipFile.addProperty("id", "tooltips_from_game");
			tooltipFile.addProperty("_comment", "Whole item tooltips collected in game. "
					+ "Translate them as blocks.");
			tooltipFile.add("tooltips", blocks);
			writeAtomic(dumpDir.resolve("tooltips.json"),
					new GsonBuilder().setPrettyPrinting().disableHtmlEscaping().create().toJson(tooltipFile));

			// Идентификаторы предметов из NBT — разведка: есть ли у нас ключ
			// надёжнее текста. Подробности в комментарии к ITEM_IDS.
			JsonObject idFile = new JsonObject();
			idFile.addProperty("id", "item_ids_from_game");
			idFile.addProperty("_comment", "SkyBlock item ids read from NBT (custom_data). "
					+ "Data from the server, not a report about the mod: keep accumulating. "
					+ "Read by tools/check_item_ids.py");
			JsonObject ids = new JsonObject();
			ITEM_IDS.forEach(ids::addProperty);
			idFile.add("ids", ids);
			JsonObject keys = new JsonObject();
			NBT_KEYS.forEach(keys::addProperty);
			idFile.add("nbt_keys", keys);
			JsonObject samples = new JsonObject();
			NBT_SAMPLES.forEach(samples::addProperty);
			idFile.add("samples", samples);
			writeAtomic(dumpDir.resolve("item-ids.json"),
					new GsonBuilder().setPrettyPrinting().disableHtmlEscaping().create().toJson(idFile));
		} catch (IOException exception) {
			SkyblockRuClient.LOG.warn("[SkyblockRU] could not write the dump: {}", exception.toString());
		}
	}

	/**
	 * Пишет файл атомарно: сперва во временный, потом подменяет.
	 *
	 * <p>Стало обязательным, когда дамп начали сбрасывать при выходе из игры.
	 * Прямая запись в целевой файл рвётся вместе с процессом, и на диске
	 * остаётся половина JSON — а следующий запуск на нём не поднимет НИЧЕГО,
	 * то есть одна неудачная секунда стоила бы всего накопленного.
	 */
	private static void writeAtomic(Path target, String content) throws IOException {
		Path temp = target.resolveSibling(target.getFileName() + ".tmp");
		Files.writeString(temp, content, StandardCharsets.UTF_8);
		try {
			Files.move(temp, target, java.nio.file.StandardCopyOption.REPLACE_EXISTING,
					java.nio.file.StandardCopyOption.ATOMIC_MOVE);
		} catch (java.nio.file.AtomicMoveNotSupportedException unsupported) {
			// файловая система не умеет — обычная подмена всё равно лучше записи поверх
			Files.move(temp, target, java.nio.file.StandardCopyOption.REPLACE_EXISTING);
		}
	}

	private static List<Map.Entry<String, Map<String, AtomicInteger>>> sortedSources() {
		List<Map.Entry<String, Map<String, AtomicInteger>>> list = new ArrayList<>(BY_SOURCE.entrySet());
		list.sort(Map.Entry.comparingByKey());
		return list;
	}

	// ⚠️ Метода clear() здесь больше НЕТ, и добавлять его обратно не надо.
	// Он обнулял собранное за все сессии разом — без подтверждения и без отмены,
	// а вызывала его команда, стоявшая в списке рядом с /skyblockru dump.
	// Сбор — это часы игры; кнопки «стереть всё» у него быть не должно.
	// Начать заново = удалить файлы в config/skyblockru/dump/ руками.
}
