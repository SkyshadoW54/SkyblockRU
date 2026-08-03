package ru.skyblockru.core;

import java.util.List;

/**
 * Поиск ТЕРМИНА в тексте подсказки — чистая логика, без Minecraft.
 *
 * <p><b>Зачем отдельный класс.</b> Правила жили внутри {@link Wiki}, который
 * завязан на Minecraft, и проверить их без игры было НЕЧЕМ. Из-за этого баг
 * со справкой для «Tracking» пережил две попытки починки: он воспроизводится
 * только на предмете, у которого имя кончается словом с заглавной, а на экране
 * это выглядит как «справка просто не появляется». Здесь логика проверяется
 * настоящей Java из {@code tools/check_wiki_terms.py}.
 *
 * <p><b>Главное правило.</b> Hypixel пишет имя характеристики с Заглавной,
 * а обычное слово со строчной. Значит слово с заглавной вплотную к термину —
 * продолжение имени: «Heat Resistance», «Sea Creature Chance». А «Mining Speed
 * with part installed» проверку проходит: дальше обычные слова.
 */
public final class TermMatch {

	private TermMatch() {
	}

	public static boolean isWordChar(char symbol) {
		return (symbol >= 'A' && symbol <= 'Z') || (symbol >= 'a' && symbol <= 'z');
	}

	/**
	 * Прошла ли между двумя позициями ГРАНИЦА СТРОКИ.
	 *
	 * <p>⚠️ Ради этого метода всё и затевалось. Строки подсказки склеиваются
	 * ПРОБЕЛОМ — иначе термин, разорванный переносом («Farming / Fortune»),
	 * не найдётся никогда. Но вместе с переносом пропадает и граница, и слово
	 * из ЧУЖОЙ строки начинает считаться частью имени:
	 *
	 * <pre>
	 * Future Calories Talisman     &lt;- имя предмета, первая строка
	 * Tracking: +0.5               &lt;- термин, вторая строка
	 * склеено: «Future Calories Talisman Tracking: +0.5»
	 *                              ^^^^^^^^ слева «Talisman» с заглавной
	 * </pre>
	 *
	 * Справка для «Tracking» молча не появлялась, и на предмете с коротким
	 * именем баг не воспроизводился. Границы строк передаются отдельно
	 * и обрывают взгляд влево.
	 */
	static boolean crossesLine(List<Integer> lineStarts, int from, int to) {
		if (lineStarts == null) {
			return false;
		}
		for (int start : lineStarts) {
			if (start > from && start <= to) {
				return true;
			}
		}
		return false;
	}

	/**
	 * Термин — лишь ЧАСТЬ более длинного имени характеристики?
	 *
	 * <p>⚠️ Это третий подход к одной беде, и первые два были заплатками.
	 * «Chance» всплывал внутри «Sea Creature Chance», «Heat» — внутри «Heat
	 * Resistance». Сперва я отсеивал короткий термин длинным ИЗ СПРАВКИ — но
	 * работает это, лишь когда длинный там есть: статьи «Treasure Chance» нет,
	 * и беда вернулась на следующем же предмете.
	 */
	public static boolean partOfLongerName(String text, int start, int end,
			List<Integer> lineStarts) {
		if (start >= 2 && text.charAt(start - 1) == ' ') {
			int before = start - 2;
			while (before >= 0 && isWordChar(text.charAt(before))) {
				before--;
			}
			char first = text.charAt(before + 1);
			// ⚠️ Слово из ДРУГОЙ строки частью имени быть не может: между ними
			// стоял перенос, который Hypixel поставил по смыслу, а не по ширине.
			boolean sameLine = !crossesLine(lineStarts, before + 1, start);
			if (sameLine && before + 1 < start - 1 && first >= 'A' && first <= 'Z') {
				return true;
			}
		}
		if (end + 1 < text.length() && text.charAt(end) == ' ') {
			char next = text.charAt(end + 1);
			// Справа граница строки значит то же самое: следующая строка —
			// новая мысль, а не продолжение имени.
			if (crossesLine(lineStarts, end, end + 1)) {
				return false;
			}
			return next >= 'A' && next <= 'Z';
		}
		return false;
	}

	/** Встречается ли термин как ЦЕЛОЕ слово и не внутри длинного имени. */
	public static boolean mentions(String text, String term, List<Integer> lineStarts) {
		int at = text.indexOf(term);
		while (at >= 0) {
			boolean leftOk = at == 0 || !isWordChar(text.charAt(at - 1));
			int after = at + term.length();
			boolean rightOk = after >= text.length() || !isWordChar(text.charAt(after));
			if (leftOk && rightOk && !partOfLongerName(text, at, after, lineStarts)) {
				return true;
			}
			at = text.indexOf(term, at + 1);
		}
		return false;
	}

