package ru.skyblockru.core;

import net.minecraft.network.chat.ClickEvent;
import net.minecraft.network.chat.Component;
import net.minecraft.network.chat.ComponentContents;
import net.minecraft.network.chat.MutableComponent;
import net.minecraft.network.chat.Style;
import net.minecraft.network.chat.TextColor;
import net.minecraft.network.chat.contents.PlainTextContents;
import ru.skyblockru.config.RuConfig;

import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;

/**
 * Переводит готовый Component, сохраняя оформление.
 *
 * <p>Две попытки, в таком порядке:
 * <ol>
 *   <li><b>Строка целиком.</b> Hypixel режет предложение на куски разного цвета,
 *       поэтому сначала склеиваем весь текст и ищем перевод для него. Цвета берём
 *       из перевода (в нём можно писать §-коды) либо наследуем от первого куска,
 *       а клик/наведение с оригинала переносим — иначе кликабельные строки чата
 *       перестали бы работать.</li>
 *   <li><b>По кускам.</b> Если целиком не нашлось, идём по дереву и переводим
 *       каждый кусок отдельно. Тут оформление и события сохраняются полностью.</li>
 * </ol>
 *
 * <p>⚠️ У перевода целой строки есть цена: если оригинал был раскрашен в несколько
 * цветов, а в переводе §-кодов нет, вся строка станет одноцветной. Такие случаи
 * пересчитывает {@link Diagnostics#colorLoss}, и видно их в /skyblockru diag.
 */
public final class TextTranslator {

	public static final String SRC_CHAT = "chat";
	public static final String SRC_ITEM_NAME = "item_name";
	public static final String SRC_ITEM_LORE = "item_lore";
	public static final String SRC_SCOREBOARD = "scoreboard";
	public static final String SRC_TAB = "tab";
	public static final String SRC_ACTION_BAR = "action_bar";
	public static final String SRC_TITLE = "title";
	public static final String SRC_SCREEN = "screen";
	public static final String SRC_BOSS_BAR = "boss_bar";
	public static final String SRC_NAME_TAG = "name_tag";

	/**
	 * Строки, для которых перевода точно нет.
	 *
	 * <p>Названия предметов и строки сайдбара запрашиваются каждый кадр. Без этого
	 * списка мод на каждом кадре заново обходил бы дерево текста впустую. Список
	 * сбрасывается при перезагрузке словарей — иначе новый перевод не подхватится.
	 */
	private static final Set<String> MISSES = Collections.newSetFromMap(new ConcurrentHashMap<>());

	private static final int MISS_CACHE_LIMIT = 50_000;

	private TextTranslator() {
	}

	public static void clearCache() {
		MISSES.clear();
	}

	public static Component translate(Component source, String origin) {
		return translate(source, origin, null);
	}

	/**
	 * @param context откуда строка — например, имя предмета, чью подсказку читают.
	 *                Уходит в дамп рядом со строкой: переводчику без этого
	 *                непонятно, к чему относится обрывок фразы.
	 */
	public static Component translate(Component source, String origin, String context) {
		try {
			return translateOrThrow(source, origin, context);
		} catch (RuntimeException exception) {
			// Отрисовка игры не должна падать из-за кривого правила в словаре.
			Diagnostics.error("translation (" + origin + ")", exception);
			return source;
		}
	}

