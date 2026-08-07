package ru.skyblockru.core;

import java.util.regex.Pattern;

/**
 * Текст ЧУЖОГО МОДА — не наше дело: ни переводить, ни собирать, ни отправлять.
 *
 * <p><b>Зачем.</b> У игрока рядом с нами стоят SkyHanni, Skyblocker, Odin
 * и десятки других. Они пишут в чат, рисуют свои экраны и дописывают текст
 * прямо в подсказку предмета — а наши точки перехвата ванильные, значит всё
 * это проходит через нас наравне с текстом Hypixel:
 *
 * <pre>
 * [SkyHanni] +5 SkyBlock XP (Collections) (3/10)
 * (From SkyHanni)                    &lt;- приписка соседа к ПРЕДМЕТУ
 * block.skyhanni.opaque_water        &lt;- ключ локализации чужого мода
 * Odin Update Available              &lt;- заголовок на пол-экрана
 * </pre>
 *
 * <p>Переводить это нельзя по трём причинам, и каждая достаточна:
 * <ul>
 *   <li>сосед обновляется еженедельно, строки меняются — перевод отвалится
 *       МОЛЧА, и человек решит, что сломался наш мод;</li>
 *   <li>покрытие вышло бы случайным: часть чужого мода по-русски, часть нет —
 *       это читается как поломка;</li>
 *   <li>соседи ЧИТАЮТ свой текст обратно (SkyHanni разбирает чат и панель).
 *       Подменив текст, мы ломаем не надпись, а их работу.</li>
 * </ul>
 *
 * <p>⚠️ ОДИН признак на все пути. Раньше он жил приватным полем в
 * {@link TelemetryFilter}, то есть закрывал только отправку: перевод и сбор
 * чужие строки пропускали. Копии признака в этом проекте расходились трижды,
 * поэтому место у него теперь одно, а потребителей несколько.
 *
 * <p>⚠️ Имена ищем ПО ГРАНИЦЕ СЛОВА, а не подстрокой: «Odin» сидит внутри
 * «expl<b>odin</b>g», и в живом дампе таких строк четыре («Exploding Frog»,
 * «and exploding for {n} damage»).
 *
 * <p>⚠️ Список НЕ полон и полным не будет — модов сотни. Поэтому вторая линия
 * это техномусор (стектрейс, исключение), по которому чужой мод виден
 * независимо от имени, а третья — порог «строку прислали МНОГИЕ» на нашей
 * стороне при разборе.
 *
 * <p>Замер 08.08 по всем дампам: признак задевает 2 строки, и обе — настоящие
 * сообщения соседей. В наших словарях и очереди — 0 задетых, то есть готовый
 * перевод он не гасит.
 */
public final class ForeignMods {

	private ForeignMods() {
	}

	private static final Pattern FOREIGN = Pattern.compile(
			"\\b(?:SkyHanni|Skyblocker|NotEnoughUpdates|Firmament|Odin|Devonian"
			+ "|ModMenu|Sodium|Lithium|FerriteCore)\\b"
			+ "|\\bat\\.[a-z0-9_]+\\.[a-z0-9_.]+"
			+ "|\\w*Exception\\b|\\bError while\\b|\\bstacktrace\\b",
			Pattern.CASE_INSENSITIVE);

	/** Похоже ли, что строку написал не Hypixel, а сосед по папке модов. */
	public static boolean looksForeign(String line) {
		return line != null && !line.isEmpty() && FOREIGN.matcher(line).find();
	}

	/**
	 * Точка входа для проверки без игры: {@code java ForeignMods строка}.
	 *
	 * <p>Без аргументов читает строки со стандартного ввода — по одной,
	 * ответ на каждую своей строкой. ⚠️ Так сделано нарочно: сторож проверяет
	 * признак на ЖИВОМ дампе, а это 28 тысяч строк, и запуск отдельной JVM
	 * на каждую занимал минуты вместо секунды.
	 */
	public static void main(String[] args) throws java.io.IOException {
		if (args.length >= 1) {
			System.out.println(looksForeign(args[0]) ? "FOREIGN" : "OURS");
			return;
		}
		java.io.BufferedReader in = new java.io.BufferedReader(
				new java.io.InputStreamReader(System.in, java.nio.charset.StandardCharsets.UTF_8));
		StringBuilder out = new StringBuilder();
		for (String line = in.readLine(); line != null; line = in.readLine()) {
			out.append(looksForeign(line) ? "FOREIGN" : "OURS").append('\n');
		}
		System.out.print(out);
	}
}
