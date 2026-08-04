package ru.skyblockru.core;

import com.google.gson.Gson;
import com.google.gson.JsonObject;
import ru.skyblockru.SkyblockRuClient;
import ru.skyblockru.config.RuConfig;

import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import java.util.stream.Stream;

/**
 * Словарь: держит все пакеты перевода и отвечает на вопрос
 * «как по-русски будет вот эта строка».
 *
 * <p>Порядок поиска:
 * <ol>
 *   <li>точное совпадение;</li>
 *   <li>шаблон с числами: «+5 Strength» ищется как «+{n} Strength»,
 *       числа потом подставляются обратно — один перевод закрывает все значения;</li>
 *   <li>регулярные выражения;</li>
 *   <li>глоссарий — замена знакомых терминов внутри незнакомой строки
 *       (переводит хотя бы частично).</li>
 * </ol>
 */
public final class Translator {

	/** Что именно сработало — нужно диагностике, чтобы было видно, чем живёт перевод. */
	public record Match(String text, String kind) {
	}

	private static final Gson GSON = new Gson();

	/** Числа, включая дробные и с разделителями: 1, 12.5, 1,250 */
	private static final Pattern NUMBER = Pattern.compile("\\d+(?:[.,]\\d+)*");
	private static final Pattern PLACEHOLDER = Pattern.compile("\\{n}");

	/** Признак файла, сохранённого с двойным экранированием: в ключе лежит текст \\uXXXX. */
	private static final Pattern ESCAPED_LITERAL = Pattern.compile("\\\\u[0-9a-fA-F]{4}");

	/** Встроенные пакеты внутри jar — их список лежит в packs/index.json */
	private static final String BUILTIN_DIR = "/assets/skyblockru/packs/";

	/**
	 * Перевод вместе с областью применения.
	 *
	 * @param only где правило разрешено (item_lore, chat...); null — везде.
	 *             Нужно, чтобы ванильные названия работали в описаниях,
	 *             но не трогали заголовки предметов: по русскому названию
	 *             вещь не найти на аукционе.
	 */
	private record Entry(String value, Set<String> only) {
		boolean allows(String origin) {
			return only == null || (origin != null && only.contains(origin));
		}
	}

	/** Кто и как уже перевёл этот ключ — для жалобы на расхождение словарей. */
	private record Seen(String packId, String value) {
	}

	private record ScopedRule(Pattern pattern, String replacement, Set<String> only,
	                         boolean translateGroups, String anchor) {
		boolean allows(String origin) {
			return only == null || (origin != null && only.contains(origin));
		}

		/**
		 * Дешёвый отказ ДО запуска регулярки.
		 *
		 * <p>Правило вида {@code ^Requires (.+)} не может совпасть со строкой,
		 * которая с «Requires » не начинается, — значит и Matcher создавать
		 * незачем. Проверка идёт по построению, поведение не меняется.
		 */
		boolean maybe(String source) {
			return anchor == null || source.startsWith(anchor);
		}
	}

	/**
	 * Литеральное начало шаблона, если оно есть, иначе {@code null}.
	 *
	 * <p>⚠️ Замер 03.08 на 2368 живых правилах и 8000 строк из дампа: якорь
	 * есть у 60% правил, и отсев по нему ускоряет поиск РОВНО ВДВОЕ —
	 * 105 -> 53 мкс на строку. Дороже всего обход меню, где мод читает восемь
	 * предметов разом: 16.8 -> 8.5 мс, то есть из «пропущенный кадр» в «половина».
	 *
	 * <p>Разбор нарочно трусливый: набрав любой символ, имеющий в регулярках
	 * особый смысл, останавливаемся. Лучше пропустить правило в отсев
	 * (оно просто проверится как раньше), чем отбросить строку, которая
	 * на самом деле подходит.
	 */
	private static String anchorOf(String pattern) {
		if (!pattern.startsWith("^")) {
			return null;
		}
		StringBuilder literal = new StringBuilder();
		for (int i = 1; i < pattern.length(); i++) {
			char symbol = pattern.charAt(i);
			if ("\\[](){}.*+?|$^".indexOf(symbol) >= 0) {
				break;
			}
			literal.append(symbol);
		}
		// Короткий якорь почти ничего не отсекает, а проверку стоит.
		return literal.length() >= 3 ? literal.toString() : null;
	}

	private static final List<TranslationPack> PACKS = new ArrayList<>();
	private static final Map<String, Entry> EXACT = new HashMap<>();
	private static final Map<String, Entry> TEMPLATES = new HashMap<>();
	private static final Map<String, Entry> GLOSSARY = new HashMap<>();

	/**
	 * Абзацы: вся фраза целиком -> перевод целиком.
	 *
	 * <p>Отдельно от {@link #EXACT}, потому что ищутся они по другому поводу
	 * (склеенный абзац, а не одна строка) и не должны мешать построчному
	 * переводу, если абзац не подошёл.
	 */
	private static final Map<String, Entry> PARAGRAPHS = new HashMap<>();
	private static final List<ScopedRule> REGEX = new ArrayList<>();

	/**
	 * Переводы, привязанные к предмету: имя предмета -> (строка -> перевод).
	 * Проверяются ПЕРЕД общим словарём и побеждают его.
	 */
	private static final Map<String, Map<String, String>> BY_ITEM = new HashMap<>();

	/** Глоссарий, отсортированный от длинных терминов к коротким. */
	private static List<Map.Entry<String, Entry>> glossarySorted = List.of();

	private static int loadedPacks;

	/** Нашлась ли папка словарей под язык клиента. Показывается в /skyblockru. */
	private static volatile boolean languagePacks;

	/**
	 * Язык, ПОД КОТОРЫЙ собран текущий набор словарей.
	 *
	 * <p>Нужен, чтобы заметить смену языка в настройках игры. Словари мод читает
	 * вручную, а не через менеджер ресурсов, поэтому сами они не перечитываются:
	 * игрок менял язык на русский уже в игре и получал полностью английский
	 * экран, хотя мод был жив и команды отвечали. Причина в логе была названа
	 * прямо («NO DICTIONARIES for language 'en_us'»), но искать её в логе —
	 * не работа игрока.
	 */
	private static volatile String loadedLanguage = "";

	/**
	 * Сменился ли язык клиента с момента загрузки словарей.
	 *
	 * <p>Сравнение строк, дешевле некуда — можно звать хоть каждый тик.
	 * Пустой ответ игнорируем: на раннем старте языкового менеджера ещё нет,
	 * и перезагрузка там только навредит.
	 *
	 * <p>⚠️ Сравниваем язык СЛОВАРЕЙ, а не клиента. С языком клиента вышло бы
	 * вечное «сменился»: у английского клиента он en_us, а словари собраны
	 * под ru_ru — и мод перечитывал бы 28 файлов каждую секунду, молча съедая
	 * кадры. Спрашивать надо ровно то, от чего зависит набор словарей.
	 */
	public static boolean languageChanged() {
		String now = dictionaryLanguage();
		return !now.isBlank() && !now.equals(loadedLanguage);
	}