	private static Component translateOrThrow(Component source, String origin, String context) {
		if (source == null || !RuConfig.get().enabled || !Hypixel.isActive()) {
			return source;
		}

		String plain = source.getString();
		if (plain.isBlank()) {
			return source;
		}

		// ⚠️ ЧУЖОЙ МОД НЕ ТРОГАЕМ — ни переводить, ни собирать.
		//
		// Наши точки перехвата ванильные, поэтому через них проходит и текст
		// соседей: SkyHanni дописывает «(From SkyHanni)» в подсказку предмета,
		// Odin показывает свой заголовок на пол-экрана. Совпади такая строка
		// со словарём — мы перевели бы её случайно.
		//
		// Почему это плохо, даже когда перевод верный: сосед обновляется
		// еженедельно и меняет строки, так что перевод отвалится МОЛЧА; сами
		// соседи ЧИТАЮТ свой текст обратно (SkyHanni разбирает чат и панель),
		// и подмена ломает не надпись, а их работу.
		//
		// Проверка стоит ЗДЕСЬ, в общих воротах: ниже расходятся построчный
		// путь, абзацы и сбор — завести признак в каждом значило бы однажды
		// забыть один. Замер 08.08: по всем дампам признак задевает 2 строки,
		// обе настоящие сообщения соседей, а в наших словарях — ни одной.
		if (ForeignMods.looksForeign(plain)) {
			return source;
		}

		// Имена, подсвеченные самим Hypixel, запоминаем ДО перевода и до того,
		// как строка потеряет разметку: дальше по дороге §-коды снимаются,
		// и признак «сервер выделил это цветом» пропадает навсегда.
		//
		// ⚠️ ТОЛЬКО ЧАТ. Сперва собирали отовсюду — и нахватали игровых терминов:
		// в описании предмета цветом помечено ВСЁ значимое («Cost», «Grants»,
		// «Protection VI», «Wither», «Sharpness VII»), и признак «выделено
		// цветом» там значит «важное», а не «имя собственное». А в реплике NPC
		// тело белое и одноцветное, поэтому выделенное в нём — действительно
		// место, персонаж или существо. Из 215 собранных отовсюду именами были
		// единицы.
		if (RuConfig.get().dumpUntranslated && SRC_CHAT.equals(origin)) {
			Highlights.note(source);
		}

		// ⚠️ ЦВЕТА ПАНЕЛИ И ТАБА — тоже ДО перевода и до снятия кодов.
		//
		// Для абзацев лора сбор есть с 26.07, а панель и таб остались без него:
		// чтобы разметить их перевод, цвет от Hypixel взять было НЕГДЕ. Дамп
		// снимает §-коды при записи, в логи Minecraft таблица игроков не
		// попадает (это не чат), в NEU и на аукционе её нет вовсе. Цвета
		// приходилось восстанавливать по скриншотам — по одной строке за раз.
		//
		// ⚠️ Врезка ОДНА на обе области, а не по миксину на каждую: панель
		// переводится в четырёх точках (заголовок, счёт, префикс команды, таб),
		// и шестую однажды забыли бы — это записанное правило проекта про
		// ворота, через которые надо провести ВСЕ пути.
		if (RuConfig.get().dumpUntranslated
				&& (SRC_SCOREBOARD.equals(origin) || SRC_TAB.equals(origin))) {
			UnknownStrings.recordPanelColors(origin, source);
		}

		// Слова живого игрока не трогаем вовсе: ни переводим, ни записываем.
		// Проверка стоит ДО поиска по словарю — иначе широкое правило могло бы
		// поймать чужую реплику и подменить её.
		// §-коды убираем ДО поиска — ровно так же делают перевод по кускам
		// (translateLiteral) и сборщик незнакомых строк.
		//
		// ⚠️ Раньше тут искали по «грязной» строке, и это тихо ломало целый класс
		// случаев: Hypixel вставляет коды ВНУТРЬ строки («Late Spring §a19th»),
		// а в словарь мы пишем чистый текст — тот самый, что показывает дамп.
		// Совпасть они не могли никогда. Симптом обманчив: строка в дампе
		// выглядит чистой, запись в словаре выглядит верной, а перевода нет.
		String core = LegacyText.strip(plain).strip();

		if (SRC_CHAT.equals(origin) && PlayerChat.isPlayerMessage(core)) {
			return source;
		}

		if (MISSES.contains(core)) {
			// в дамп всё равно пишем: так видно, что попадается чаще всего
			UnknownStrings.record(origin, plain, context);
			return source;
		}

		// ⚠️ НАБОР ВАРИАНТОВ ОТВЕТА: у каждого свой clickEvent, и перевод ЦЕЛИКОМ
		// их терял. `rebuild` собирает строку заново из плоского текста, а событие
		// потом вешается ОДНО на всю строку (`firstEventStyle`) — то есть событие
		// ПЕРВОГО варианта. На экране незаметно, а нажатие на «[Не-а.]» выполняло
		// команду «[Конечно.]»: игрок дважды отказался от разговора, и оба раза
		// NPC продолжал рассказывать. Перевод ломал не текст, а игру.
		//
		// Покусочный путь сохраняет стиль каждого куска вместе с его событием
		// (`walk` копирует `node.getStyle()`), поэтому при нескольких РАЗНЫХ
		// событиях идём только им. Не перевелось ничего — отдаём оригинал:
		// английская кнопка, которая работает, лучше русской, которая врёт.
		if (distinctClickEvents(source) > 1) {
			int[] stats = {0, 0};
			Component perSegment = walk(source, stats, origin, context);
			if (stats[0] > 0) {
				Diagnostics.hit(origin, Diagnostics.KIND_SEGMENT);
				return perSegment;
			}
			UnknownStrings.record(origin, plain, context);
			return source;
		}

		// context — имя предмета: если для него задан отдельный перевод, он победит общий
		Translator.Match whole = Translator.lookup(core, origin, context);

		// У РАЗНОЦВЕТНОЙ строки сперва пробуем перевести по кускам, и берём этот
		// перевод, только если перевелись ВСЕ куски.
		//
		// Зачем: перевод целиком собирает строку заново и красит её сам —
		// цвета приходится копировать из оригинала, а копия может разойтись
		// с ним. По кускам каждый кусок остаётся собой: «Purse:» переводится,
		// а золотая сумма и имя NPC не трогаются вовсе — их цвет РОДНОЙ,
		// а не восстановленный.
		//
		// Условие «перевелись все» обязательно: иначе половина кусков осталась бы
		// английской и строка вышла бы смесью языков — хуже, чем перевод целиком.
		if (countColors(source) > 1) {
			int[] stats = {0, 0};
			Component perSegment = walk(source, stats, origin, context);
			if (stats[1] > 0 && stats[0] == stats[1]) {
				Diagnostics.hit(origin, Diagnostics.KIND_SEGMENT);
				return perSegment;
			}
		}

		if (whole != null) {
			Diagnostics.hit(origin, whole.kind());
			return rebuild(source, plain, whole.text());
		}

		// ⚠️ Запасной проход по кускам: тут переводится НЕ ВСЁ, и результат
		// берём, только если он перестал быть английским.
		//
		// Раньше условием было «перевёлся хоть один кусок» — и это оказалось
		// фабрикой смеси языков на всём разноцветном тексте:
		//   «Talk to §aRoddy§7 in the §aBackwater Bayou§7 to apply parts…»
		//   -> «Поговори с Roddy in the Backwater Bayou to apply parts…»
		// Кусок «Talk to» лежит точной записью (он же объектив на панели),
		// остальные — нет, и на экран уезжала одна русская фраза посреди
		// английской. Игрок видит это как «половина не переведена», хотя
		// половина как раз переведена — и лучше бы не была.
		int[] stats = {0, 0};
		Component perSegment = walk(source, stats, origin, context);
		if (stats[0] > 0 && !Translator.stillEnglish(perSegment.getString())) {
			Diagnostics.hit(origin, Diagnostics.KIND_SEGMENT);
			return perSegment;
		}

		// Полоса над хотбаром собрана КОЛОНКАМИ через несколько пробелов, и
		// середина всё время разная: защита, опыт навыка, локация, DPS, задание.
		// Правило на каждое сочетание писать бесполезно — их десятки, и Hypixel
		// добавляет новые. Переводим каждую колонку отдельно: тогда любое
		// сочетание собирается само.
		String byColumns = translateColumns(plain, origin);
		if (byColumns != null) {
			Diagnostics.hit(origin, Diagnostics.KIND_COLUMNS);
			return rebuild(source, plain, byColumns);
		}

		String partial = Translator.applyGlossary(core, origin);
		if (partial != null) {
			Diagnostics.hit(origin, Diagnostics.KIND_GLOSSARY);
			return rebuild(source, plain, partial);
		}

		if (MISSES.size() < MISS_CACHE_LIMIT) {
			MISSES.add(core);
		}
		UnknownStrings.record(origin, plain, context);
		return source;
	}

