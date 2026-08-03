package ru.skyblockru.core;

import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;

import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import net.minecraft.ChatFormatting;
import net.minecraft.network.chat.Component;
import net.minecraft.world.item.ItemStack;
import ru.skyblockru.config.RuConfig;

/**
 * СПРАВКА по терминам SkyBlock: что это такое и зачем нужно.
 *
 * <p><b>Зачем.</b> Часть названий мы намеренно не переводим — по ним ищут вещи
 * на аукционе и читают гайды. Но игроку от английского слова толку мало:
 * «Overbloom» ничего не говорит о том, что это характеристика Земледелия
 * и что она даёт. Перевести — потерять поиск, оставить — потерять смысл.
 *
 * <p><b>Решение.</b> Ни то, ни другое: термин остаётся английским, а по Shift
 * под описанием появляется пояснение по-русски. Игрок получает и смысл,
 * и возможность найти вещь по английскому названию.
 *
 * <p>⚠️ Факты берутся из вики Hypixel, а не сочиняются: выдуманное описание
 * хуже отсутствующего, потому что ему верят.
 */
public final class Wiki {

	private static final Map<String, Entry> TERMS = new LinkedHashMap<>();

	/**
	 * Справка по ЗАЧАРОВАНИЯМ — отдельный набор и отдельная клавиша.
	 *
	 * <p><b>Почему не свалить в один.</b> Термины и зачарования отвечают на разные
	 * вопросы, и на предмете их бывает много сразу: у дрели восемь зачарований
	 * и три характеристики. Свалив всё в одну панель по одной клавише, мы бы
	 * показали простыню, в которой не найти нужное. Разные клавиши разделяют
	 * не «источники данных», а НАМЕРЕНИЕ игрока: он спрашивает либо «что это
	 * за характеристика», либо «что делает это зачарование».
	 */
	private static final Map<String, Entry> ENCHANTS = new LinkedHashMap<>();

	/** Линия между статьями — такая же, какую Hypixel рисует в подсказках. */
	private static final String SEPARATOR = "-".repeat(17);

	private Wiki() {
	}

	/**
	 * Одна статья: русское название, цвет термина и пояснение построчно.
	 *
	 * @param color §-код, каким Hypixel красит термин В ИГРЕ. Пусто — жёлтый.
	 *              Нужен, чтобы заголовок справки выглядел так же, как строка,
	 *              к которой он относится: игрок ищет глазами то же слово того
	 *              же цвета.
	 */
	public record Entry(String title, String color, List<String> lines) {
	}

	/**
	 * Читает справку из ресурсов мода для языка игрока.
	 *
	 * <p>Файла нет — просто нет справки: молчим, а не падаем.
	 */
	public static void load(String language) {
		read(language, "/assets/skyblockru/wiki/" + language + ".json", TERMS);
		// Зачарования лежат отдельным файлом: их 93, и наполняются они своим
		// темпом. Нет файла — просто нет справки по зачарованиям.
		read(language, "/assets/skyblockru/wiki/enchants_" + language + ".json", ENCHANTS);
	}

	private static void read(String language, String path, Map<String, Entry> into) {
		into.clear();
		try (InputStream stream = open(language, path)) {
			if (stream == null) {
				return;
			}
			JsonObject root = JsonParser.parseReader(
					new InputStreamReader(stream, StandardCharsets.UTF_8)).getAsJsonObject();
			JsonObject terms = root.getAsJsonObject("terms");
			if (terms == null) {
				return;
			}
			for (Map.Entry<String, JsonElement> item : terms.entrySet()) {
				JsonObject value = item.getValue().getAsJsonObject();
				List<String> lines = new ArrayList<>();
				value.getAsJsonArray("lines").forEach(line -> lines.add(line.getAsString()));
				into.put(item.getKey(), new Entry(
						value.has("title") ? value.get("title").getAsString() : "",
						value.has("color") ? value.get("color").getAsString() : "",
						lines));
			}
		} catch (RuntimeException | java.io.IOException ignored) {
			// битый файл справки — не повод ломать перевод
		}
	}