	/**
	 * Необязательные словари, какие вообще нашлись: id -> описание.
	 *
	 * <p>Нужен, чтобы {@code /skyblockru packs} мог показать игроку, что можно
	 * включить. Без такого списка возможность есть, но о ней никто не узнает —
	 * а невидимая настройка всё равно что отсутствующая.
	 */
	private static final Map<String, String> OPTIONAL = new java.util.LinkedHashMap<>();

	/** Список необязательных словарей: id -> описание. Пустой, пока не загрузились. */
	public static Map<String, String> optionalPacks() {
		return Map.copyOf(OPTIONAL);
	}

	/** Включён ли необязательный словарь: сперва выбор игрока, потом умолчание файла. */
	public static boolean packEnabled(TranslationPack pack) {
		Boolean choice = RuConfig.get().packs.get(pack.id);
		return choice != null ? choice : pack.defaultEnabled;
	}

	private Translator() {
	}

	public static int packCount() {
		return loadedPacks;
	}

	public static int exactCount() {
		return EXACT.size() + TEMPLATES.size();
	}

	public static int templateCount() {
		return TEMPLATES.size();
	}

	public static int regexCount() {
		return REGEX.size();
	}

	public static int glossaryCount() {
		return GLOSSARY.size();
	}

	/** Тексты всех регулярок — диагностика по ним ищет правила, которые ни разу не совпали. */
	public static List<String> allRulePatterns() {
		return REGEX.stream().map(rule -> rule.pattern().pattern()).toList();
	}

	/** Перечитывает словари: встроенные в jar + пользовательские из config/skyblockru/packs. */
	public static synchronized void reload(Path userPacksDir) {
		PACKS.clear();
		EXACT.clear();
		TEMPLATES.clear();
		GLOSSARY.clear();
		PARAGRAPHS.clear();
		REGEX.clear();
		BY_ITEM.clear();

		List<String> problems = new ArrayList<>();
		OPTIONAL.clear();

		String language = dictionaryLanguage();
		// Справка по терминам живёт рядом со словарями и подчиняется тому же
		// языку: нет файла под язык игрока — просто не будет подсказок.
		Wiki.load(language);
		for (String name : builtinPackNames(language)) {
			try (InputStream stream = Translator.class.getResourceAsStream(BUILTIN_DIR + name)) {
				if (stream == null) {
					problems.add("builtin pack not found: " + name);
					continue;
				}
				JsonObject json = GSON.fromJson(
						new InputStreamReader(stream, StandardCharsets.UTF_8), JsonObject.class);
				TranslationPack pack = TranslationPack.fromJson(name, json, problems);
				// Необязательные словари запоминаем ВСЕГДА, даже выключенные:
				// иначе /skyblockru packs не смог бы предложить их включить.
				if (!pack.defaultEnabled || RuConfig.get().packs.containsKey(pack.id)) {
					OPTIONAL.put(pack.id, pack.about);
				}
				if (!packEnabled(pack)) {
					continue;
				}
				PACKS.add(pack);
			} catch (IOException | RuntimeException exception) {
				problems.add("builtin pack " + name + ": " + exception);
			}
		}

		// Пользовательские словари. Плоская папка читается всегда — так было
		// с самого начала, и ломать это нельзя. Подпапка с кодом языка —
		// для тех, кто держит рядом несколько языков.
		if (userPacksDir != null) {
			loadUserPacks(userPacksDir, problems);
			loadUserPacks(userPacksDir.resolve(language), problems);
		}

		// Меньший priority — важнее: такие пакеты применяем последними, чтобы они перекрыли остальные.
		PACKS.sort(Comparator.comparingInt((TranslationPack p) -> p.priority).reversed());

		// откуда пришёл ключ — чтобы в отчёте было видно, какие файлы спорят между собой
		Map<String, Seen> origin = new HashMap<>();

		for (TranslationPack pack : PACKS) {
			for (Map.Entry<String, String> entry : pack.exact.entrySet()) {
				String key = entry.getKey();
				String value = entry.getValue();
				checkEntry(pack.id, key, value, origin, problems, pack.identityOk(key));

				if (key.contains("{s}")) {
					// Записи с ником игрока превращаем в регулярку прямо при
					// загрузке. Иначе они мертвы: обобщение по числам ({n})
					// ник не ловит, и 82 собранные строки так и лежали без
					// перевода, сколько их ни переводи.
					ScopedRule rule = templateRule(key, value, pack.only);
					if (rule == null) {
						problems.add(pack.id + ": \"" + key + "\" and \"" + value
								+ "\" have different placeholder counts - cannot build the rule");
					} else {
						REGEX.add(rule);
					}
					continue;
				}
				if (key.contains("{n}")) {
					// шаблон написан руками: "+{n} Strength" -> "+{n} Сила"
					TEMPLATES.put(key, new Entry(value, pack.only));
					continue;
				}
				EXACT.put(key, new Entry(value, pack.only));
				String template = toTemplate(key);
				if (template != null) {
					// строку с конкретным числом обобщаем сами: "+5 Сила" закроет и "+7", и "+120"
					TEMPLATES.putIfAbsent(template, new Entry(toTemplateValue(value), pack.only));
				}
			}
			for (TranslationPack.RegexRule rule : pack.regex) {
				REGEX.add(new ScopedRule(rule.pattern(), rule.replacement(), pack.only,
						rule.translateGroups(), anchorOf(rule.pattern().pattern())));
			}
			pack.paragraphs.forEach((source, translation) ->
					PARAGRAPHS.put(source, new Entry(translation, pack.only)));
			pack.glossary.forEach((term, translation) ->
					GLOSSARY.put(term, new Entry(translation, pack.only)));
			pack.byItem.forEach((item, lines) ->
					BY_ITEM.computeIfAbsent(item, key -> new HashMap<>()).putAll(lines));
		}

		glossarySorted = GLOSSARY.entrySet().stream()
				.sorted(Comparator.comparingInt((Map.Entry<String, Entry> e) -> e.getKey().length()).reversed())
				.toList();

		loadedPacks = PACKS.size();
		// ⚠️ Запоминаем, ПОД КАКОЙ ЯЗЫК собран этот набор словарей. По нему
		// клиент замечает, что игрок сменил язык в настройках, и перечитывает
		// сам — см. languageChanged(). Без этого смена языка на лету оставляла
		// мод с чужими словарями до перезапуска игры.
		loadedLanguage = language;
		// иначе строки, помеченные как «перевода нет», так и остались бы без перевода
		TextTranslator.clearCache();
		// игрок мог сменить язык игры — ванильные названия спросим заново
		VanillaNames.clearCache();
		Diagnostics.setLoadProblems(problems);

		SkyblockRuClient.LOG.info("[SkyblockRU] language {}: {} packs, {} lines, {} rules, {} terms",
				language, loadedPacks, exactCount(), regexCount(), glossaryCount());
		if (!languagePacks) {
			// Кричим громко и по делу. Именно так однажды тихо умер весь перевод:
			// язык определился как en_us, папки под него нет, в логе было только
			// «dictionaries: 1» — и ни одной жалобы. Молчать тут нельзя.
			SkyblockRuClient.LOG.warn("[SkyblockRU] NO DICTIONARIES for language '{}' - "
					+ "the game will stay English. Available: {}", language, availableLanguages());
		}
		for (String problem : problems) {
			SkyblockRuClient.LOG.warn("[SkyblockRU] {}", problem);
		}
	}