	/** Собирает новый Component из перевода целой строки. */
	private static Component rebuild(Component source, String plain, String translated) {
		// пробелы по краям оригинала сохраняем: на них держится вёрстка сайдбара и тултипов
		String left = plain.substring(0, plain.length() - plain.stripLeading().length());
		String right = plain.substring(plain.stripTrailing().length());

		// Цвета у Hypixel живут §-кодами ВНУТРИ текста, а не стилями компонента
		// (видно в dump/styles.txt: кусок «Монет: §6142,427» имеет цвет=white).
		// Коды мы убираем перед поиском по словарю — иначе не совпадёт ни одна
		// запись, — но выдать перевод без них значит выбросить всю раскраску.
		// Поэтому переносим их обратно.
		String coloured = translated;
		if (LegacyText.hasCodes(plain) && !LegacyText.hasCodes(translated)) {
			coloured = carryLegacyCodes(plain, translated);
		}
		// ⚠️ Шапку реплики NPC заменяем на оригинальную: у каждого NPC свой цвет
		// имени, а в словаре он взят с вики, где указан лишь у 59% реплик —
		// у остальных имя красилось жёлтым от метки «[NPC]». Метод сам решает,
		// применимо ли: у не-реплики он вернёт перевод нетронутым.
		coloured = ParagraphColors.swapNpcPrefix(plain, coloured);

		Style base = dropOddModifiers(source, bodyStyle(source, firstStyle(source)));
		MutableComponent byColon = paintByColon(source, left + coloured + right, base);
		MutableComponent result = byColon != null
				? byColon : restyleFromSource(left + coloured + right, source, base);

		// Считаем ПОСЛЕ переноса стилей: жалуемся только на цвета, которые
		// действительно потерялись. Раньше проверка стояла до и ругалась на всё
		// подряд — из-за этого настоящие потери («Кошелёк» с белой суммой вместо
		// золотой) тонули в шуме и дошли до игры.
		if (countColors(result) < countColors(source)) {
			Diagnostics.colorLoss(plain.strip());
		}

		// ⚠️ Проверяем СВОЙ ЖЕ вывод на смесь языков. Такие строки весь день
		// находил игрок и присылал скриншотами; признак механический, и мод
		// вполне может заметить их сам.
		UnknownStrings.noteMixed(plain, result.getString());

		Style events = firstEventStyle(source);
		if (events != null) {
			Style style = result.getStyle();
			if (events.getClickEvent() != null) {
				style = style.withClickEvent(events.getClickEvent());
			}
			if (events.getHoverEvent() != null) {
				style = style.withHoverEvent(events.getHoverEvent());
			}
			result.setStyle(style);
		}
		return result;
	}

	/** Колонки Hypixel разделяет несколькими пробелами подряд. */
	private static final java.util.regex.Pattern COLUMN_GAP = java.util.regex.Pattern.compile("\\s{2,}");

	/** Ведущие §-коды колонки: их надо сохранить, они и красят колонку. */
	private static final java.util.regex.Pattern LEADING_CODES =
			java.util.regex.Pattern.compile("^((?:§.)*)([\\s\\S]*)$");

	/**
	 * Переводит строку по колонкам. Возвращает null, если ни одна не поддалась.
	 *
	 * <p>Разбираем СЫРУЮ строку, вместе с §-кодами: у каждой колонки свой код
	 * впереди, он её и красит. Оторвём — потеряем цвет, как уже было с
	 * «Кошельком».
	 */
	private static String translateColumns(String plain, String origin) {
		java.util.regex.Matcher gaps = COLUMN_GAP.matcher(plain);
		if (!gaps.find()) {
			return null;
		}
		gaps.reset();

		StringBuilder out = new StringBuilder(plain.length() + 16);
		boolean changed = false;
		int last = 0;
		while (gaps.find()) {
			changed |= appendColumn(out, plain.substring(last, gaps.start()), origin);
			out.append(gaps.group());
			last = gaps.end();
		}
		changed |= appendColumn(out, plain.substring(last), origin);
		return changed ? out.toString() : null;
	}