	/**
	 * Файл справки: сперва С ДИСКА, потом встроенный в jar.
	 *
	 * <p>⚠️ Ради этого справка и читается через отдельный метод. Словари уже
	 * умеют обновляться по сети ({@link UpdateService}) — они лежат в
	 * {@code config/skyblockru/packs} и перекрывают встроенные, поэтому новые
	 * переводы доезжают до игрока без нового jar. Справка так не умела: её
	 * читали только из ресурсов, то есть добавить статью значило пересобрать
	 * мод и заставить всех переустановить его.
	 *
	 * <p>Теперь {@code config/skyblockru/wiki/<язык>.json} перекрывает
	 * встроенный файл — тем же способом и с тем же ограничением: скачиваются
	 * ТОЛЬКО тексты, никогда не код.
	 */
	private static InputStream open(String language, String builtin) {
		try {
			Path dir = ru.skyblockru.SkyblockRuClient.configDir();
			if (dir != null) {
				Path file = dir.resolve("wiki").resolve(language + ".json");
				if (Files.isRegularFile(file)) {
					return Files.newInputStream(file);
				}
			}
		} catch (IOException | RuntimeException ignored) {
			// не прочитали свой файл — берём встроенный, справка не критична
		}
		return Wiki.class.getResourceAsStream(builtin);
	}

	public static int size() {
		return TERMS.size();
	}

	/** Сколько статей по зачарованиям — для /skyblockru. */
	public static int enchantSize() {
		return ENCHANTS.size();
	}

	/**
	 * Встречается ли термин в тексте КАК ОТДЕЛЬНОЕ СЛОВО.
	 *
	 * <p>⚠️ Голый {@code contains} находил термин внутри чужого слова, и справка
	 * показывала статью не про то: «Speed» всплывал внутри «Mining Speed»,
	 * «Heat» внутри «Heat Resistance». Границу проверяем по латинским буквам,
	 * а не через {@code \b}: термин бывает из двух слов, а сразу за ним идёт
	 * двоеточие, кириллица или значок. Тот же приём, что в
	 * {@code protected.mentions()} на стороне инструментов.
	 */
	private static boolean mentions(String text, String term) {
		return TermMatch.mentions(text, term, lineStarts);
	}

	/**
	 * Встречается ли ЗАЧАРОВАНИЕ — то есть имя ВМЕСТЕ С РИМСКИМ УРОВНЕМ.
	 *
	 * <p>⚠️ Одного имени НЕДОСТАТОЧНО, и это стоило двух неверных починок.
	 * Зачарование «Chance» — обычное слово, оно сидит внутри характеристик
	 * «Sea Creature Chance», «Treasure Chance», «Double Hook Chance» и любых
	 * будущих. Сперва я гасил такие случаи отсевом по длине — но он работает,
	 * только если длинный термин ЕСТЬ В СПРАВКЕ. Статьи «Treasure Chance» нет,
	 * и заплатка тут же перестала помогать.
	 *
	 * <p>Признак нужен не «какой термин длиннее», а «зачарование ли это вообще».
	 * В подсказке Hypixel пишет зачарование только с уровнем: «Chance V»,
	 * «Growth VI». У характеристики уровня не бывает никогда. Тот же приём уже
	 * работает в инструментах ({@code translate_tooltips.enchants_in}), где
	 * «Growth V» защищают, а «growth» в прозе переводят.
	 */
	private static boolean mentionsEnchant(String text, String name) {
		return TermMatch.mentionsEnchant(text, name);
	}

	private static void dropSwallowed(List<String> found, String text) {
		found.removeIf(term -> swallowedBy(term, text));
	}

	/**
	 * Лежит ли имя целиком внутри более длинного, которое ТОЖЕ есть в тексте.
	 *
	 * <p>⚠️ Смотрим ОБА словаря сразу, и это суть починки. Зачарование
	 * «Chance» проверялось только против других зачарований — а поглощает его
	 * ТЕРМИН «Sea Creature Chance», лежащий в другом файле. Поэтому на наживке
	 * по Alt всплывала статья про зачарование, которого в предмете нет вовсе.
	 *
	 * <p>Первая попытка чинила это отсевом внутри одного списка и, конечно,
	 * не помогла: списка два, а текст один.
	 */
	private static boolean swallowedBy(String term, String text) {
		for (String other : TERMS.keySet()) {
			if (other.length() > term.length() && other.contains(term) && mentions(text, other)) {
				return true;
			}
		}
		for (String other : ENCHANTS.keySet()) {
			if (other.length() > term.length() && other.contains(term) && mentions(text, other)) {
				return true;
			}
		}
		return false;
	}

