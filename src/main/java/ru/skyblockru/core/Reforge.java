package ru.skyblockru.core;

import java.util.Locale;
import java.util.function.Function;

/**
 * Название перекованной вещи: «Fortunate Lapis Pickaxe» → «Удачливая
 * лазуритовая кирка».
 *
 * <p><b>Зачем отдельная механика.</b> Перековка — это ПРЕФИКС к имени, и пар
 * «перековка + предмет» столько, что перечислить их нельзя: 148 перековок
 * на 5162 имени. Замер по строкам от игроков: заголовков вида «префикс + имя»
 * <b>11 029</b>, то есть БОЛЬШЕ, чем обычных имён (6545), и у 9512 из них
 * перевод основы уже куплен — он просто не доставался, потому что в словаре
 * лежит «Lapis Pickaxe», а сервер шлёт «Fortunate Lapis Pickaxe».
 *
 * <p><b>Почему не правилом.</b> Решение игрока 22.08: правила «не совсем
 * точные и могут сломаться». Здесь оно было бы вдвойне опасно — правило
 * по форме («первое слово + остаток») режет и обычные имена, у которых
 * первое слово частью имени и является («Ancient Necron's Chestplate»).
 *
 * <p><b>На чём стоим вместо догадки.</b> Сервер сам говорит, перекована ли
 * вещь: в NBT лежит {@code modifier} ({@link Items#modifierOf}). Пусто —
 * не режем вовсе. А написание префикса берём ИЗ САМОГО НАЗВАНИЯ, поэтому
 * сверять ключ NBT с текстом не нужно: у «Fortunate Lapis Pickaxe» перековка
 * написана ровно там, где её читает игрок.
 *
 * <p>Вторая защита — словарь: остаток обязан найтись как ИМЯ ПРЕДМЕТА.
 * Не нашёлся — возвращаем {@code null}, и имя остаётся английским. Так
 * перековка, не дающая префикса ({@code aote_stone}), ничего не ломает.
 */
public final class Reforge {

	/** Род перевода: по нему выбирается форма префикса. */
	public enum Gender {
		MASCULINE, FEMININE, NEUTER, PLURAL
	}

	private Reforge() {
	}

	/**
	 * Собрать перевод названия перекованной вещи.
	 *
	 * <p>Чистая функция: ни Minecraft, ни статики — поэтому её гоняет
	 * {@code check_reforges.py} настоящей Java без запуска игры.
	 *
	 * @param title    название целиком, как прислал сервер
	 * @param reforged сказал ли NBT, что вещь перекована
	 * @param names    перевод имени предмета либо {@code null}
	 * @param reforges формы перековки по её английскому написанию либо {@code null}
	 * @param genders  заданный род слова ({@code m|f|n|p}) либо {@code null}
	 * @return собранное название либо {@code null}, если собирать не из чего
	 */
	public static String compose(String title, boolean reforged,
			Function<String, String> names,
			Function<String, String[]> reforges,
			Function<String, String> genders) {
		if (title == null) {
			return null;
		}
		// ⚠️ ХВОСТ ПРОКАЧКИ СНИМАЕМ ПЕРВЫМ ДЕЛОМ. Сервер дописывает к имени
		// звёзды и мастер-звёзды («Heroic Hyperion ✪✪✪✪✪➎»), и в словаре
		// такого ключа нет и быть не может: вариантов прокачки у одной вещи
		// десятки. Замер по строкам от игроков: 4451 разное имя, 62 840
		// показов — это крупнейшая семья непереведённого.
		String tail = tailOf(title);
		String head = title.substring(0, title.length() - tail.length()).stripTrailing();
		String body = composeBody(head, reforged, names, reforges, genders);
		if (body != null) {
			return tail.isEmpty() ? body : body + tail;
		}
		// ⚠️ ВЕДУЩИЙ ЗНАЧОК СНИМАЕМ ТАК ЖЕ, КАК ХВОСТ, и это не мелочь.
		// Hypixel помечает часть вещей значком ПЕРЕД именем («✿ Ancient
		// Maxor's Boots ✪✪✪✪✪»), и такого ключа в словаре нет: значок зависит
		// от косметики, а не от вещи. Хвост мы снимали, а начало — нет,
		// и всё помеченное оставалось английским целиком.
		//
		// Замер 23.08 по строкам от игроков: 1501 имя с ведущим значком,
		// из них 1229 переводятся сразу, как только значок снят.
		//
		// ⚠️ Пробуем это ВТОРЫМ заходом, а не первым. Сперва имя ищется целиком:
		// если словарь знает его вместе со значком, ничего снимать не надо.
		// Так правка не может подменить уже работающий перевод.
		String lead = leadOf(head);
		if (lead.isEmpty()) {
			return null;
		}
		String bare = head.substring(lead.length());
		String inner = composeBody(bare, reforged, names, reforges, genders);
		if (inner == null) {
			return null;
		}
		return lead + inner + tail;
	}