	/** Переводит одну колонку. true — перевод нашёлся. */
	private static boolean appendColumn(StringBuilder out, String column, String origin) {
		String codes = "";
		String body = column;
		java.util.regex.Matcher split = LEADING_CODES.matcher(column);
		if (split.matches()) {
			codes = split.group(1);
			body = split.group(2);
		}
		String core = LegacyText.strip(body).strip();
		if (core.isEmpty()) {
			out.append(column);
			return false;
		}
		Translator.Match found = Translator.lookup(core, origin, null);
		if (found == null) {
			out.append(column);
			return false;
		}
		out.append(codes).append(found.text());
		return true;
	}

	/** Кусок оригинала вида «код + текст»: «§dSusan» -> код «§d», текст «Susan». */
	private static final java.util.regex.Pattern LEGACY_RUN =
			java.util.regex.Pattern.compile("((?:§.)+)([^§]*)");

	/**
	 * Возвращает в перевод §-коды оригинала.
	 *
	 * <p>Ведущий код ставим в начало — он задаёт цвет всей строки. Дальше ищем
	 * куски, перенесённые в перевод дословно (число, имя NPC, значок), и ставим
	 * перед ними их родной код.
	 *
	 * <p>⚠️ И код, которым идёт текст ПОСЛЕ куска, — тоже. Без него цвет
	 * выделенного имени тёк до конца строки: «§3Lotus Sea Creatures §fand»
	 * в оригинале возвращает белый после имени, а мы этот возврат теряли,
	 * и в переводе бирюзовым становилось «и целой уймы». Снаружи выглядит
	 * так, будто NPC говорит цветом названия.
	 *
	 * <p>Пример: «§eTalk to §dSusan§e!» + «Поговори с Susan!» =
	 * «§eПоговори с §dSusan§e!».
	 */
	private static String carryLegacyCodes(String original, String translated) {
		java.util.List<String[]> runs = new java.util.ArrayList<>();
		java.util.regex.Matcher matcher = LEGACY_RUN.matcher(original);
		int firstAt = -1;
		while (matcher.find()) {
			if (firstAt < 0) {
				firstAt = matcher.start();
			}
			runs.add(new String[]{matcher.group(1), matcher.group(2)});
		}

		String result = translated;
		String leading = "";
		for (int i = 0; i < runs.size(); i++) {
			String code = runs.get(i)[0];
			String piece = runs.get(i)[1].strip();
			if (i == 0 && firstAt == 0) {
				leading = code;
				// ⚠️ Ведущий код красит ВСЮ строку, если не вернуть цвет тела
				// сразу за префиксом. У реплики NPC это видно ярче всего:
				//   §c[NPC] Mayor Diana§f: I am in perfect communion with nature.
				// Первый кусок уходит в начало перевода, а §f теряется — его
				// кусок «: I am…» переведён, искать в переводе нечего. В итоге
				// вся реплика красилась цветом МЭРА, и игрок прислал скриншот,
				// где так окрасились сразу четверо.
				//
				// Правка узкая: возвращаем цвет, только если сам префикс уцелел
				// в переводе ДОСЛОВНО. Имена NPC мы не переводим, поэтому у реплик
				// он уцелевает всегда, а у прозы («§7Grants…» → «Даёт…») —
				// никогда, и там ничего не меняется.
				String after = i + 1 < runs.size() ? runs.get(i + 1)[0] : "";
				if (!after.isEmpty() && !piece.isEmpty()) {
					int at = result.indexOf(piece);
					if (at >= 0) {
						int end = at + piece.length();
						result = result.substring(0, end) + after + result.substring(end);
					}
				}
				continue;
			}
			// Однобуквенный кусок берём, только если это НЕ буква и не цифра:
			// значок ☀ перенести надо, а одинокая «s» случайно попала бы
			// в середину русского слова и раскрасила бы его кусками.
			boolean plainWord = piece.length() < MIN_RUN_LENGTH
					&& (piece.isEmpty() || Character.isLetterOrDigit(piece.charAt(0)));
			if (plainWord) {
				continue;
			}
			int at = result.indexOf(piece);
			if (at < 0 || (at >= 2 && result.charAt(at - 2) == '§')) {
				continue;
			}
			// Чем красится текст ПОСЛЕ куска. У последнего куска возвращать
			// нечего — дальше строки нет.
			String after = i + 1 < runs.size() ? runs.get(i + 1)[0] : "";
			result = result.substring(0, at) + code + piece + after
					+ result.substring(at + piece.length());
		}
		return leading + result;
	}

	/** Кусок оригинала со своим цветом: его текст и стиль. */
	private record ColoredRun(String text, Style style) {
	}