	/**
	 * Есть ли в подсказке зачарование, про которое мы можем рассказать.
	 *
	 * <p>⚠️ Спрашиваем СЕРВЕР, когда он отвечает: список из NBT говорит прямо,
	 * какие зачарования на вещи. Признак по форме («имя + римский уровень»)
	 * остаётся запасным — у большинства предметов списка нет вовсе.
	 * Без сервера приглашение «Alt — зачарования» висело на наживке, где
	 * зачарований нет, а есть характеристика со словом «Chance».
	 */
	private static boolean hasEnchantArticle(String text) {
		// ⚠️ Спрашиваем ТЕКСТ, а не NBT. Раньше при непустом списке от сервера
		// решение принималось по нему одному — и приглашение «Alt —
		// зачарования» не появлялось на предметах с Gravity, Drain, Prismatic
		// и ещё четырьмя: сервер их в NBT не кладёт вовсе, хотя в лоре они
		// стоят. Приглашение обязано совпадать с тем, что покажет панель,
		// а панель теперь ищет по форме «имя + римский уровень».
		for (String name : ENCHANTS.keySet()) {
			if (TermMatch.showArticle(text, name)) {
				return true;
			}
		}
		return false;
	}

	/**
	 * Зажата ли клавиша справки.
	 *
	 * <p>⚠️ Раньше здесь был Shift, зашитый константой. Клавишу теперь задаёт
	 * игрок в обычном меню управления ({@link Keys}) — иначе возможность,
	 * которую нельзя переназначить, для части игроков просто отсутствует:
	 * Shift может не работать или быть занят другим модом.
	 */
	private static boolean shiftDown() {
		return Keys.down(Keys.WIKI);
	}

	/**
	 * Готовая справка для предмета под курсором и размеры его подсказки.
	 *
	 * <p>Размеры нужны, чтобы поставить панель РЯДОМ: позицию основной
	 * подсказки без них не вычислить, а спросить её у игры уже нельзя —
	 * к моменту отрисовки она ещё не построена.
	 */
	public record Panel(ItemStack stack, List<Component> lines,
	                    int mainWidth, int mainHeight) {
	}

	private static Panel pending;

	/**
	 * Где начинается каждая строка в склеенном тексте подсказки.
	 *
	 * <p>Нужно, чтобы правило «слева слово с заглавной — часть имени» не смотрело
	 * ЧЕРЕЗ границу строк: строки склеены пробелом, и последнее слово имени
	 * предмета оказывается вплотную к первому термину лора. Подробности —
	 * в {@link TermMatch#crossesLine}.
	 *
	 * <p>⚠️ Поле статическое, как {@link #pending} и {@link #sweeping} рядом:
	 * подсказка строится в одном потоке рендера, и значение живёт ровно один
	 * вызов {@code append}. Передавать его параметром пришлось бы через шесть
	 * сигнатур, включая {@code dropSwallowed}.
	 */
	private static java.util.List<Integer> lineStarts;

	/**
	 * Сбор подсказок обходит ВСЕ предметы меню, и справку там готовить незачем.
	 *
	 * <p>⚠️ Без этого флага панель показывала бы пояснение от чужого предмета:
	 * {@code ContainerSweepMixin} раз в секунду строит подсказки всех слотов,
	 * и последний из них затирал бы справку для того, на который игрок навёл.
	 */
	private static boolean sweeping;

	public static void sweeping(boolean value) {
		sweeping = value;
	}

	/**
	 * Отдаёт справку, если она приготовлена ДЛЯ ЭТОГО предмета.
	 *
	 * <p>Сверяем по ссылке, а не по имени: в меню бывают одинаковые вещи,
	 * а стек в слоте — тот же объект, что игра передала в построение подсказки.
	 */
	public static Panel panelFor(ItemStack hovered) {
		Panel ready = pending;
		if (ready == null || hovered == null || ready.stack() != hovered) {
			return null;
		}
		return ready;
	}

