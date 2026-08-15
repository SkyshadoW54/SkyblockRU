package ru.skyblockru.core;

import java.util.List;
import java.util.regex.Pattern;

/**
 * Предмет или кнопка меню — по БЛОКУ подсказки.
 *
 * <p>Зачем. Заголовок подсказки приходит одним и тем же источником
 * ({@code item_name}) и у настоящей вещи, и у кнопки меню: «Ant Shard»
 * и «Accept Offer» для приёмника неотличимы. А решения у них разные —
 * имя предмета мы не переводим (по нему ищут на аукционе), кнопку переводить
 * НАДО. Из-за этого 1465 строк очереди годами висели «непонятно чем»,
 * и разделить их было нечем: каталог предметов сервера отстаёт от контента
 * (из 1381 строки от игроков в нём нашлись ЧЕТЫРЕ).
 *
 * <p>Признак же есть, и он у Hypixel механический: <b>у вещи в подсказке
 * стоит строка редкости</b> — «COMMON», «LEGENDARY LEGGINGS», «a MYTHIC
 * HELMET a». У кнопки её не бывает. Замер по 9556 живым блокам: строка
 * редкости есть у 4756, то есть ровно у половины, и это похоже на правду —
 * меню в SkyBlock не меньше, чем вещей.
 *
 * <p>⚠️ Ошибаемся мы в БЕЗОПАСНУЮ сторону. Ванильный предмет («Anvil»)
 * строки редкости не имеет и будет назван кнопкой — то есть попадёт
 * в работу лишним. Обратная ошибка была бы дороже: спрятанная кнопка
 * становится невидимой для всех отчётов, а на этом проект уже терял
 * 1639 строк.
 *
 * <p>⚠️ Логика вынесена в отдельный класс НАРОЧНО: {@code UnknownStrings}
 * тянет Minecraft, и проверить признак без запуска игры было бы нечем.
 * Гоняется настоящей Java в {@code tools/check_titles.py}.
 */
public final class Titles {

	/**
	 * Строка редкости. Формы взяты из живого дампа, а не выдуманы:
	 * «COMMON», «COMMON RABBIT», «LEGENDARY LEGGINGS», «a MYTHIC HELMET a».
	 *
	 * <p>⚠️ Ведущее «a» — это не артикль, а МЕРЦАЮЩИЙ СИМВОЛ Hypixel:
	 * «§d§l§ka» рисуется бегущими глифами и выглядит звёздочкой. Дамп
	 * §-коды снимает, и от звёздочки остаётся голая буква — записанная
	 * грабля проекта. Поэтому её приходится пропускать явно.
	 */
	private static final Pattern RARITY = Pattern.compile(
			"^(?:a )?(COMMON|UNCOMMON|RARE|EPIC|LEGENDARY|MYTHIC|DIVINE|SPECIAL"
			+ "|VERY SPECIAL|SUPREME|ADMIN|ULTIMATE)\\b");

	private Titles() {
	}

	/** Есть ли в блоке подсказки строка редкости, то есть вещь ли это. */
	public static boolean hasRarity(List<String> lines) {
		if (lines == null) {
			return false;
		}
		for (String line : lines) {
			if (line != null && RARITY.matcher(line.trim()).find()) {
				return true;
			}
		}
		return false;
	}

	/**
	 * Заголовок кнопки меню — то, что стоит переводить.
	 *
	 * <p>Блок короче двух строк не считаем ничем: у него нет описания,
	 * а значит и признака. Так же поступает {@code recordTooltip}.
	 */
	public static boolean isMenuTitle(String title, List<String> lines) {
		return title != null && !title.isBlank()
				&& lines != null && lines.size() >= 2
				&& !hasRarity(lines);
	}
}