	/**
	 * Ведущий значок имени: «✿ Ancient Maxor's Boots» -> «✿ ».
	 *
	 * <p>⚠️ ПРИЗНАК, А НЕ СПИСОК. Сперва тут был перечень увиденных значков —
	 * и он отстал от первой же новой вещи: у самоцветов значок свой на каждый
	 * тип («☂ Perfect Aquamarine Gemstone», «✎ Fine Sapphire Gemstone»),
	 * у метки рецепта третий («✖ Coal Minion I»), у реликвии четвёртый («⚚»).
	 * Замер 23.08: список закрывал 1229 имён, признак — на 179 больше,
	 * и все 179 просмотрены глазами, ложных нет.
	 *
	 * <p>Широким его делать безопасно ровно потому, что снятие ничего
	 * не решает само: остаток обязан найтись в словаре, иначе compose
	 * возвращает null и имя остаётся английским.
	 *
	 * <p>⚠️ Значок обязан отделяться ПРОБЕЛОМ. Без этого признак съел бы
	 * начало имени у вещей, где значок и есть первая буква названия, —
	 * а такие у Hypixel бывают.
	 */
	static String leadOf(String title) {
		int at = 0;
		while (at < title.length() && isLeadMark(title.charAt(at))) {
			at++;
		}
		if (at == 0) {
			return "";
		}
		int end = at;
		while (end < title.length() && title.charAt(end) == ' ') {
			end++;
		}
		return end > at ? title.substring(0, end) : "";
	}

	private static boolean isLeadMark(char ch) {
		return !Character.isLetterOrDigit(ch) && ch != ' ';
	}

	/**
	 * Хвост прокачки в конце имени: звёзды, мастер-звёзды, знак ковки.
	 *
	 * <p>Набор взят ИЗ ЖИВЫХ строк, а не выдуман: U+272A встретился 20 165 раз,
	 * U+2726 — 323, мастер-звёзды U+278A…U+2793 идут следом за ними.
	 */
	static String tailOf(String title) {
		int end = title.length();
		int at = end;
		while (at > 0) {
			char ch = title.charAt(at - 1);
			if (ch == ' ' || isUpgradeMark(ch)) {
				at--;
				continue;
			}
			break;
		}
		// Хвостом считаем только то, где есть хоть один ЗНАК прокачки:
		// иначе мы срезали бы обычные пробелы и звали это хвостом.
		String tail = title.substring(at);
		for (int i = 0; i < tail.length(); i++) {
			if (isUpgradeMark(tail.charAt(i))) {
				return tail;
			}
		}
		return "";
	}

	private static boolean isUpgradeMark(char ch) {
		return ch == '✪' || ch == '✦' || (ch >= '➊' && ch <= '➓');
	}