	/**
	 * Дописывает справку к подсказке предмета.
	 *
	 * <p>Без Shift показывается одна серая строка-приглашение: иначе о справке
	 * никто не узнает — невидимая возможность всё равно что отсутствующая.
	 * С Shift пояснение уходит в ОТДЕЛЬНОЕ окно сбоку ({@link WikiPanel}):
	 * дописанное вниз, оно сливалось с описанием вещи в один длинный столбец.
	 *
	 * @param stack предмет, чью подсказку строим; по нему панель узнает свою
	 * @param lines строки подсказки, куда дописываем
	 */
	public static void append(ItemStack stack, List<Component> lines) {
		if (!sweeping) {
			pending = null; // подсказка строится заново — старая справка не в счёт
		}
		// ⚠️ ОБЩИЙ ВЫКЛЮЧАТЕЛЬ ДЕЙСТВУЕТ И НА СПРАВКУ. Без этих ворот после
		// /skyblockru off подсказка оставалась английской, а под ней всё равно
		// висела русская строка-приглашение и открывалась русская панель.
		// Со стороны это выглядит как «мод не выключается» — та же беда, что
		// уже была с шапкой и подвалом таба. Оба вопроса задаём здесь же,
		// где остальные пути: TextTranslator и Paragraphs.apply.
		if (!RuConfig.get().enabled || !Hypixel.isActive()) {
			pending = null;
			return;
		}
		if ((TERMS.isEmpty() && ENCHANTS.isEmpty()) || !RuConfig.get().wikiHints
				|| lines.isEmpty()) {
			return;
		}
		// Какую справку спрашивают, решает КЛАВИША, а не содержимое предмета:
		// на дрели есть и характеристики, и зачарования сразу.
		boolean wantEnchants = Keys.down(Keys.ENCHANTS);
		Map<String, Entry> source = wantEnchants ? ENCHANTS : TERMS;
		// Ищем термин в ЧИСТОМ тексте: §-коды и цвет тут ни при чём.
		//
		// ⚠️ Строки склеиваем ПРОБЕЛОМ, а не переводом строки. Ширину подсказки
		// выбирает игрок, и Hypixel режет описание по ней, а не по смыслу:
		// «Даёт +50⛏ Farming / Fortune.» — термин разорван переносом. По тексту
		// с «\n» такой термин не найдётся никогда, и справка молча не появлялась
		// ровно там, где она нужнее всего — на длинных названиях.
		// ⚠️ ГРАНИЦЫ СТРОК ЗАПОМИНАЕМ ОТДЕЛЬНО. Склейка пробелом нужна (см. выше),
		// но вместе с переносом пропадает и граница — а слово из ЧУЖОЙ строки
		// начинало считаться продолжением имени характеристики:
		//
		//     Future Calories Talisman   <- имя предмета
		//     Tracking: +0.5             <- термин
		//     склеено: «…Calories Talisman Tracking: +0.5»
		//
		// «Talisman» с заглавной стоял слева от «Tracking», и справка молча
		// не появлялась. На предмете с коротким именем баг не воспроизводился,
		// поэтому пережил две попытки починки. Правило теперь смотрит влево
		// только в пределах СВОЕЙ строки (TermMatch.crossesLine).
		StringBuilder whole = new StringBuilder();
		java.util.List<Integer> starts = new ArrayList<>(lines.size());
		for (Component line : lines) {
			starts.add(whole.length());
			whole.append(LegacyText.strip(line.getString())).append(' ');
		}
		String text = whole.toString();
		lineStarts = starts;

		// ⚠️ NBT ЗДЕСЬ БОЛЬШЕ НЕ СПРАШИВАЕМ, и это не откат к догадке.
		//
		// Список зачарований из NBT выглядел надёжнее признака по форме, но
		// замер показал обратное: из 120 статей, реально стоящих в подсказках,
		// сервер подтверждает 113, а семь не кладёт вовсе — Gravity, Drain,
		// Prismatic, Dragon Tracer, Rainbow, Turbo-Crop, Woodsplitter. Справка
		// по ним молчала, и игрок сообщал об этом трижды.
		//
		// Проверено и обратное: 21 имя из справки встречается в форме «имя +
		// римский уровень» без подтверждения сервером, и ВСЕ 21 — настоящие
		// зачарования. Ложных срабатываний ноль, потому что перебираются имена
		// СТАТЕЙ, а коллекций и предметов («Melon Slice VII») среди них нет.
		// Отсекать было нечего — фильтр только терял.

		List<String> found = new ArrayList<>(2);
		for (String term : source.keySet()) {
			// ⚠️ Зачарование ищем ПО ФОРМЕ «имя + римский уровень», а термин —
			// по имени. Иначе зачарование «Chance» всплывает внутри любой
			// характеристики, кончающейся этим словом: Sea Creature Chance,
			// Treasure Chance, Double Hook Chance.
			// ⚠️ NBT-фильтр СНЯТ с поиска статей — он отсекал только хорошее.
			// Замер по живому дампу: 21 имя из справки стоит в форме «имя +
			// римский уровень» без подтверждения сервером, и все 21 — настоящие
			// зачарования (Gravity, Drain, Prismatic, Pyroclasm, Mana Pool…).
			// Ложных срабатываний ноль: фильтр перебирает имена СТАТЕЙ, а
			// коллекций среди них нет. Подробности — в TermMatch.showArticle.
			if (wantEnchants
					? TermMatch.showArticle(text, term)
					: mentions(text, term)) {
				found.add(term);
			}
		}
		dropSwallowed(found, text);
		// ⚠️ Для приглашения список берём ЗАНОВО: выше он читался только когда
		// зажат Alt, а приглашение показывается как раз без него.
		boolean enchantsHere = !ENCHANTS.isEmpty()
				&& hasEnchantArticle(text);

		if (found.isEmpty()) {
			// ⚠️ Приглашение показываем, только если справка ЕСТЬ хоть по чему-то
			// в этом предмете. Иначе строка «Alt — про зачарования» висела бы
			// на каждой вещи, включая те, где зачарований нет вовсе.
			if (!wantEnchants) {
				// ⚠️ ТЕРМИНОВ НЕТ — но зачарования могут быть, и раньше мы
				// выходили прямо здесь. На мече с двумя десятками зачарований
				// приглашение не показывалось ВООБЩЕ: терминов из справки
				// в нём нет («Урон», «Сила» и «Swing Range» туда пока не
				// попали), а до проверки Alt дело не доходило. Справка была,
				// а узнать о ней игрок не мог — то есть её как бы и не было.
				if (enchantsHere && !shiftDown()) {
					lines.add(Component.empty());
					lines.add(Component.literal(
									Keys.label(Keys.ENCHANTS) + " — зачарования")
							.withStyle(ChatFormatting.DARK_GRAY));
				}
				return;
			}
			source = TERMS;
			// ⚠️ ТОТ ЖЕ поиск, что и выше: `mentions` плюс отсев поглощённых.
			// Раньше здесь стоял голый `contains`, и запасной путь обходил
			// обе защиты разом — на наживке со строкой «Sea Creature Chance»
			// всплывала статья про зачарование «Chance», то есть совсем
			// про другое. Ветка редкая (нажат Alt, а зачарований нет),
			// поэтому и жила незамеченной.
			for (String term : source.keySet()) {
				if (mentions(text, term)) {
					found.add(term);
				}
			}
			dropSwallowed(found, text);
			if (found.isEmpty()) {
				return;
			}
		}

		if (!shiftDown() && !wantEnchants) {
			// ⚠️ Приглашение ОДНО на все предметы, без названия термина.
			// «что такое Overbloom» читается как вопрос про конкретное слово,
			// и на каждой вещи оно разное — глазу не за что зацепиться.
			// Постоянная строка на одном месте узнаётся сразу и не отвлекает.
			lines.add(Component.empty());
			// ⚠️ Клавиши называем ТЕКУЩИЕ, а не «Shift» и «Alt»: игрок мог их
			// переназначить, и приглашение звало бы не туда.
			String hint = Keys.label(Keys.WIKI) + " — подробности";
			if (enchantsHere) {
				hint += ", " + Keys.label(Keys.ENCHANTS) + " — зачарования";
			}
			lines.add(Component.literal(hint).withStyle(ChatFormatting.DARK_GRAY));
			return;
		}
		if (sweeping) {
			return; // обход слотов: подсказку никто не видит, панели не нужны
		}

		List<Component> article = new ArrayList<>();
		for (String term : found) {
			Entry entry = source.get(term);
			if (!article.isEmpty()) {
				// ⚠️ Разделитель взят У HYPIXEL, а не выдуман: в подсказках
				// аукциона он рисует ровно такую линию, и в живом дампе она
				// встречается 635 раз — 17 дефисов. Пустой строки между
				// статьями не хватало: два определения читались как одно.
				article.add(Component.empty());
				article.add(Component.literal(SEPARATOR)
						.withStyle(ChatFormatting.DARK_GRAY));
			}
			// ⚠️ Жирным — только английский термин. Кириллица в жирном шрифте
			// Minecraft слипается, «шахтёра» читается плохо. Дочерний компонент
			// НАСЛЕДУЕТ стиль родителя, поэтому bold(false) ставим явно —
			// одного withStyle(цвет) для этого мало.
			article.add(Component.literal(term)
					.withStyle(style -> style.withColor(termColor(entry))
							.withBold(true))
					.append(Component.literal(
							entry.title().isEmpty() ? "" : " — " + entry.title())
							.withStyle(style -> style.withColor(termColor(entry))
									.withBold(false))));
			for (String line : entry.lines()) {
				// ⚠️ Строку разбираем как есть, с §-кодами: справка красится
				// сама, а не заливается одним серым. Термин, число и название
				// культуры игрок должен видеть так же, как в самой игре, —
				// иначе пояснение читается хуже описания, которое оно поясняет.
				article.add(LegacyText.parse(line, net.minecraft.network.chat.Style.EMPTY
						.withColor(ChatFormatting.GRAY)));
			}
		}
		pending = new Panel(stack, article, contentWidth(lines), contentHeight(lines));
	}