	/**
	 * Проверки, которые ловят типовые ошибки в словарях.
	 * Каждая появилась после того, как на неё наступили вживую.
	 */
	private static void checkEntry(String packId, String key, String value,
	                               Map<String, Seen> origin, List<String> problems,
	                               boolean allowIdentity) {
		// Файл сохранён с двойным экранированием: в ключ попал текст "" вместо символа.
		// Внешне выглядит правильно, а совпадать не будет никогда.
		if (ESCAPED_LITERAL.matcher(key).find()) {
			problems.add(packId + ": key \"" + key + "\" holds the TEXT \\uXXXX instead of the character - "
					+ "the file was saved double-escaped, the rule will never match");
		}
		// Число дырок {n} в ключе и переводе должно совпадать, иначе подстановка перекосится.
		int keyHoles = count(key, "{n}");
		int valueHoles = count(value, "{n}");
		if (keyHoles != valueHoles) {
			problems.add(packId + ": \"" + key + "\" - {n} placeholders in the source: " + keyHoles
					+ ", in the translation: " + valueHoles);
		}
		// ⚠️ Тождественная запись обычно мусор — движок и так оставит строку.
		// Но у словаря заголовков она и есть ИНСТРУМЕНТ: `Paragraphs.header`
		// режет найденный перевод только когда вырезанное совпадает с переводом
		// первой строки, а имена зачарований мы не переводим — значит их
		// «перевод» и есть оригинал. Без записи lookup вернёт null, резка
		// отменится, заголовок слипнется с описанием. Таких записей 1229,
		// и жалоба на них горела всегда — а вечно красный сторож приучает
		// не смотреть на красное, то есть прячет настоящую беду.
		if (key.equals(value) && !allowIdentity) {
			problems.add(packId + ": \"" + key + "\" translates to itself - the entry is useless");
		}
		// Иконки Hypixel (сердце, мана, категории мобов) — символы приватной зоны.
		// Переводчик их легко теряет: на экране они выглядят «мусором», и рука тянется убрать.
		// А в игре на их месте окажется дыра в подсказке.
		String lostIcons = missingIcons(key, value);
		if (!lostIcons.isEmpty()) {
			problems.add(packId + ": \"" + key + "\" - the translation lost Hypixel icons ("
					+ lostIcons + "), the game will show a hole there");
		}
		// Ругаемся только когда переводы РАЗНЫЕ: скачанный словарь штатно перекрывает
		// встроенный теми же строками, и жаловаться на каждое совпадение — шум.
		//
		// ⚠️ Пара «пакет + перевод» лежит РЕКОРДОМ, а не склеенной строкой.
		// Раньше склеивали и разбирали обратно через split, разделитель из
		// исходника пропал — и осталось split("") по пустой строке. Java режет
		// такое по буквам: в parts[0] попадала ПЕРВАЯ БУКВА имени пакета,
		// в parts[1] — остаток имени вместе с переводом, и он не совпадал
		// с переводом никогда. Отсюда 59 жалоб на совпадающие строки
		// («g and rarity translate it differently» — это «glossary»,
		// от которого осталась одна буква). Настоящий конфликт в таком шуме
		// уже не разглядеть, то есть проверка не просто врала — она молчала
		// про то, ради чего написана.
		Seen previous = origin.get(key);
		if (previous != null && !previous.packId().equals(packId)
				&& !previous.value().equals(value)) {
			problems.add("key \"" + key + "\": " + previous.packId() + " and " + packId
					+ " translate it differently (\"" + previous.value() + "\" vs \"" + value + "\")");
		}
		origin.put(key, new Seen(packId, value));
	}

	/**
	 * Иконки, которые есть в оригинале, но потерялись в переводе.
	 * Возвращает их коды через запятую; пустая строка — всё на месте.
	 */
	private static String missingIcons(String key, String value) {
		StringBuilder lost = new StringBuilder();
		for (int i = 0; i < key.length(); i++) {
			char c = key.charAt(i);
			if (c >= 0xE000 && c <= 0xF8FF && value.indexOf(c) < 0) {
				String code = String.format("U+%04X", (int) c);
				if (lost.indexOf(code) < 0) {
					if (lost.length() > 0) {
						lost.append(", ");
					}
					lost.append(code);
				}
			}
		}
		return lost.toString();
	}

	private static int count(String text, String part) {
		int total = 0;
		int at = text.indexOf(part);
		while (at >= 0) {
			total++;
			at = text.indexOf(part, at + part.length());
		}
		return total;
	}

	/** Читает словари игрока из одной папки. Нет папки — молча ничего, это норма. */
	private static void loadUserPacks(Path dir, List<String> problems) {
		if (dir == null || !Files.isDirectory(dir)) {
			return;
		}
		try (Stream<Path> files = Files.list(dir)) {
			List<Path> jsons = files
					.filter(p -> p.getFileName().toString().endsWith(".json"))
					.sorted()
					.toList();
			for (Path path : jsons) {
				try {
					JsonObject json = GSON.fromJson(
							Files.readString(path, StandardCharsets.UTF_8), JsonObject.class);
					TranslationPack userPack = TranslationPack.fromJson(
								path.getFileName().toString(), json, problems);
						// ⚠️ ПЕРЕКЛЮЧАТЕЛЬ ДЕЙСТВУЕТ И ЗДЕСЬ. Раньше пользовательский
						// словарь клали в PACKS без разбора: пакет с «default»: false
						// из config/skyblockru/packs применялся ВСЕГДА, в обход
						// /skyblockru pack <id> off. Игрок выключал перевод, а тот
						// оставался — и объяснить это было нечем.
						if (!userPack.defaultEnabled
								|| RuConfig.get().packs.containsKey(userPack.id)) {
							OPTIONAL.put(userPack.id, userPack.about);
						}
						if (!packEnabled(userPack)) {
							continue;
						}
						PACKS.add(userPack);
				} catch (IOException | RuntimeException exception) {
					problems.add("pack " + path.getFileName() + ": " + exception);
				}
			}
		} catch (IOException exception) {
			problems.add("cannot read packs folder " + dir + ": " + exception);
		}
	}