	/**
	 * Добавляет к кускам их ПЕРЕВОДЫ — чтобы цвет доставался и русскому слову.
	 *
	 * <p>Список остаётся отсортированным от длинных к коротким: иначе короткий
	 * кусок откусит начало длинного и раскрасит строку клочьями.
	 */
	private static List<ColoredRun> withTranslations(List<ColoredRun> runs) {
		List<ColoredRun> out = new ArrayList<>(runs);
		Set<String> seen = new HashSet<>();
		for (ColoredRun run : runs) {
			String core = run.text().strip();
			// Короткие не спрашиваем: «V» или «10» в словаре не термин,
			// а совпасть в русской фразе могут где угодно.
			if (core.length() < 3 || !seen.add(core)) {
				continue;
			}
			Translator.Match found = Translator.lookup(core, SRC_ITEM_LORE, null);
			if (found == null) {
				continue;
			}
			String russian = found.text().strip();
			if (russian.isEmpty() || russian.equals(core) || seen.contains(russian)) {
				continue;
			}
			seen.add(russian);
			out.add(new ColoredRun(russian, run.style()));
		}
		out.sort(Comparator.comparingInt((ColoredRun run) -> run.text().length()).reversed());
		return out;
	}

	/**
	 * Минимальная длина куска, чей цвет переносим. Совсем короткие («а», «и»)
	 * случайно совпали бы с обрывком русского слова и покрасили бы не то.
	 */
	private static final int MIN_RUN_LENGTH = 2;

	/**
	 * Собирает переведённую строку, сохраняя цвета оригинала.
	 *
	 * <p>Зачем: Hypixel красит части строки по-разному — «Purse: » белым, а сумму
	 * золотым. Раньше весь перевод получал ОДИН стиль (первого куска), и золото
	 * пропадало: строка выходила блёклой и непохожей на оригинал.
	 *
	 * <p>Идея простая: то, что в переводе осталось дословно (число, ник, имя NPC),
	 * — это перенесённый кусок оригинала, и его цвет мы знаем. Такие куски красим
	 * как в оригинале, остальное — базовым стилем. Никаких §-кодов вручную
	 * прописывать не нужно, и работает это для всех строк сразу.
	 */
	private static MutableComponent restyleFromSource(String text, Component source, Style base) {
		List<ColoredRun> runs = coloredRuns(source, base);
		if (runs.isEmpty()) {
			return LegacyText.parse(text, base);
		}
		// ⚠️ Цвет возвращаем не только тому, что уцелело ДОСЛОВНО, но и
		// переведённому — если перевод куска знает наш же словарь.
		//
		// «§b Crit Chance» превращается в «Шанса крита», и дословного поиска
		// хватить не может: искомого текста в строке больше нет. А словарь
		// пару знает, значит место в русской фразе известно точно. Тот же приём
		// уже работает для абзацев (Paragraphs.aliases) — здесь его не было,
		// и каждый переведённый термин молча терял подсветку.
		//
		// ⚠️ Спрашиваем ТОЛЬКО точный словарь: правило может позвать само себя,
		// а глоссарий вернёт полуфразу.
		runs = withTranslations(runs);

		MutableComponent out = Component.empty().setStyle(base);
		StringBuilder pending = new StringBuilder();
		int index = 0;
		while (index < text.length()) {
			ColoredRun hit = null;
			for (ColoredRun run : runs) {
				if (text.startsWith(run.text(), index)) {
					hit = run;
					break;
				}
			}
			if (hit == null) {
				pending.append(text.charAt(index));
				index++;
				continue;
			}
			if (!pending.isEmpty()) {
				out.append(LegacyText.parse(pending.toString(), base));
				pending.setLength(0);
			}
			out.append(Component.literal(hit.text()).setStyle(hit.style()));
			index += hit.text().length();
		}
		if (!pending.isEmpty()) {
			out.append(LegacyText.parse(pending.toString(), base));
		}
		return out;
	}

	/**
	 * Раскраска строки вида «ПОДПИСЬ: значение» — по её же двоеточию.
	 *
	 * <p>⚠️ Живые случаи со скриншотов, и все три об одном:
	 * <pre>
	 *   §eNote:§7 Permanent fuel…      -> «Примечание:» стало серым, а было жёлтым
	 *   §7Buy it now: §63,298,000,000 coins -> «монет» посерело, число осталось золотым
	 *   §7Ends in: §65d                -> «д» посерело
	 * </pre>
	 * Обычный перенос цвета ищет кусок оригинала ДОСЛОВНО, а переведённое слово
	 * так не найти — цвет и пропадал. Но у этих строк есть своя структура:
	 * подпись до двоеточия и значение после, каждая своего цвета. Двоеточие
	 * переживает перевод, поэтому по нему и красим.
	 *
	 * <p>Ничего не выдумываем: цвета берутся из оригинала, а если частей не две
	 * или цвет у них общий — возвращаем null, и работает обычный путь.
	 *
	 * @return раскрашенная строка либо null, если приём тут не годится
	 */
	private static MutableComponent paintByColon(Component source, String translated, Style base) {
		String plain = source.getString();
		int colon = plain.indexOf(':');
		int mine = translated.indexOf(':');
		if (colon <= 0 || mine <= 0 || mine + 1 >= translated.length()) {
			return null;
		}
		// ⚠️ Цвет значения берём с первого НЕПРОБЕЛЬНОГО знака после двоеточия.
		// Пробел принадлежит куску подписи, и по нему цвета вышли бы одинаковыми
		// у «§7Buy it now: §63,298,000,000 coins» — приём молча не сработал бы.
		int valueAt = colon + 1;
		while (valueAt < plain.length() && Character.isWhitespace(plain.charAt(valueAt))) {
			valueAt++;
		}
		if (valueAt >= plain.length()) {
			return null;
		}
		Style label = styleAt(source, firstLetter(plain));
		Style value = styleAt(source, valueAt);
		if (label == null || value == null || java.util.Objects.equals(
				label.getColor(), value.getColor())) {
			return null;    // одноцветная строка — красить нечего
		}
		// то же деление в переводе: двоеточие и пробел после него остаются с подписью
		int split = mine + 1;
		while (split < translated.length() && Character.isWhitespace(translated.charAt(split))) {
			split++;
		}
		// ⚠️ Значение бывает РАЗНОЦВЕТНЫМ, и заливать его одним цветом нельзя:
		// «§7Mining Speed: §e+2,590 §e[+500] §9[+50] §d(+240)» — жёлтое базовое,
		// синяя ковка, фиолетовые самоцветы. Схлопывание в жёлтое видно на экране
		// сразу, а строится такая строка у КАЖДОГО прокачанного предмета
		// (в корпусе NEU 880 строк «подпись: разноцветное значение»).
		// Поэтому подпись красим сами, а значение отдаём обычному переносу цветов:
		// числа и скобки переживают перевод дословно, значит их цвет точно известен.
		MutableComponent out = Component.empty().setStyle(base);
		out.append(Component.literal(translated.substring(0, split)).setStyle(label));
		out.append(restyleFromSource(translated.substring(split), source, value));
		return out;
	}

