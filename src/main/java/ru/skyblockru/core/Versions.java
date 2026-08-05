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

	/**
	 * СТРОГО ли {@code candidate} новее, чем {@code current}.
	 *
	 * <p>⚠️ Раньше мод сообщал о «новой версии» при ЛЮБОМ расхождении — то есть
	 * и тогда, когда у игрока сборка СВЕЖЕЕ выложенной. Так и вышло: в чате
	 * висело «Вышла версия мода 0.2.5» у человека с 0.2.6, да ещё и с советом
	 * скачать её вручную. Совет вредный: он предлагает откатиться назад.
	 *
	 * <p>Сравниваем по числам, а не по строкам: «0.2.10» новее «0.2.9», хотя
	 * по алфавиту наоборот. Часть, которая не разбирается в число, считается
	 * нулём — и при полном равенстве чисел новее не объявляем. Молчать
	 * безопаснее, чем звать на обновление впустую.
	 */
	public static boolean newer(String candidate, String current) {
		String[] left = base(candidate).split("\\.");
		String[] right = base(current).split("\\.");
		int size = Math.max(left.length, right.length);
		for (int i = 0; i < size; i++) {
			int a = number(i < left.length ? left[i] : "");
			int b = number(i < right.length ? right[i] : "");
			if (a != b) {
				return a > b;
			}
		}
		return false;
	}

	/** Ведущее число части версии: «2», «0», «3rc1» -> 3. Нет цифр — ноль. */
	private static int number(String part) {
		int at = 0;
		while (at < part.length() && Character.isDigit(part.charAt(at))) {
			at++;
		}
		if (at == 0) {
			return 0;
		}
		try {
			return Integer.parseInt(part.substring(0, at));
		} catch (NumberFormatException broken) {
			return 0;
		}
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