	/**
	 * Язык, выбранный в клиенте: {@code ru_ru}, {@code en_us} и т.п.
	 *
	 * <p>Проверено javap по официальным маппингам 26.2:
	 * {@code LanguageManager.getSelected()} возвращает именно строку-код.
	 *
	 * <p>Minecraft может быть ещё не поднят (ранняя инициализация, тесты) —
	 * тогда честнее вернуть en_us, чем уронить загрузку словарей.
	 */
	/**
	 * Язык СЛОВАРЕЙ — он же язык, на который мод переводит.
	 *
	 * <p>⚠️ Раньше это был просто язык клиента, и мод молчал, если словарей
	 * под него нет: «лучше без перевода, чем чужой язык». Довод верный для
	 * мода, который переводит НА язык игрока, но наш переводит НА РУССКИЙ —
	 * его для этого и ставят. Игрок запустил новый инстанс с английским
	 * клиентом и получил полностью английский экран при живом моде; правильный
	 * ответ тут не «включи русский в настройках», а «переводи всё равно».
	 *
	 * <p>Порядок выбора:
	 * <ol>
	 *   <li>язык, явно заданный в конфиге ({@code language}) — если под него
	 *       есть словари;</li>
	 *   <li>язык клиента — если под него есть словари: у того, кто играет
	 *       по-русски, ничего не меняется;</li>
	 *   <li>единственный доступный язык — наш случай, словари только
	 *       {@code ru_ru};</li>
	 *   <li>язык по умолчанию из {@code index.json} ({@code defaultLanguage}) —
	 *       осознанный выбор автора сборки, а не догадка.</li>
	 * </ol>
	 *
	 * <p>⚠️ РАНЬШЕ ПОСЛЕДНИМ ПУНКТОМ БЫЛ «ПЕРВЫЙ ПО АЛФАВИТУ», и это ловушка
	 * с отложенным сроком: пока язык один, работает пункт 3, и всё хорошо.
	 * Стоит появиться второму — скажем, {@code de_de} — и русский игрок
	 * с английским клиентом получил бы НЕМЕЦКИЙ экран, потому что «de» раньше
	 * «ru». Сработало бы не в день правки, а в день, когда придёт первый
	 * переводчик, — и виноватым выглядел бы он.
	 * Теперь запасной язык назван явно в {@code index.json}.
	 *
	 * <p>⚠️ Цена отвязки — записи, которые берут текст У КЛИЕНТА через
	 * {@code @ключ} (ванильные названия и зачарования). При английском клиенте
	 * они придут английскими: «Protection V» вместо «Защита V». Замер: таких
	 * записей 153 во включённых словарях (ещё 2585 — в выключенных по умолчанию
	 * {@code vanilla_names} и {@code sb_stats}, они не в счёт). Это осознанный
	 * размен: 153 английских названия против полностью английского экрана.
	 */
	public static String dictionaryLanguage() {
		List<String> available = availableLanguages();
		if (available.isEmpty()) {
			return languageCode();
		}
		String forced = RuConfig.get().language;
		if (forced != null && !forced.isBlank()) {
			String wanted = forced.toLowerCase(java.util.Locale.ROOT);
			if (available.contains(wanted)) {
				return wanted;
			}
			SkyblockRuClient.LOG.warn("[SkyblockRU] config language '{}' has no dictionaries,"
					+ " ignoring it. Available: {}", forced, available);
		}
		String client = languageCode();
		if (available.contains(client)) {
			return client;
		}
		if (available.size() == 1) {
			return available.get(0);
		}
		// ⚠️ Языков несколько, а под клиент словарей нет. Алфавит тут не судья:
		// он выдал бы игроку случайный чужой язык. Спрашиваем автора сборки.
		String fallback = defaultLanguage();
		String pick = available.contains(fallback) ? fallback : client;
		SkyblockRuClient.LOG.warn("[SkyblockRU] no dictionaries for client language '{}',"
				+ " using '{}'. Set \"language\" in config to choose. Available: {}",
				client, pick, available);
		return pick;
	}

	/**
	 * Язык, на который мод переводит, когда язык клиента не подошёл.
	 *
	 * <p>Лежит в {@code index.json} полем {@code defaultLanguage}. Поля нет —
	 * возвращаем пусто, и тогда игра остаётся английской: это честнее, чем
	 * показать игроку язык, которого он не просил.
	 */
	public static String defaultLanguage() {
		try (InputStream stream = Translator.class.getResourceAsStream(BUILTIN_DIR + "index.json")) {
			if (stream == null) {
				return "";
			}
			JsonObject json = GSON.fromJson(new InputStreamReader(stream, StandardCharsets.UTF_8), JsonObject.class);
			return json.has("defaultLanguage") ? json.get("defaultLanguage").getAsString() : "";
		} catch (IOException | RuntimeException exception) {
			return "";
		}
	}

	public static String languageCode() {
		try {
			net.minecraft.client.Minecraft client = net.minecraft.client.Minecraft.getInstance();
			if (client != null && client.getLanguageManager() != null) {
				String code = client.getLanguageManager().getSelected();
				if (code != null && !code.isBlank()) {
					return code.toLowerCase(java.util.Locale.ROOT);
				}
			}
		} catch (RuntimeException | LinkageError ignored) {
			// язык не спросить у игры — спросим у её настроек, ниже
		}
		return languageFromOptions();
	}

	/**
	 * Язык из options.txt.
	 *
	 * <p>⚠️ Это не «на всякий случай», а обязательный путь. Словари грузятся
	 * в onInitializeClient, а там {@code LanguageManager} ещё не поднят —
	 * и первая версия честно откатывалась на en_us. Папки en_us нет, поэтому
	 * не грузилось НИ ОДНОГО языкового словаря: в логе «dictionaries: 1»
	 * (только common), а в игре перевод пропал целиком. Ошибка тихая:
	 * ни исключения, ни предупреждения — просто английский текст.
	 */
	private static String languageFromOptions() {
		try {
			Path options = net.fabricmc.loader.api.FabricLoader.getInstance()
					.getGameDir().resolve("options.txt");
			if (Files.isRegularFile(options)) {
				for (String line : Files.readAllLines(options, StandardCharsets.UTF_8)) {
					if (line.startsWith("lang:")) {
						String code = line.substring("lang:".length()).trim();
						if (!code.isBlank()) {
							return code.toLowerCase(java.util.Locale.ROOT);
						}
					}
				}
			}
		} catch (IOException | RuntimeException ignored) {
			// настроек нет или они нечитаемы — останемся без перевода, но без падения
		}
		return "en_us";
	}

