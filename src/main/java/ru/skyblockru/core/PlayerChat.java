package ru.skyblockru.core;

import java.util.regex.Pattern;

/**
 * Отличает написанное живым игроком от текста сервера.
 *
 * <p>Сообщения игроков не переводим и не собираем. Причины обе весомые:
 * это их собственные слова, которые подменять нельзя, и это чужая переписка,
 * которую незачем хранить — особенно если мод будет собирать данные у других.
 *
 * <p>Различаем по <b>скобочной метке перед ником</b>: на SkyBlock у игрока
 * всегда есть хотя бы уровень — «[128] Ник: текст», «[61] [VIP] Ник: текст».
 * У служебных строк такой метки нет, поэтому «Objective: Talk to the Bartender»
 * и «Fuel Tank: Not Installed» проверку не проходят и переводятся как обычно.
 *
 * <p>Реплики NPC («[NPC] Clerk Seraphine: ...») внешне устроены так же,
 * но это текст сервера, и переводить его как раз надо.
 */
public final class PlayerChat {

	private static final Pattern MESSAGE =
			Pattern.compile("^(?:\\[[^\\]]{1,24}\\]\\s*[^\\w\\s]*\\s*)+[A-Za-z0-9_]{3,16}:\\s.*");

	private static final Pattern NPC = Pattern.compile("^\\[NPC\\]\\s.*");

	private PlayerChat() {
	}

	/** Написано живым игроком? Реплики NPC сюда не попадают. */
	public static boolean isPlayerMessage(String text) {
		if (text == null || text.length() < 6) {
			return false;
		}
		if (NPC.matcher(text).matches()) {
			return false;
		}
		return MESSAGE.matcher(stripBadges(text)).matches();
	}

	/**
	 * Убрать ЗНАЧКИ между меткой и ником: «[128] ᛝ Ник:» -> «[128] Ник:».
	 *
	 * <p>⚠️ Признак «не буква» тут НЕПОЛНЫЙ, и это уже записанная грабля —
	 * просто вылезшая в новом месте. Hypixel берёт под значки буквы чужих
	 * алфавитов: «ᛝ» — руническая, для Java это БУКВА, и класс {@code [^\w\s]}
	 * её не снимает. Из-за этого сообщение игрока
	 * «[128] ᛝ Ник: текст» проверку не проходило и попадало и в перевод,
	 * и в сбор — то есть чужая переписка складывалась в дамп.
	 * Замер по живому дампу: из 1465 строк чата признак опознал игроком НОЛЬ,
	 * хотя такие сообщения там есть.
	 *
	 * <p>Тот же признак уже выведен и проверен в {@code Paragraphs.isMarkerChar}
	 * (значки удочки «ථ», «ꨃ», «࿉»): буква считается значком, если её алфавит
	 * не латиница, не кириллица и не COMMON. Правило одно — держим его так же.
	 */
	private static String stripBadges(String text) {
		StringBuilder out = new StringBuilder(text.length());
		for (int i = 0; i < text.length(); i++) {
			char symbol = text.charAt(i);
			if (isBadge(symbol)) {
				continue;
			}
			out.append(symbol);
		}
		return out.toString();
	}

	private static boolean isBadge(char symbol) {
		if (!Character.isLetter(symbol)) {
			return false;
		}
		Character.UnicodeScript script = Character.UnicodeScript.of(symbol);
		return script != Character.UnicodeScript.LATIN
				&& script != Character.UnicodeScript.CYRILLIC
				&& script != Character.UnicodeScript.COMMON;
	}
}