	/** Позиция первого непробельного знака: с него начинается подпись. */
	private static int firstLetter(String text) {
		int at = 0;
		while (at < text.length() && Character.isWhitespace(text.charAt(at))) {
			at++;
		}
		return at;
	}

	/** Стиль куска, накрывающего эту позицию строки. */
	private static Style styleAt(Component source, int index) {
		Style[] found = {null};
		int[] seen = {0};
		source.visit((style, text) -> {
			if (found[0] == null && seen[0] + text.length() > index && !text.isBlank()) {
				found[0] = style;
				return Optional.of(Boolean.TRUE);
			}
			seen[0] += text.length();
			return Optional.empty();
		}, Style.EMPTY);
		return found[0];
	}

	/**
	 * Куски оригинала, чей цвет отличается от базового — от длинных к коротким.
	 *
	 * <p>Порядок важен: сначала пробуем длинные, иначе короткий кусок откусит
	 * начало длинного и раскрасит строку кусками.
	 */
	private static List<ColoredRun> coloredRuns(Component source, Style base) {
		List<ColoredRun> runs = new ArrayList<>();
		Set<String> seen = new HashSet<>();
		source.visit((style, text) -> {
			String core = text.strip();
			// Однобуквенный кусок берём, только если это НЕ буква и не цифра —
			// то же исключение, что и в carryLegacyCodes. Без него значок «❣»
			// (один знак) в куски не попадал, и строка «§4❣ §cRequires §dHeart of
			// the Mountain» теряла красный целиком: фиолетовым красилось всё,
			// потому что фиолетового БОЛЬШЕ по знакам. Цвет приходит двумя путями,
			// и правило для §-кодов надо было завести и для стилей компонента.
			boolean plainWord = core.length() < MIN_RUN_LENGTH
					&& (core.isEmpty() || Character.isLetterOrDigit(core.charAt(0)));
			if (plainWord || style.getColor() == null) {
				return Optional.empty();
			}
			if (style.getColor().equals(base.getColor())) {
				return Optional.empty();
			}
			if (seen.add(core)) {
				runs.add(new ColoredRun(core, style));
			}
			return Optional.empty();
		}, Style.EMPTY);
		runs.sort(Comparator.comparingInt((ColoredRun run) -> run.text().length()).reversed());
		return runs;
	}

	/** Сколько разных цветов в строке. Больше одного — перевод без §-кодов их потеряет. */
	private static int countColors(Component source) {
		Set<TextColor> colors = new HashSet<>();
		source.visit((style, text) -> {
			if (!text.isBlank() && style.getColor() != null) {
				colors.add(style.getColor());
			}
			return Optional.empty();
		}, Style.EMPTY);
		return colors.size();
	}

	/**
	 * Рекурсивно переводит каждый текстовый кусок дерева.
	 *
	 * @param stats счётчик: [0] — сколько кусков переведено, [1] — сколько кусков
	 *              вообще можно было перевести. Нужен, чтобы отличить «перевелось
	 *              всё» от «перевелась половина»: у разноцветных строк первый
	 *              случай лучше перевода целиком (цвета остаются РОДНЫМИ,
	 *              а не скопированными), второй — хуже (выйдет смесь языков).
	 */
	private static Component walk(Component node, int[] stats, String origin, String item) {
		ComponentContents contents = node.getContents();
		if (!(contents instanceof PlainTextContents plain)) {
			// не обычный текст (например, переводимый ключ ванилы) — не трогаем
			return node;
		}

		String text = plain.text();
		String translated = translateLiteral(text, origin, item);
		MutableComponent copy = Component.literal(translated != null ? translated : text);
		if (!LegacyText.strip(text).strip().isEmpty()) {
			stats[1]++;
		}
		if (translated != null) {
			stats[0]++;
		}
		copy.setStyle(node.getStyle());

		List<Component> siblings = node.getSiblings();
		for (Component sibling : siblings) {
			copy.append(walk(sibling, stats, origin, item));
		}
		return copy;
	}