	/** Есть ли вообще перевод под выбранный язык. По нему /skyblockru честно говорит «нет». */
	public static boolean hasLanguagePacks() {
		return languagePacks;
	}

	/** Языки, для которых словари есть, — чтобы жалоба в логе была полезной. */
	public static List<String> availableLanguages() {
		try (InputStream stream = Translator.class.getResourceAsStream(BUILTIN_DIR + "index.json")) {
			if (stream == null) {
				return List.of();
			}
			JsonObject json = GSON.fromJson(new InputStreamReader(stream, StandardCharsets.UTF_8), JsonObject.class);
			JsonObject languages = json.getAsJsonObject("languages");
			return languages == null ? List.of() : List.copyOf(languages.keySet());
		} catch (IOException | RuntimeException exception) {
			return List.of();
		}
	}

	/**
	 * Имена встроенных пакетов для языка: сперва общие, потом языковые.
	 *
	 * <p>Содержимое jar не перечислить, поэтому список лежит в index.json.
	 * Раскладка: {@code common/} работает на любом языке (там @ключи, а не текст),
	 * {@code <язык>/} — собственно перевод. Нет папки под язык игрока — вернём
	 * только общие, и игра просто останется английской. Это правильное поведение:
	 * лучше без перевода, чем чужой язык.
	 */
	private static List<String> builtinPackNames(String language) {
		try (InputStream stream = Translator.class.getResourceAsStream(BUILTIN_DIR + "index.json")) {
			if (stream == null) {
				return List.of();
			}
			JsonObject json = GSON.fromJson(new InputStreamReader(stream, StandardCharsets.UTF_8), JsonObject.class);
			List<String> names = new ArrayList<>();
			if (json.has("common") && json.get("common").isJsonArray()) {
				json.getAsJsonArray("common").forEach(e -> names.add("common/" + e.getAsString()));
			}
			languagePacks = false;
			JsonObject languages = json.getAsJsonObject("languages");
			if (languages != null && languages.has(language) && languages.get(language).isJsonArray()) {
				languagePacks = true;
				languages.getAsJsonArray(language)
						.forEach(e -> names.add(language + "/" + e.getAsString()));
			}
			return names;
		} catch (IOException | RuntimeException exception) {
			SkyblockRuClient.LOG.warn("[SkyblockRU] index.json of builtin packs unreadable: {}", exception.toString());
			return List.of();
		}
	}

	/**
	 * Ищет перевод строки. Возвращает null, если ничего не нашлось —
	 * тогда вызывающий код оставляет оригинал и (если включено) пишет строку в дамп.
	 */
	public static Match lookup(String source, String origin) {
		return lookup(source, origin, null);
	}

	/**
	 * @param item предмет, в чьей подсказке встретилась строка. Если для него задан
	 *             отдельный перевод — берётся он: одна и та же строка у разных
	 *             предметов может продолжать разные фразы, и общий словарь тут врёт.
	 */
	public static Match lookup(String source, String origin, String item) {
		if (source == null || source.isBlank()) {
			return null;
		}

		if (item != null) {
			Map<String, String> lines = BY_ITEM.get(item);
			if (lines != null) {
				String personal = lines.get(source);
				if (personal != null) {
					return match(personal, Diagnostics.KIND_BY_ITEM);
				}
			}
		}

		Entry exact = EXACT.get(source);
		if (exact != null && exact.allows(origin)) {
			return match(exact.value(), Diagnostics.KIND_EXACT);
		}

		String byTemplate = byNumberTemplate(source, origin);
		if (byTemplate != null) {
			return match(byTemplate, Diagnostics.KIND_TEMPLATE);
		}

		for (ScopedRule rule : REGEX) {
			if (!rule.allows(origin)) {
				continue;
			}
			// ⚠️ Дешёвый отказ до дорогой регулярки — см. anchorOf: вдвое
			// быстрее на живых данных, поведение то же по построению.
			if (!rule.maybe(source)) {
				continue;
			}
			Matcher matcher = rule.pattern().matcher(source);
			if (matcher.matches()) {
				Diagnostics.ruleHit(rule.pattern().pattern());
				String result = rule.translateGroups()
						? expandGroups(rule.replacement(), matcher, origin)
						: matcher.replaceFirst(rule.replacement());
				return match(result, Diagnostics.KIND_REGEX);
			}
		}

		return null;
	}

	/**
	 * Подставляет захваченные куски, переводя каждый по словарю.
	 *
	 * <p>Нужно для строк «название + постоянная фраза». Пример из подсказки
	 * миньона: «Cobblestone. Minions also work when». Постоянную часть закрывает
	 * одно правило на всех миньонов, а вот материал у каждого свой — и без
	 * перевода куска строка выходила наполовину английской.
	 *
	 * <p>Кусок переводим ТОЛЬКО точным словарём и глоссарием, но не правилами:
	 * иначе правило может позвать само себя и уйти в бесконечность.
	 */
	private static String expandGroups(String replacement, Matcher matcher, String origin) {
		StringBuilder out = new StringBuilder(replacement.length() + 16);
		for (int i = 0; i < replacement.length(); i++) {
			char symbol = replacement.charAt(i);
			boolean isGroupRef = symbol == '$'
					&& i + 1 < replacement.length()
					&& Character.isDigit(replacement.charAt(i + 1));
			if (!isGroupRef) {
				out.append(symbol);
				continue;
			}
			int number = replacement.charAt(i + 1) - '0';
			i++;
			if (number < 1 || number > matcher.groupCount()) {
				continue;
			}
			String raw = matcher.group(number);
			if (raw != null) {
				out.append(translateGroup(raw, origin));
			}
		}
		return out.toString();
	}

	/**
	 * Насколько глубоко пускаем перевод захваченного куска.
	 *
	 * <p>Один уровень нужен по делу: «Objective: Talk to Susan» — подпись
	 * переводит одно правило, а «Talk to Susan» внутри неё уже другое.
	 * Глубже нельзя: правило, поймавшее собственный результат, зациклится.
	 */
	private static final int MAX_GROUP_DEPTH = 1;

	private static final ThreadLocal<int[]> GROUP_DEPTH = ThreadLocal.withInitial(() -> new int[1]);

