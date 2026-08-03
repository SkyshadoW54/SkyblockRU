package ru.skyblockru.core;

import java.util.Locale;
import java.util.Set;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * Что можно отправлять на сервер перевода — ЧИСТАЯ ЛОГИКА, без Minecraft.
 *
 * <p><b>Зачем отдельным классом.</b> Пока признак сидел внутри {@code Telemetry},
 * проверить его было нечем: тот класс тянет {@code Minecraft} и в одиночку
 * не компилируется. А ошибиться здесь дороже, чем где-либо ещё в проекте —
 * промах означает не кривой перевод, а чужую переписку на сервере.
 * Теперь его гоняет {@code tools/check_telemetry.py} настоящей Java,
 * на живом дампе и с подсадкой заведомых случаев.
 *
 * <p>⚠️ Мусор (ники, номера серверов, даты панели) сюда не доходит:
 * его отсекает {@link UnknownStrings#isNoise} ещё при сборе. Здесь снимается
 * только то, что касается ДРУГИХ ЛЮДЕЙ.
 */
public final class TelemetryFilter {

	/**
	 * Реплика игрока: на SkyBlock перед ником всегда стоит метка уровня.
	 *
	 * <p>⚠️ Признак от СТРУКТУРЫ, а не список рангов. Вычищать ники перебором
	 * форматов — тупик: у игроков разные ранги ({@code MVP+}, {@code MVP++}),
	 * значки ({@code ᛝ}, {@code ꤥ}) и цвета, и все они стоят ПОСЛЕ метки.
	 * Замер на живом дампе: отсекает ровно 9 строк из 1465, и все девять —
	 * настоящие реплики игроков.
	 */
	private static final Pattern PLAYER_LINE =
			Pattern.compile("^\\[(?:\\{n}|\\d+)]\\s*\\S+.*:");

	/**
	 * Личные и групповые каналы.
	 *
	 * <p>⚠️ Замер по живому дампу (1465 строк чата) не нашёл НИ ОДНОЙ такой
	 * строки. Признак стоит страховкой: появится формат — узнать об этом
	 * задним числом будет неоткуда, данные уже уйдут.
	 */
	private static final Pattern PRIVATE_LINE =
			Pattern.compile("^(?:Party|Guild|Co-op|Officer)\\s*>|^To\\s+\\S+\\s*:");

	/** Личное входящее — но только если пишет ЧЕЛОВЕК, см. {@link #SYSTEM_SENDERS}. */
	private static final Pattern FROM_LINE = Pattern.compile("^From\\s+(\\S+)\\s*:");

	/**
	 * «Отправители», которые на самом деле сервер.
	 *
	 * <p>⚠️ Без этого списка наивный фильтр «всё, что начинается с From X:»
	 * выбросил бы {@code From stash: Dark Oak Log} — выдачу из хранилища,
	 * то есть ПОЛЕЗНУЮ системную строку. Поймано замером по живому дампу:
	 * из трёх совпадений «From» все три оказались этим.
	 */
	private static final Set<String> SYSTEM_SENDERS = Set.of("stash", "storage", "sacks");

	/** Слишком длинная строка — не текст интерфейса, а чей-то простыня-разговор. */
	private static final int MAX_LENGTH = 500;

	private TelemetryFilter() {
	}

	/** Отправлять ли эту строку. */
	public static boolean worthSending(String source, String line) {
		if (line == null || line.isBlank() || line.length() > MAX_LENGTH) {
			return false;
		}
		if (!"chat".equals(source)) {
			return true;
		}
		if (PLAYER_LINE.matcher(line).find() || PRIVATE_LINE.matcher(line).find()) {
			return false;
		}
		Matcher from = FROM_LINE.matcher(line);
		if (from.find()) {
			return SYSTEM_SENDERS.contains(from.group(1).toLowerCase(Locale.ROOT));
		}
		return true;
	}

	/** Точка входа для проверки без игры: {@code java TelemetryFilter источник строка}. */
	public static void main(String[] args) {
		if (args.length >= 2) {
			System.out.println(worthSending(args[0], args[1]) ? "SEND" : "SKIP");
		}
	}
}