	/**
	 * Перевод одного куска. Возвращает null, если перевода нет.
	 * Коды §, приклеенные к началу куска, сохраняются как есть.
	 */
	private static String translateLiteral(String text, String origin, String item) {
		if (text.isBlank()) {
			return null;
		}

		String clean = LegacyText.strip(text);
		String core = clean.strip();
		if (core.length() < 2) {
			return null;
		}

		Translator.Match match = Translator.lookup(core, origin, item);
		if (match == null) {
			return null;
		}

		// возвращаем на место §-префикс и пробелы по краям
		String prefix = text.substring(0, text.length() - text.stripLeading().length());
		int codeEnd = leadingCodesLength(text);
		String codes = text.substring(0, codeEnd);
		String left = clean.substring(0, clean.length() - clean.stripLeading().length());
		String right = clean.substring(clean.stripTrailing().length());
		return codes.isEmpty() ? prefix + match.text() + right : codes + left + match.text() + right;
	}

	/** Сколько символов в начале строки занято кодами §X. */
	private static int leadingCodesLength(String text) {
		int i = 0;
		while (i + 1 < text.length() && text.charAt(i) == '§') {
			i += 2;
		}
		return i;
	}

	/** Стиль первого непустого куска — им красим перевод, если в нём нет своих §-кодов. */
	private static Style firstStyle(Component source) {
		Style[] found = {Style.EMPTY};
		source.visit((style, text) -> {
			if (!text.isBlank()) {
				found[0] = style;
				return Optional.of(Boolean.TRUE);
			}
			return Optional.empty();
		}, Style.EMPTY);
		return found[0];
	}

	/**
	 * Снимает с базового стиля ЗАЧЁРКИВАНИЕ и ОБФУСКАЦИЮ, если ими помечена
	 * лишь малая часть строки.
	 *
	 * <p>⚠️ Живой случай со скриншота. Плашку про безопасность Hypixel рисует
	 * так: сверху и снизу строка дефисов, ЗАЧЁРКНУТАЯ стилем (так рисуется
	 * линия), между ними обычный текст. §-кодов в ней нет вовсе — стиль лежит
	 * в компоненте. Базовым брался стиль первого куска, то есть зачёркнутый,
	 * и весь перевод выходил перечёркнутым: «НИКОГДА не вводи данные своего
	 * аккаунта Microsoft» читалось как отменённое.
	 *
	 * <p>{@link #bodyStyle} этого не ловил: он взвешивает ЦВЕТ, а зачёркивание
	 * цветом не является. Считаем отдельно — по длине текста, а не по кускам:
	 * линия из дефисов длинная, но она одна, и по кускам победила бы.
	 *
	 * <p>Курсив и жирность НЕ трогаем: ими Hypixel помечает осмысленные вещи
	 * («§oшёпот», жирные заголовки), и снимать их — терять смысл.
	 */
	private static Style dropOddModifiers(Component source, Style base) {
		if (!base.isStrikethrough() && !base.isObfuscated()) {
			return base;
		}
		int[] all = {0};
		int[] struck = {0};
		int[] hidden = {0};
		source.visit((style, text) -> {
			String core = text.strip();
			if (core.isEmpty()) {
				return Optional.empty();
			}
			all[0] += core.length();
			if (style.isStrikethrough()) {
				struck[0] += core.length();
			}
			if (style.isObfuscated()) {
				hidden[0] += core.length();
			}
			return Optional.empty();
		}, Style.EMPTY);
		if (all[0] == 0) {
			return base;
		}
		Style out = base;
		if (base.isStrikethrough() && struck[0] * 2 < all[0]) {
			out = out.withStrikethrough(false);
		}
		if (base.isObfuscated() && hidden[0] * 2 < all[0]) {
			out = out.withObfuscated(false);
		}
		return out;
	}

	/**
	 * Доля строки, до которой первый кусок считается ПОДПИСЬЮ, а не телом.
	 * «Note: » — это шесть знаков из тридцати трёх.
	 */
	private static final double LABEL_SHARE = 0.35;

