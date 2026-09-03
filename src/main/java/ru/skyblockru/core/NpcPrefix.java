package ru.skyblockru.core;

import java.util.function.UnaryOperator;

/**
 * Имя говорящего в реплике NPC: «[NPC] Kat: …».
 *
 * <p>⚠️ ЗАЧЕМ ОТДЕЛЬНАЯ МЕХАНИКА, а не словарь. Реплики переведены целиком
 * и лежат в {@code 62-npc-dialogues} — 9322 записи, где имя стоит английским.
 * В полном режиме имя надо показать по-русски, но копия словаря с русскими
 * именами весила бы +1.7 МБ и уехала бы ВСЕМ, включая тех, кому режим
 * не нужен: словарь грузится выключенным, а качается всегда.
 *
 * <p>А подменить имя можно уже В ГОТОВОМ переводе: оно там стоит ДОСЛОВНО,
 * потому что имена мы не переводим. Одно место на все 9322 реплики.
 *
 * <p>⚠️ ТОЛЬКО ПРЕФИКС, до первого двоеточия. В теле реплики имя требует
 * ПАДЕЖА («Поговори с Кэт», а не «с Кэт»… именительный там неверен), а падеж
 * машинно не выводится — записанное правило проекта. В префиксе же имя стоит
 * в именительном всегда: это подпись говорящего.
 *
 * <p>Логика чистая, без Minecraft, — проверяется без игры
 * ({@code tools/check_npc_prefix.py}).
 */
public final class NpcPrefix {

	private static final String MARK = "[NPC] ";

	private NpcPrefix() {
	}

	/**
	 * Имя говорящего из ОРИГИНАЛА реплики, иначе {@code null}.
	 *
	 * <p>⚠️ Берём из оригинала, а не из перевода: в переводе перед именем
	 * стоят §-коды («§e[NPC] §cRyan§f: …»), и разбирать их незачем — имя
	 * оттуда всё равно совпадает дословно.
	 */
	public static String speakerOf(String source) {
		if (source == null) {
			return null;
		}
		int mark = source.indexOf(MARK);
		if (mark < 0) {
			return null;
		}
		int from = mark + MARK.length();
		int colon = source.indexOf(':', from);
		if (colon <= from) {
			return null;
		}
		String name = source.substring(from, colon).trim();
		if (name.isEmpty() || name.length() > 40) {
			return null;
		}
		// ⚠️ В подписи говорящего не бывает служебных знаков — если они есть,
		// это не реплика, а что-то другое, и трогать её нельзя.
		for (int i = 0; i < name.length(); i++) {
			char c = name.charAt(i);
			if (c == '[' || c == ']' || c == '{' || c == '}' || c == '\u00a7') {
				return null;
			}
		}
		return name;
	}

	/**
	 * Заменить имя говорящего в ПЕРЕВОДЕ на русское.
	 *
	 * @param source     оригинал реплики (оттуда берём имя)
	 * @param translated готовый перевод реплики
	 * @param russian    что словарь даёт для имени; {@code null} — оставить как есть
	 * @return перевод с русским именем либо он же без изменений
	 */
	public static String apply(String source, String translated,
	                           UnaryOperator<String> russian) {
		String name = speakerOf(source);
		if (name == null || translated == null) {
			return translated;
		}
		String ru = russian.apply(name);
		if (ru == null || ru.isBlank() || ru.equals(name)) {
			return translated;
		}
		// ⚠️ МЕНЯЕМ ТОЛЬКО ДО ПЕРВОГО ДВОЕТОЧИЯ. Дальше идёт тело реплики,
		// где то же имя требует падежа — там подмена дала бы «расскажи Кэт»
		// вместо «расскажи Кэт»… то есть именительный в косвенной позиции.
		int colon = translated.indexOf(':', headStart(translated));
		if (colon < 0) {
			return translated;
		}
		String head = translated.substring(0, colon);
		// ⚠️ §-КОДЫ РАЗРЫВАЮТ ИМЯ, и дословный поиск его не находит.
		// Hypixel красит куски по отдельности, поэтому в переводе стоит
		// «Melody §d♫», а не «Melody ♫». Записанная грабля проекта.
		int[] span = findIgnoringCodes(head, name);
		if (span == null) {
			return translated;          // имя переведено иначе — не трогаем
		}
		return head.substring(0, span[0]) + ru + head.substring(span[1])
				+ translated.substring(colon);
	}

	/**
	 * Где стоит {@code name} в {@code text}, если не считать §-коды.
	 *
	 * @return пара «начало, конец» в исходной строке либо {@code null}
	 */
	static int[] findIgnoringCodes(String text, String name) {
		for (int start = 0; start < text.length(); start++) {
			if (text.charAt(start) == '§') {
				start++;                    // сам код началом быть не может
				continue;
			}
			int i = start;
			int j = 0;
			while (i < text.length() && j < name.length()) {
				char c = text.charAt(i);
				if (c == '§' && i + 1 < text.length()) {
					i += 2;
					continue;
				}
				if (c != name.charAt(j)) {
					break;
				}
				i++;
				j++;
			}
			if (j == name.length()) {
				return new int[] { start, i };
			}
		}
		return null;
	}

	/** С какого места искать двоеточие подписи. */
	private static int headStart(String translated) {
		int mark = translated.indexOf(MARK);
		return mark < 0 ? 0 : mark + MARK.length();
	}
}