	/** Перевод одного захваченного куска: словарь целиком, иначе глоссарий, иначе как есть. */
	private static String translateGroup(String raw, String origin) {
		int[] depth = GROUP_DEPTH.get();
		if (depth[0] < MAX_GROUP_DEPTH) {
			depth[0]++;
			try {
				Match nested = lookup(raw, origin, null);
				if (nested != null) {
					return nested.text();
				}
			} finally {
				depth[0]--;
			}
		}
		// ⚠️ НАБОР ВАРИАНТОВ ОТВЕТА режем на части.
		//
		// «Select an option: [Absolutely!] [Tell me more…] [Not right now.]» —
		// захват тут ВЕСЬ набор сразу, и как ключ он бесполезен: наборы
		// не повторяются, у каждого NPC свой. Это ровно та же комбинаторика,
		// что была с зачарованиями, и лечится так же — переводом КУСКОВ.
		//
		// Замер по живому дампу: наборов 21, а разных вариантов внутри 24,
		// причём 18 из них уже переведены поштучно. То есть словарь почти
		// готов, ему просто не давали сработать.
		String byChoices = translateChoices(raw, origin);
		if (byChoices != null) {
			return byChoices;
		}

		String byGlossary = applyGlossary(raw, origin);
		if (byGlossary != null) {
			return byGlossary;
		}
		// ⚠️ Кусок перевести не удалось — записываем его как непереведённый.
		//
		// Без этого он НЕВИДИМ для очереди: строка целиком считается переведённой
		// (правило-то сработало), в untranslated.json её нет, и заметить беду
		// можно только глазами в игре. Так реплики выбора в диалогах NPC —
		// «Выбери вариант: [Yeah. Why is that?]» — оставались английскими,
		// и спросить их перевод было неоткуда.
		if (looksLikePhrase(raw)) {
			UnknownStrings.record(origin, raw);
		}
		return raw;
	}

	/**
	 * Строка целиком из вариантов в скобках: «[Да!] [Нет.] [Подумаю.]»
	 *
	 * <p>⚠️ Между вариантами Hypixel ставит не только пробел. Длинный набор он
	 * пишет СТОЛБИКОМ, помечая каждый вариант стрелкой:
	 * <pre>«➜ [How are perks chosen?] \n  ➜ [What are Special Mayors?]»</pre>
	 * Прежний шаблон требовал строку из ОДНИХ скобок, такой набор не резался
	 * вовсе — и на экране выходило худшее из возможного: подпись «Выбери
	 * вариант:» по-русски, а все варианты под ней по-английски.
	 *
	 * <p>Поэтому разделителем считаем что угодно, кроме букв, цифр и самих
	 * скобок: тогда стрелка, перенос и отступ проходят, а текст между
	 * вариантами — нет (иначе под «набор» попала бы обычная фраза со вставкой
	 * в скобках). Сами разделители при сборке сохраняются как есть.
	 */
	private static final Pattern CHOICE_SET =
			Pattern.compile("^(?:[^\\p{L}\\p{N}\\[\\]]*\\[[^\\]]+\\][^\\p{L}\\p{N}\\[\\]]*)+$");

	/** Один вариант вместе со скобками — в словаре они лежат именно так. */
	private static final Pattern CHOICE = Pattern.compile("\\[[^\\]]+\\]");

	/**
	 * Перевод НАБОРА вариантов ответа — по одному варианту за раз.
	 *
	 * <p>Каждый вариант ищется в словаре отдельно, потому что конечны именно
	 * они, а не их сочетания. Ненайденный остаётся английским И ЗАПИСЫВАЕТСЯ
	 * поштучно — так его можно спросить в следующий раз; раньше в дамп уезжал
	 * весь набор, а такой ключ не встретится второй раз никогда.
	 *
	 * <p>⚠️ Смешанный набор («[Да!] [Give me a moment.]») — это смесь языков,
	 * и она хуже, чем совсем без перевода: мод сам себя за такое ругает
	 * в {@code UnknownStrings.noteMixed}. Поэтому либо переводим ВЕСЬ набор,
	 * либо не трогаем его вовсе.
	 *
	 * @return переведённый набор или null, если это не набор либо перевод
	 *         нашёлся не для всех вариантов
	 */
	private static String translateChoices(String raw, String origin) {
		String text = raw.trim();
		if (text.isEmpty() || !CHOICE_SET.matcher(text).matches()) {
			return null;
		}
		Matcher parts = CHOICE.matcher(raw);
		StringBuilder out = new StringBuilder();
		int last = 0;
		boolean all = true;
		while (parts.find()) {
			out.append(raw, last, parts.start());
			String option = parts.group();
			Match found = lookup(option, origin, null);
			if (found == null) {
				all = false;
				out.append(option);
				UnknownStrings.record(origin, option);
			} else {
				out.append(found.text());
			}
			last = parts.end();
		}
		out.append(raw.substring(last));
		return all ? out.toString() : null;
	}

	/**
	 * Кусок похож на ФРАЗУ, а не на имя?
	 *
	 * <p>Признак тот же, что во всём проекте: имена Hypixel пишет с заглавной
	 * («Gold Ore», «Cobblestone»), а в обычной фразе есть слова со строчной.
	 * Нужен, чтобы в очередь не поехали названия материалов из правил миньонов:
	 * их мы не переводим по замыслу, и копить их незачем.
	 */
	private static boolean looksLikePhrase(String raw) {
		String clean = LegacyText.strip(raw).trim();
		if (clean.length() < 6 || clean.indexOf(' ') < 0) {
			return false;
		}
		for (String word : clean.split("[^\\p{L}']+")) {
			if (word.length() > 2 && Character.isLowerCase(word.charAt(0))) {
				return true;
			}
		}
		return false;
	}

	/**
	 * Достраивает перевод: @ключи заменяются на официальный перевод из самой игры.
	 * Если игра такого ключа не знает — перевода нет вовсе, лучше оставить оригинал,
	 * чем показать игроку сырой ключ.
	 */
	private static Match match(String value, String kind) {
		if (VanillaNames.hasKeys(value)) {
			String expanded = VanillaNames.expand(value);
			return expanded == null ? null : new Match(expanded, kind);
		}
		return new Match(value, kind);
	}