	/**
	 * Базовый стиль перевода: цвет ТЕЛА строки, а не первого куска.
	 *
	 * <p>⚠️ Живой случай со скриншота. «§eNote:§7 Permanent fuel can be taken» —
	 * жёлтая подпись и серое тело. Базовым брался стиль первого куска, то есть
	 * жёлтый, и весь перевод выходил жёлтым: «Примечание: постоянное топливо
	 * можно забрать» целиком. Подпись при этом теряется всё равно — русское
	 * слово в оригинале не найти, — но заливать её цветом ВСЮ строку незачем.
	 *
	 * <p>Сужено нарочно: подменяем стиль ТОЛЬКО когда первый кусок явно короче
	 * тела и у тела есть свой преобладающий цвет. Одноцветные строки, пары
	 * «подпись / значение» и «§6Ability: X §eRIGHT CLICK», где золотого много,
	 * остаются как были — цветовые решения в этом проекте дважды ломали экран,
	 * и расширять правку без нужды нельзя.
	 */
	private static Style bodyStyle(Component source, Style first) {
		// ⚠️ Вес цвета считаем в КУСКАХ, а не в знаках — то же правило, что
		// в ParagraphColors.body. По знакам длинная подсветка перетягивала тело
		// на себя: у «§4❣ §cRequires §dHeart of the Mountain» фиолетового 21 знак
		// против красных 9, и всё предупреждение красилось фиолетовым — красного
		// на экране не оставалось вовсе. По кускам красных два («Requires» и
		// точка в конце), фиолетовый один: тело красное, как и выглядит оригинал.
		// Смежные куски одного цвета считаем за один — перенос строки режет кусок
		// надвое, и счёт удваивал бы его.
		Map<TextColor, Integer> runs = new HashMap<>();
		Map<TextColor, Integer> chars = new HashMap<>();
		TextColor[] last = {null};
		int[] total = {0};
		int[] head = {0};
		source.visit((style, text) -> {
			String core = text.strip();
			if (core.isEmpty() || style.getColor() == null) {
				return Optional.empty();
			}
			if (total[0] == 0) {
				head[0] = core.length();
			}
			total[0] += core.length();
			chars.merge(style.getColor(), core.length(), Integer::sum);
			if (!style.getColor().equals(last[0])) {
				runs.merge(style.getColor(), 1, Integer::sum);
			}
			last[0] = style.getColor();
			return Optional.empty();
		}, Style.EMPTY);
		if (total[0] == 0 || head[0] > total[0] * LABEL_SHARE) {
			return first;
		}
		TextColor dominant = dominant(runs, chars);
		if (dominant == null || dominant.equals(first.getColor())) {
			return first;
		}
		Style[] found = {first};
		source.visit((style, text) -> {
			if (!text.isBlank() && dominant.equals(style.getColor())) {
				found[0] = style;
				return Optional.of(Boolean.TRUE);
			}
			return Optional.empty();
		}, Style.EMPTY);
		return found[0];
	}

	/** Цвета, которыми Hypixel набирает ОПИСАНИЕ. При ничьей побеждают они. */
	private static final Set<String> BODY_FIRST = Set.of("gray", "dark_gray");

	/**
	 * Цвет с наибольшим числом кусков. Ничья — в пользу цвета описания.
	 *
	 * <p>⚠️ Без явного правила ничью решал бы порядок обхода HashMap, и одна
	 * и та же строка красилась бы то серым, то жёлтым. У «§eNote:§7 Permanent
	 * fuel can be taken» кусков ровно по одному на цвет — ровно тот случай.
	 */
	private static TextColor dominant(Map<TextColor, Integer> runs) {
		return dominant(runs, Map.of());
	}

	/**
	 * Преобладающий цвет: больше всего КУСКОВ, ничья — в пользу серого,
	 * а если серого нет — в пользу того, кем набрано больше ЗНАКОВ.
	 *
	 * <p>⚠️ Без разбора по знакам ничья решалась порядком обхода HashMap, то есть
	 * СЛУЧАЙНО. Видно это на репликах NPC, где кусков ровно два: «§c[NPC] Mayor
	 * Diana§f: I am in perfect communion with nature.» — шапка в цвет мэра
	 * и белое тело. Выиграй шапка, и весь перевод красится красным; игрок прислал
	 * скриншот, где так окрасились реплики сразу четырёх мэров. Ни один из цветов
	 * не серый, поэтому прежний тайбрейк молчал.
	 *
	 * <p>Знаки тут именно ТАЙБРЕЙК, а не основная мера: считать ими сразу нельзя —
	 * длинная подсветка перетягивает тело на себя (записано у {@link #bodyStyle}).
	 */
	private static TextColor dominant(Map<TextColor, Integer> runs,
			Map<TextColor, Integer> chars) {
		TextColor best = null;
		int most = -1;
		for (Map.Entry<TextColor, Integer> entry : runs.entrySet()) {
			int score = entry.getValue();
			boolean better = score > most;
			if (!better && score == most && best != null) {
				boolean bodyish = BODY_FIRST.contains(entry.getKey().serialize());
				boolean bestBodyish = BODY_FIRST.contains(best.serialize());
				better = bodyish && !bestBodyish
						|| bodyish == bestBodyish
							&& chars.getOrDefault(entry.getKey(), 0)
								> chars.getOrDefault(best, 0);
			}
			if (better) {
				best = entry.getKey();
				most = score;
			}
		}
		return best;
	}

	/**
	 * Сколько РАЗНЫХ обработчиков клика в строке.
	 *
	 * <p>Один — обычная кликабельная строка чата, её можно пересобирать целиком.
	 * Два и больше — это набор вариантов ответа, где каждая кнопка ведёт к своей
	 * команде, и схлопывать их в один нельзя (см. вызов в {@link #translate}).
	 */
	private static int distinctClickEvents(Component source) {
		Set<ClickEvent> seen = new HashSet<>();
		source.visit((style, text) -> {
			if (style.getClickEvent() != null) {
				seen.add(style.getClickEvent());
			}
			return Optional.empty();
		}, Style.EMPTY);
		return seen.size();
	}

	/** Первый стиль с кликом или подсказкой — их нельзя терять при пересборке. */
	private static Style firstEventStyle(Component source) {
		Style[] found = {null};
		source.visit((style, text) -> {
			if (style.getClickEvent() != null || style.getHoverEvent() != null) {
				found[0] = style;
				return Optional.of(Boolean.TRUE);
			}
			return Optional.empty();
		}, Style.EMPTY);
		return found[0];
	}
}