	/**
	 * Встречается ли ЗАЧАРОВАНИЕ — то есть имя ВМЕСТЕ С РИМСКИМ УРОВНЕМ.
	 *
	 * <p>⚠️ Одного имени НЕДОСТАТОЧНО, и это стоило двух неверных починок.
	 * Зачарование «Chance» — обычное слово, оно сидит внутри характеристик
	 * «Sea Creature Chance», «Treasure Chance» и любых будущих. В подсказке
	 * Hypixel пишет зачарование только с уровнем: «Chance V», «Growth VI».
	 * У характеристики уровня не бывает никогда.
	 */
	public static boolean mentionsEnchant(String text, String name) {
		int at = text.indexOf(name);
		while (at >= 0) {
			boolean leftOk = at == 0 || !isWordChar(text.charAt(at - 1));
			int after = at + name.length();
			if (leftOk && hasRomanLevel(text, after)) {
				return true;
			}
			at = text.indexOf(name, at + 1);
		}
		return false;
	}

	/**
	 * Сервер признаёт это зачарование? Сверка имени статьи со списком из NBT.
	 *
	 * <p>⚠️ У УЛЬТИМАТИВНЫХ сервер добавляет префикс: в NBT лежит
	 * {@code ultimate_chimera}, а статья называется «Chimera». Прямая сверка
	 * не совпадала, и справка по Alt МОЛЧА не появлялась — на 20 статьях
	 * из 135: Chimera, Bank, Combo, Flash, Inferno, Legion, One For All,
	 * Soul Eater, Swarm, The One, Wisdom и других.
	 *
	 * <p>Про сам префикс в проекте было известно — он записан в CLAUDE.md
	 * про сверку списков с сервером («ultimate_chimera против нашего Chimera»).
	 * Но до справки правило не довели, и она отсекала статьи, которые есть.
	 *
	 * <p>⚠️ Пустой список значит «данных нет» (у большинства предметов NBT
	 * с зачарованиями не бывает), и тогда фильтр не применяется вовсе —
	 * иначе справка пропала бы там, где раньше показывалась.
	 */
	public static boolean serverKnows(java.util.Set<String> byServer, String bareTerm) {
		if (byServer == null || byServer.isEmpty()) {
			return true;
		}
		return byServer.contains(bareTerm) || byServer.contains("ultimate" + bareTerm);
	}

	/**
	 * Показывать ли статью справки по этому имени.
	 *
	 * <p>⚠️ NBT здесь ДОБАВЛЯЕТ уверенности, но НЕ отсекает. Раньше отсекал —
	 * и это было ошибкой, доказанной замером: из 120 статей, реально стоящих
	 * в подсказках, сервер подтверждает 113, а 7 не кладёт в NBT вовсе
	 * (Gravity, Drain, Prismatic, Dragon Tracer, Rainbow, Turbo-Crop,
	 * Woodsplitter). Справка по ним молчала.
	 *
	 * <p>Проверено, от чего фильтр защищал: в живом дампе 21 имя из справки
	 * встречается в форме «имя + римский уровень» без подтверждения сервера,
	 * и ВСЕ 21 — настоящие зачарования (Strong Vitality, Pyroclasm, Mana Pool,
	 * Veteran…). **Ложных срабатываний ноль.** Так и должно быть: фильтр
	 * перебирает имена СТАТЕЙ, а коллекций и предметов («Melon Slice VII»)
	 * среди них нет — отсекать было нечего.
	 *
	 * <p>Признак остаётся прежний и надёжный: имя ВМЕСТЕ С РИМСКИМ УРОВНЕМ.
	 * У характеристики уровня не бывает никогда.
	 *
	 * <p>⚠️ Это записанное правило проекта: «данные должны добавлять
	 * уверенности, а не отнимать её». Спроси, что будет там, где источник
	 * молчит, — здесь он молчит у семи зачарований из ста двадцати.
	 */
	public static boolean showArticle(String text, String name) {
		return mentionsEnchant(text, name);
	}

	/** Сразу за позицией стоит римский уровень («Growth VI»)? */
	public static boolean hasRomanLevel(String text, int from) {
		int at = from;
		while (at < text.length() && text.charAt(at) == ' ') {
			at++;
		}
		int digits = at;
		while (digits < text.length() && "IVXLC".indexOf(text.charAt(digits)) >= 0) {
			digits++;
		}
		if (digits == at || digits - at > 6) {
			return false;
		}
		at = digits;
		return at >= text.length() || !isWordChar(text.charAt(at));
	}
}
