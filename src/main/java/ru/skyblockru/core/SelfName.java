package ru.skyblockru.core;

import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * Имя САМОГО игрока в собранной строке — заменяется на {@code {s}}.
 *
 * <p>Зачем. Hypixel обращается к игроку по нику прямо в тексте: «[NPC] Terry:
 * Ahoy, Player_1!», «Player_1's Museum». Мод обобщал только ник С РАНГОМ
 * («[MVP+] Ник») и подпись («Seller: Ник»), а голое имя в середине строки
 * оставалось как есть. Отсюда три беды сразу:
 * <ul>
 *   <li>запись бесполезна всем, кроме одного человека: у другого игрока там
 *       другой ник, и совпадения не будет НИКОГДА;</li>
 *   <li>строка уезжает с телеметрией вместе с ником — а это личные данные.
 *       Замер 07.08: 23 строки, все 23 уже ушли на сервер;</li>
 *   <li>она же попадает в очередь и просит денег за перевод чужого имени.</li>
 * </ul>
 *
 * <p>⚠️ ПРИЗНАК ЖЕЛЕЗНЫЙ, а не догадка по форме. Своё имя клиент знает точно
 * ({@code Minecraft.getUser().getName()}), поэтому тут нечего угадывать —
 * в отличие от чужих ников, которых мы ловим по СТРУКТУРЕ строки
 * ({@code tools/check_nicknames.py}). Это ровно тот случай, когда источник
 * отвечает на наш вопрос прямо.
 *
 * <p>⚠️ Обобщаем, а НЕ выбрасываем. «[NPC] Elizabeth: Hey {s}!» работает
 * у каждого игрока и никого не называет; в проекте так уже переведены
 * 79 реплик. Удалённая запись — потерянный перевод, который завтра купят
 * заново.
 *
 * <p>⚠️ ЦЕНА ОШИБКИ ЗДЕСЬ МАЛА, и это разрешает не осторожничать. Ключ дампа
 * управляет СБОРОМ, а не переводом: {@code Translator} ищет по сырой строке.
 * Значит игрок с ником-словом («Melon») получит мусорную запись в дампе,
 * но экран у него не изменится. Обратная сторона — молчание — стоит дороже:
 * ники всех игроков едут к нам.
 *
 * <p>Логика чистая, без Minecraft: её гоняет {@code tools/check_self_name.py}
 * настоящей Java и без игры. Место выбрано именно за это — в
 * {@link UnknownStrings} проверить правку было бы нечем.
 */
public final class SelfName {

	private SelfName() {
	}

	/** Ник Minecraft: 3–16 знаков, буквы, цифры, подчёркивание. */
	private static final Pattern VALID = Pattern.compile("^[A-Za-z0-9_]{3,16}$");

	/**
	 * Заменяет имя игрока на {@code {s}} везде, где оно стоит ОТДЕЛЬНЫМ словом.
	 *
	 * <p>Границей считается всё, кроме букв, цифр и подчёркивания, — то есть
	 * набора, из которого состоит сам ник. Поэтому «Ahoy, Player_1!» меняется,
	 * а «Player_12» при нике «Player_1» — нет: это другой человек.
	 *
	 * <p>Притяжательная форма отдаётся как есть: «Player_1's Museum» →
	 * «{s}'s Museum». Апостроф в набор ника не входит, значит граница на месте,
	 * а хвост «'s» остаётся частью английской фразы — переводчику он нужен.
	 *
	 * @param text текст со снятыми §-кодами
	 * @param self ник игрока; {@code null}, пустой или неправдоподобный — текст
	 *             возвращается нетронутым
	 */
	public static String mask(String text, String self) {
		if (text == null || text.isEmpty() || self == null) {
			return text;
		}
		String name = self.trim();
		// ⚠️ Неправдоподобное имя не подставляем ВОВСЕ. На раннем старте клиент
		// отдаёт пустую строку, а в offline-режиме имя бывает произвольным:
		// короткий обрывок вроде «a» вырезал бы куски настоящих слов.
		if (!VALID.matcher(name).matches()) {
			return text;
		}
		int at = indexOfWord(text, name);
		if (at < 0) {
			return text;
		}
		StringBuilder out = new StringBuilder(text.length());
		int from = 0;
		while (at >= 0) {
			out.append(text, from, at).append("{s}");
			from = at + name.length();
			at = indexOfWord(text, name, from);
		}
		return out.append(text, from, text.length()).toString();
	}

	/** Имя игрока стоит в строке отдельным словом? */
	public static boolean mentions(String text, String self) {
		return text != null && self != null && VALID.matcher(self.trim()).matches()
				&& indexOfWord(text, self.trim()) >= 0;
	}

	private static int indexOfWord(String text, String name) {
		return indexOfWord(text, name, 0);
	}

	/**
	 * Ищет имя как отдельное слово, начиная с {@code from}.
	 *
	 * <p>⚠️ Поиск ТОЧНЫЙ по регистру. Ник у Minecraft один и пишется всегда
	 * одинаково, а сравнение без регистра задевало бы больше обычных слов —
	 * лишняя вольность там, где источник даёт точный ответ.
	 */
	private static int indexOfWord(String text, String name, int from) {
		int at = text.indexOf(name, from);
		while (at >= 0) {
			boolean leftFree = at == 0 || !isNameChar(text.charAt(at - 1));
			int end = at + name.length();
			boolean rightFree = end >= text.length() || !isNameChar(text.charAt(end));
			if (leftFree && rightFree) {
				return at;
			}
			at = text.indexOf(name, at + 1);
		}
		return -1;
	}

	private static boolean isNameChar(char c) {
		return c == '_' || Character.isLetterOrDigit(c);
	}

	/** Точка входа для проверки без игры: {@code java SelfName ник строка}. */
	public static void main(String[] args) {
		if (args.length < 2) {
			System.err.println("usage: SelfName <self> <text>");
			System.exit(2);
		}
		System.out.println(mask(args[1], args[0]));
	}
}