	/**
	 * Частичный перевод: подменяет знакомые термины внутри незнакомой строки.
	 * Возвращает null, если ничего не заменилось.
	 */
	public static String applyGlossary(String source, String origin) {
		if (glossarySorted.isEmpty() || source.isBlank()) {
			return null;
		}
		String result = source;
		boolean changed = false;
		for (Map.Entry<String, Entry> entry : glossarySorted) {
			Entry value = entry.getValue();
			if (!value.allows(origin)) {
				continue;
			}
			// Термины без области действия — это грубая замена «всё подряд», она
			// даёт смесь языков, поэтому включается отдельным флагом. Термины,
			// ограниченные категорией, автор словаря задал осознанно — их применяем всегда.
			if (value.only() == null && !RuConfig.get().glossaryPass) {
				continue;
			}
			String term = entry.getKey();
			int index = result.indexOf(term);
			if (index < 0) {
				continue;
			}
			// только целые слова: иначе «Bow» испортит «Bowl»
			if (!isWordBoundary(result, index, term.length())) {
				continue;
			}
			// ...и не ВНУТРИ составного имени: «Depth Champion» — имя бонуса
			if (insideProperName(result, index, term)) {
				continue;
			}
			String replacement = value.value();
			if (VanillaNames.hasKeys(replacement)) {
				replacement = VanillaNames.expand(replacement);
				if (replacement == null) {
					continue; // игра такого ключа не знает — оставляем как было
				}
			}
			result = result.replace(term, replacement);
			changed = true;
		}
		if (!changed) {
			return null;
		}
		// ⚠️ Не отдаём СМЕСЬ ЯЗЫКОВ.
		//
		// Живой случай: «Grants +0◆ Mining Spread on Ores and Blocks.» глоссарий
		// превращал в «Grants +0◆ Разброс добычи on Ores and Blocks.» — одно
		// русское словосочетание посреди английской фразы. Читается хуже, чем
		// английская строка целиком, и в правилах проекта это записано прямо.
		//
		// Ради чего глоссарий с областью вообще заводился — список зачарований
		// «Wisdom V, Growth VI, Protection VI»: там после подстановки НЕ ОСТАЁТСЯ
		// английских слов, и проверка его пропускает. А прозу, где английского
		// после подстановки больше, чем русского, откатываем целиком.
		return stillEnglish(result) ? null : result;
	}

	/**
	 * После подстановки в строке осталось БОЛЬШЕ английских слов, чем русских?
	 *
	 * <p>Считаем слова, а не буквы: у русских слов буквы длиннее, и по буквам
	 * счёт перекашивался бы в их пользу. Числа, значки и разметка не в счёт —
	 * они одинаковы на любом языке.
	 */
	static boolean stillEnglish(String text) {
		int latin = 0;
		int cyrillic = 0;
		int at = 0;
		while (at < text.length()) {
			char symbol = text.charAt(at);
			if (!Character.isLetter(symbol)) {
				at++;
				continue;
			}
			boolean isCyrillic = symbol >= 'Ѐ' && symbol <= 'ӿ';
			int start = at;
			while (at < text.length() && Character.isLetter(text.charAt(at))) {
				at++;
			}
			// слово из одной буквы ничего не решает: это «a», «I», инициал
			if (at - start > 1 && !isRoman(text, start, at)) {
				if (isCyrillic) {
					cyrillic++;
				} else {
					latin++;
				}
			}
		}
		return latin > cyrillic;
	}

	/**
	 * Слово — РИМСКАЯ ЦИФРА? Такие не считаем ни за русские, ни за английские.
	 *
	 * <p>⚠️ Живой случай, из-за которого список зачарований оставался целиком
	 * английским: «Strong Vitality V, Sugar Rush III, Thorns III». После
	 * подстановки выходит «Сильная живучесть V, Sugar Rush III, Шипы III» —
	 * три русских слова против четырёх «английских», и два из этих четырёх —
	 * уровни «III». Перевес мнимый: римская цифра одинакова на любом языке,
	 * ровно как числа и значки, которые счёт и так пропускает. А уровней
	 * в списке столько же, сколько названий, поэтому они и перевешивали —
	 * тем вернее, чем больше зачарований переведено.
	 */
	private static boolean isRoman(String text, int start, int end) {
		for (int at = start; at < end; at++) {
			if ("IVXLC".indexOf(text.charAt(at)) < 0) {
				return false;
			}
		}
		return true;
	}

	/**
	 * Термин стоит ВНУТРИ составного имени собственного?
	 *
	 * <p>Живой случай: «Tiered Bonus: Depth Champion (0/8)» превращалось
	 * в «Depth Чемпион». Зачарование {@code Champion} лежит в глоссарии с
	 * областью, то есть подставляется всегда, а {@code Depth Champion} —
	 * название бонуса комплекта, и его в словаре нет. Половина имени
	 * по-русски, половина по-английски: смесь языков хуже, чем целая
	 * английская фраза.
	 *
	 * <p>Признак: перед термином стоит ЕЩЁ ОДНО слово с заглавной буквы.
	 * Два слова с заглавной подряд — это составное имя, а не «слово из
	 * словаря посреди фразы». В списке зачарований такого не бывает: там
	 * перед термином либо начало строки, либо запятая («Wisdom V, Growth VI»).
	 *
	 * <p>Ложные срабатывания возможны в начале предложения («Grants Champion
	 * V»), и это осознанный размен: там останется английский, а не смесь.
	 */
	private static boolean insideProperName(String text, int index, String term) {
		if (term.isEmpty() || !Character.isUpperCase(term.charAt(0))) {
			return false;
		}
		int at = index - 1;
		if (at < 0 || text.charAt(at) != ' ') {
			return false;
		}
		at--;
		int end = at + 1;
		while (at >= 0 && Character.isLetter(text.charAt(at))) {
			at--;
		}
		int wordStart = at + 1;
		return wordStart < end && Character.isUpperCase(text.charAt(wordStart));
	}

	private static boolean isWordBoundary(String text, int start, int length) {
		int end = start + length;
		boolean leftOk = start == 0 || !Character.isLetterOrDigit(text.charAt(start - 1));
		boolean rightOk = end >= text.length() || !Character.isLetterOrDigit(text.charAt(end));
		return leftOk && rightOk;
	}

	/**
	 * «+5 Strength» -> ищем «+{n} Strength», в найденный перевод возвращаем те же числа
	 * на места {n}. Так один перевод работает для любых чисел.
	 */
	/**
	 * Ищет перевод целого абзаца.
	 *
	 * <p>Отдельно от {@link #lookup}, и намеренно СТРОГО: только точное
	 * совпадение и обобщение по числам. Ни глоссария, ни регулярок —
	 * абзац заменяет сразу несколько строк на экране, и ошибиться тут
	 * дороже, чем не перевести.
	 */
	public static Match lookupParagraph(String source, String origin, String item) {
		if (source == null || source.isBlank()) {
			return null;
		}
		if (item != null) {
			Map<String, String> personal = BY_ITEM.get(item);
			if (personal != null) {
				String found = personal.get(source);
				if (found != null) {
					return match(found, Diagnostics.KIND_BY_ITEM);
				}
			}
		}

		Entry exact = PARAGRAPHS.get(source);
		if (exact != null && exact.allows(origin)) {
			return match(exact.value(), Diagnostics.KIND_PARAGRAPH);
		}

		// «Даёт +5 к силе» должно закрывать и +7, и +120 — как у обычных строк
		String template = toTemplate(source);
		if (template != null) {
			Entry byNumbers = PARAGRAPHS.get(template);
			if (byNumbers != null && byNumbers.allows(origin)) {
				String filled = fillNumbers(byNumbers.value(), source);
				if (filled != null) {
					return match(filled, Diagnostics.KIND_PARAGRAPH);
				}
			}
		}
		return null;
	}