	private static String composeBody(String title, boolean reforged,
			Function<String, String> names,
			Function<String, String[]> reforges,
			Function<String, String> genders) {
		// Без перековки собирать нечего — но имя могло стать переводимым
		// после снятия хвоста, и тогда его берёт обычный словарь.
		if (!reforged) {
			String plain = names.apply(title);
			return plain == null || plain.isBlank() ? null : plain;
		}
		int space = title.indexOf(' ');
		if (space <= 0 || space + 1 >= title.length()) {
			String plain = names.apply(title);
			return plain == null || plain.isBlank() ? null : plain;
		}
		String prefix = title.substring(0, space);
		String base = title.substring(space + 1);

		String[] forms = reforges.apply(prefix);
		if (forms == null || forms.length != 4) {
			// Первое слово перековкой не значится — значит это часть имени.
			// Тогда вещь перекована чем-то, что префикса не даёт, и имя надо
			// искать целиком.
			String plain = names.apply(title);
			return plain == null || plain.isBlank() ? null : plain;
		}
		// ⚠️ Без перевода основы собирать нечего: «Удачливая Lapis Pickaxe» —
		// это смесь языков, а она хуже целиком английского названия.
		String baseRu = names.apply(base);
		if (baseRu == null || baseRu.isBlank()) {
			// Основы в словаре нет — но, может, всё имя целиком есть.
			String plain = names.apply(title);
			return plain == null || plain.isBlank() ? null : plain;
		}
		return forms[genderOf(baseRu, genders).ordinal()] + " " + lower(baseRu);
	}

	/**
	 * Род русского названия — по его ПЕРВОМУ слову.
	 *
	 * <p>Первое слово выбрано не случайно: в наших переводах оно и есть
	 * главное («Лазуритовая кирка», «Ботинки убийцы теней»), а согласовать
	 * префикс надо именно с ним. Замер по 5162 готовым переводам: однозначно
	 * определяется 4724 — прилагательное впереди снимает почти всю
	 * неоднозначность, потому что у него род виден по окончанию.
	 *
	 * <p>⚠️ Мягкий знак рода НЕ ВЫДАЁТ: «дрель» женского, «трюфель» мужского.
	 * Гадать тут нельзя, поэтому такие слова перечислены явно в словаре
	 * (секция {@code genders}) — ровно как двойственные имена в защите.
	 * Спрашиваем список ПЕРВЫМ: он знает то, чего окончание не скажет.
	 */
	public static Gender genderOf(String russian, Function<String, String> genders) {
		String first = firstWord(russian);
		if (first.isEmpty()) {
			return Gender.MASCULINE;
		}
		if (genders != null) {
			Gender set = named(genders.apply(first));
			if (set != null) {
				return set;
			}
		}
		// Прилагательное впереди — самый надёжный признак: род у него в окончании.
		if (first.endsWith("ый") || first.endsWith("ий") || first.endsWith("ой")) {
			return Gender.MASCULINE;
		}
		if (first.endsWith("ая") || first.endsWith("яя")) {
			return Gender.FEMININE;
		}
		if (first.endsWith("ое") || first.endsWith("ее")) {
			return Gender.NEUTER;
		}
		if (first.endsWith("ые") || first.endsWith("ие")) {
			return Gender.PLURAL;
		}
		// Существительное: окончание тоже говорит о роде, но слабее.
		if (first.endsWith("ы") || first.endsWith("и")) {
			return Gender.PLURAL;
		}
		if (first.endsWith("а") || first.endsWith("я")) {
			return Gender.FEMININE;
		}
		if (first.endsWith("о") || first.endsWith("е") || first.endsWith("ё")) {
			return Gender.NEUTER;
		}
		return Gender.MASCULINE;
	}

	private static Gender named(String mark) {
		if (mark == null || mark.isEmpty()) {
			return null;
		}
		switch (mark.charAt(0)) {
			case 'f':
				return Gender.FEMININE;
			case 'n':
				return Gender.NEUTER;
			case 'p':
				return Gender.PLURAL;
			case 'm':
				return Gender.MASCULINE;
			default:
				return null;
		}
	}

	private static String firstWord(String text) {
		String clean = text.trim();
		int space = clean.indexOf(' ');
		String word = space > 0 ? clean.substring(0, space) : clean;
		return word.toLowerCase(Locale.ROOT);
	}

	/**
	 * Название после префикса пишется со строчной: «Свирепая <b>к</b>ираса
	 * Некрона». Понижается ТОЛЬКО первая буква — имя внутри («Некрона»)
	 * остаётся с заглавной, потому что это имя собственное.
	 */
	private static String lower(String text) {
		if (text.isEmpty()) {
			return text;
		}
		char head = text.charAt(0);
		char small = Character.toLowerCase(head);
		return small == head ? text : small + text.substring(1);
	}
}
