package ru.skyblockru.core;

/**
 * Сравнение версий мода — ЧИСТАЯ ЛОГИКА, без Minecraft.
 *
 * <p><b>Зачем отдельно.</b> В jar версия записана вместе с версией игры:
 * {@code 0.2.0+26.2}, а в манифесте обновлений лежит голая {@code 0.2.0} —
 * сборок несколько, и правая часть у них РАЗНАЯ ПО ПОСТРОЕНИЮ. Наивное
 * {@code equals} объявляло их разными модами, и игрок с самой свежей сборкой
 * видел «вышла версия 0.2.0» при установленной 0.2.0, да ещё и совет
 * скачать её вручную.
 *
 * <p>⚠️ Правило «сравнивать ЛЕВУЮ часть» записано в CLAUDE.md с того дня,
 * как в проекте появились версии. Наступили всё равно — потому что сравнение
 * писалось в другом месте и раньше, чем правило. Теперь оно живёт в одном
 * месте и проверяется без игры.
 */
public final class Versions {

	private Versions() {
	}

	/** Одна ли это версия мода: {@code 0.2.0+26.2} и {@code 0.2.0} — да. */
	public static boolean same(String left, String right) {
		return base(left).equals(base(right));
	}

	/** Версия без сборочного хвоста: {@code 0.2.0+26.2} -> {@code 0.2.0}. */
	public static String base(String version) {
		if (version == null) {
			return "";
		}
		int plus = version.indexOf('+');
		return (plus < 0 ? version : version.substring(0, plus)).trim();
	}

	/** Проверка без игры: {@code java Versions левая правая}. */
	public static void main(String[] args) {
		if (args.length >= 2) {
			System.out.println(same(args[0], args[1]) ? "SAME" : "DIFFERENT");
		}
	}
}