	/** Подстановки в записи словаря: {s} — ник игрока, {n} — число. */
	private static final Pattern ANY_HOLE = Pattern.compile("\\{[sn]}");

	/** Ник Minecraft: 3–16 знаков, буквы/цифры/подчёркивание. */
	/**
	 * Ник игрока — вместе с РАНГОМ, если он есть.
	 *
	 * <p>⚠️ Ловил только голый ник, а Hypixel почти везде пишет его с рангом:
	 * «Seller: [VIP] Matthewthe69». Скобки и пробел под шаблон не подходили,
	 * и запись «Seller: {s}» -> «Продавец: {s}» не срабатывала НИ РАЗУ на
	 * аукционе — подпись оставалась английской рядом с переведёнными
	 * «Купить сейчас» и «Закончится через».
	 *
	 * <p>Ранг необязателен: в чате и на панели ник приходит и без него.
	 */
	private static final String NAME_GROUP =
			"((?:\\[[A-Za-z+]{2,10}\\]\\s*)?[A-Za-z0-9_]{3,16})";

	private static final String NUMBER_GROUP = "([\\d,.]+)";

	/**
	 * Собирает регулярку из записи с подстановками.
	 *
	 * <p>«{s} has sent you a trade request» превращается в шаблон, где на месте
	 * {s} стоит ник. Подстановки нумеруются по порядку появления, и в переводе
	 * их должно быть столько же — иначе правило вышло бы кривым, и лучше честно
	 * сказать об этом в лог, чем молча получить «$2» на экране.
	 */
	private static ScopedRule templateRule(String key, String value, Set<String> only) {
		StringBuilder pattern = new StringBuilder("^");
		Matcher holes = ANY_HOLE.matcher(key);
		int last = 0;
		int count = 0;
		while (holes.find()) {
			pattern.append(Pattern.quote(key.substring(last, holes.start())));
			pattern.append("{s}".equals(holes.group()) ? NAME_GROUP : NUMBER_GROUP);
			last = holes.end();
			count++;
		}
		pattern.append(Pattern.quote(key.substring(last))).append("$");

		StringBuilder replacement = new StringBuilder();
		Matcher target = ANY_HOLE.matcher(value);
		int tail = 0;
		int used = 0;
		while (target.find()) {
			used++;
			replacement.append(value, tail, target.start()).append('$').append(used);
			tail = target.end();
		}
		replacement.append(value.substring(tail));

		if (used != count) {
			return null;
		}
		try {
			String text = pattern.toString();
			return new ScopedRule(Pattern.compile(text), replacement.toString(), only,
					false, anchorOf(text));
		} catch (java.util.regex.PatternSyntaxException exception) {
			return null;
		}
	}

	private static String byNumberTemplate(String source, String origin) {
		Matcher matcher = NUMBER.matcher(source);
		if (!matcher.find()) {
			return null;
		}

		List<String> numbers = new ArrayList<>();
		matcher.reset();
		StringBuilder template = new StringBuilder();
		int last = 0;
		while (matcher.find()) {
			template.append(source, last, matcher.start()).append("{n}");
			numbers.add(matcher.group());
			last = matcher.end();
		}
		template.append(source.substring(last));

		Entry entry = TEMPLATES.get(template.toString());
		if (entry == null || !entry.allows(origin)) {
			return null;
		}
		String translated = entry.value();

		Matcher holes = PLACEHOLDER.matcher(translated);
		StringBuilder out = new StringBuilder();
		int index = 0;
		while (holes.find()) {
			String value = index < numbers.size() ? numbers.get(index) : "";
			holes.appendReplacement(out, Matcher.quoteReplacement(value));
			index++;
		}
		holes.appendTail(out);
		return out.toString();
	}

	/**
	 * Подставляет числа исходной строки в дырки {n} перевода.
	 *
	 * <p>Вынесено из {@link #byNumberTemplate}, потому что то же самое нужно
	 * абзацам: правило «числа держим отдельно от текста» должно быть одно,
	 * иначе строки и абзацы разойдутся в мелочах.
	 */
	private static String fillNumbers(String translated, String source) {
		List<String> numbers = new ArrayList<>();
		Matcher matcher = NUMBER.matcher(source);
		while (matcher.find()) {
			numbers.add(matcher.group());
		}
		if (numbers.isEmpty()) {
			return null;
		}
		Matcher holes = PLACEHOLDER.matcher(translated);
		StringBuilder out = new StringBuilder();
		int index = 0;
		while (holes.find()) {
			String value = index < numbers.size() ? numbers.get(index) : "";
			holes.appendReplacement(out, Matcher.quoteReplacement(value));
			index++;
		}
		holes.appendTail(out);
		return out.toString();
	}

	/** Ключ-шаблон: числа заменяются на {n}. null, если чисел в строке нет. */
	private static String toTemplate(String key) {
		Matcher matcher = NUMBER.matcher(key);
		if (!matcher.find()) {
			return null;
		}
		return matcher.reset().replaceAll("{n}");
	}

	/**
	 * То же для значения перевода: числа в переводе тоже становятся дырками.
	 *
	 * <p>⚠️ §-КОДЫ ОБХОДИМ СТОРОНОЙ. Раньше здесь стояла регулярка чисел по всей
	 * строке — и цифра кода была для неё обычным числом: «§6Sirius» превращалось
	 * в «§{n}Sirius», а потом {@link #fillNumbers} подставлял в эту дырку
	 * настоящее число из строки, и вместо золотого цвета на экран шло «§123».
	 *
	 * <p>Замер на живых словарях: из 850 автошаблонов было испорчено 191, и все
	 * — в диалогах NPC, где разметка цвета стоит в каждой реплике. Беда тихая:
	 * словарь на месте, ошибок нет, а у реплики съезжает цвет и число.
	 *
	 * <p>Поэтому идём по строке кусками: код («§» и знак за ним) переносим как
	 * есть, а числа обобщаем только в тексте между кодами.
	 */
	private static String toTemplateValue(String value) {
		StringBuilder out = new StringBuilder(value.length());
		int at = 0;
		while (at < value.length()) {
			if (value.charAt(at) == '§' && at + 1 < value.length()) {
				out.append(value, at, at + 2);
				at += 2;
				continue;
			}
			int from = at;
			while (at < value.length()
					&& !(value.charAt(at) == '§' && at + 1 < value.length())) {
				at++;
			}
			out.append(NUMBER.matcher(value.substring(from, at)).replaceAll("{n}"));
		}
		return out.toString();
	}
}