	/**
	 * Цвет заголовка статьи — тот, каким Hypixel красит термин в игре.
	 *
	 * <p>Игрок ищет глазами ТО ЖЕ слово ТОГО ЖЕ цвета: если в описании
	 * «Mining Fortune» золотой, а в справке жёлтый, это читается как другой
	 * термин. Цвет объявляет сама статья полем {@code color}; не объявила —
	 * остаётся жёлтый, как было.
	 */
	private static ChatFormatting termColor(Entry entry) {
		if (entry.color().isEmpty()) {
			return ChatFormatting.YELLOW;
		}
		try {
			// ⚠️ В 26.2 у ChatFormatting нет ни getByName, ни isColor (проверено
			// javap) — остаётся valueOf, а модификаторы отсеиваем списком.
			ChatFormatting named = ChatFormatting.valueOf(
					entry.color().toUpperCase(java.util.Locale.ROOT));
			return NOT_COLORS.contains(named) ? ChatFormatting.YELLOW : named;
		} catch (IllegalArgumentException ignored) {
			return ChatFormatting.YELLOW; // опечатка в статье — не повод падать
		}
	}

	/** Это модификаторы, а не цвета: заголовку они не подходят. */
	private static final java.util.Set<ChatFormatting> NOT_COLORS = java.util.Set.of(
			ChatFormatting.OBFUSCATED, ChatFormatting.BOLD, ChatFormatting.STRIKETHROUGH,
			ChatFormatting.UNDERLINE, ChatFormatting.ITALIC, ChatFormatting.RESET);

	/**
	 * Ширина содержимого подсказки — самая длинная её строка.
	 *
	 * <p>Считаем ПОСЛЕ перевода и без нашей справки, то есть ровно то, что
	 * увидит игрок: панель прислоняется к настоящему краю окна, а не
	 * к предполагаемому.
	 */
	private static int contentWidth(List<Component> lines) {
		net.minecraft.client.Minecraft client = net.minecraft.client.Minecraft.getInstance();
		if (client == null || client.font == null) {
			return 0;
		}
		int width = 0;
		for (Component line : lines) {
			width = Math.max(width, client.font.width(line));
		}
		return width;
	}

	/**
	 * Высота содержимого подсказки по ванильному счёту.
	 *
	 * <p>Строка текста занимает 10 пикселей, а у подсказки ровно из одной
	 * строки игра начинает счёт с −2 (проверено по байткоду
	 * {@code GuiGraphicsExtractor.tooltip}). Повторяем это, иначе панель
	 * встанет на пару пикселей мимо.
	 */
	private static int contentHeight(List<Component> lines) {
		return lines.size() * 10 + (lines.size() == 1 ? -2 : 0);
	}
}
