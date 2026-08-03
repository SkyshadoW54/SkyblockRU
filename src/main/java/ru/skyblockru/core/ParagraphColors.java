package ru.skyblockru.core;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

/**
 * Раздача ЦВЕТОВ кускам переведённого абзаца — без Minecraft, а значит проверяемо.
 *
 * <p><b>Зачем.</b> Перенос абзаца ({@link Paragraphs#wrap}) красил ВСЕ получившиеся
 * строки ведущим цветом ПЕРВОЙ строки. У одноцветной прозы это незаметно, а у
 * подсказки питомца выходило так:
 *
 * <pre>
 * было:  §bSharp Attitude
 *        §7Sea Creatures spawn with §e10%§7 of
 *        §7their maximum health missing.
 * стало: §bSharp Attitude Морские существа появляются, потеряв 10% своего…
 * </pre>
 *
 * Весь абзац — одного цвета, подсветка чисел и терминов пропала, заголовок слился
 * с прозой. Со стороны это выглядит как «перевели процентов шестьдесят».
 *
 * <p><b>Как чиним.</b> То, что осталось в переводе ДОСЛОВНО — число, процент,
 * английское имя («Sharp Attitude», «GOLD», «Trophy Fish»), — это перенесённый
 * кусок оригинала, и его цвет мы знаем. Такие куски красим как в оригинале,
 * остальное — цветом ТЕЛА абзаца, а не первой строки. Приём не новый: ровно так
 * {@code TextTranslator.restyleFromSource} уже спасает одиночные строки. Здесь
 * он вынесен в чистую логику, потому что абзац — место, где ошибка стоит дороже
 * всего: она меняет сразу несколько строк на экране.
 *
 * <p><b>Почему отдельный класс.</b> Та же причина, что у {@link ColorLayout}:
 * решение по цветам нельзя было проверить ничем, кроме живой игры, — дамп
 * §-коды снимает. Класс не знает про Minecraft (цвет — просто строка), поэтому
 * его гоняет {@code tools/check_paragraph_colors.py} на раскладках, записанных
 * модом, и показывает результат ДО сборки.
 */
public final class ParagraphColors {

	/**
	 * Кусок текста со своим цветом.
	 *
	 * @param color имя цвета («gray», «aqua») либо пустая строка — «цвета нет»
	 */
	public record Piece(String text, String color) {
	}

	/**
	 * Короче двух знаков кусок не переносим: «а», «и», одиночная цифра случайно
	 * совпали бы с обрывком русского слова и покрасили бы не то. Тот же порог,
	 * что в TextTranslator.MIN_RUN_LENGTH.
	 */
	private static final int MIN_PIECE = 2;

	private ParagraphColors() {
	}

	/**
	 * Годится ли кусок в подсветку, несмотря на длину.
	 *
	 * <p>⚠️ Порог {@link #MIN_PIECE} верен для БУКВ: одиночные «а» и «и»
	 * совпали бы с обрывком русского слова и покрасили бы не то. Но цифра
	 * частью русского слова быть не может, а значок — тем более. Из-за общего
	 * порога терялся цвет у КАЖДОГО однозначного числа: «§7Shoots §a3§7
	 * arrows» переводилось в «Стреляет 3 стрелами», и зелёная тройка выходила
	 * белой. Нашёл игрок на луке, где таких чисел три подряд.
	 *
	 * <p>Это ТРЕТИЙ случай одной и той же грабли: сперва не проходил значок
	 * в {@code coloredRuns}, потом одиночный «❣» в {@code carryLegacyCodes},
	 * теперь цифра здесь. Признак общий — короткий кусок БЕЗ БУКВ значим.
	 */
	private static boolean worthPainting(String core) {
		if (core.length() >= MIN_PIECE) {
			return true;
		}
		if (core.isEmpty()) {
			return false;
		}
		for (int i = 0; i < core.length(); i++) {
			if (Character.isLetter(core.charAt(i))) {
				return false;
			}
		}
		return true;
	}

	/**
	 * Цвет ТЕЛА абзаца: тот, которым набрано больше всего КУСКОВ.
	 *
	 * <p>⚠️ Не цвет первой строки. У подсказки способности первая строка —
	 * это заголовок своего цвета («§6Pursuit»), и красить им весь абзац значит
	 * залить золотом всю прозу. Тело же почти всегда серое, и именно оно
	 * задаёт вид описания.
	 */
	public static String body(List<Piece> original) {
		// ⚠️ Считаем КУСКИ, а не знаки. Тело — это то, что ПОВТОРЯЕТСЯ между
		// подсветками: проза разорвана ими на много кусков одного цвета,
		// а подсветка — один-два куска. По знакам же длинная подсветка
		// перетягивала тело на себя: у «§9Ancient Bonus / §7Grants §a+1
		// §9Crit Damage §7per §cCatacombs §7level.» синего 26 знаков против
		// серых 17, и служебные «за», «уровень» уезжали в синий.
		//
		// Прежний довод против кусков — «у §7Grants a §a+20%§7 chance to catch
		// §dHotspot Sea Creatures§7… кусков серого и цветного поровну» — считал
		// серый против ВСЕГО цветного разом. По каждому цвету отдельно там
		// серых кусков 4, а §d всего 2: серый выигрывает уверенно.
		// Замер на 4518 абзацах корпуса: серым тело выходит у 93% против 79%
		// по знакам, починено 630, испорчено 3 (все три — таблицы, где тела нет).
		//
		// ⚠️ Смежные куски одного цвета считаем за ОДИН: перенос строки — чужая
		// вёрстка, он режет «§f✦ Speed» надвое, и счёт удваивал один кусок.
		Map<String, Integer> weight = new HashMap<>();
		String last = null;
		for (Piece piece : original) {
			String text = piece.text().strip();
			if (text.isEmpty()) {
				continue;
			}
			if (!piece.color().equals(last)) {
				weight.merge(piece.color(), 1, Integer::sum);
			}
			last = piece.color();
		}
		String best = "";
		int most = -1;
		for (Map.Entry<String, Integer> entry : weight.entrySet()) {
			int score = entry.getValue();
			// ⚠️ Ничью разрешаем в пользу цвета описания. Без этого победитель
			// зависел бы от порядка обхода HashMap: одна и та же подсказка
			// красилась бы то серым, то фиолетовым — а это ровно тот «весь
			// профиль стал фиолетовым», на котором проект уже обжигался.
			boolean better = score > most
					|| (score == most && BODY_FIRST.contains(entry.getKey())
						&& !BODY_FIRST.contains(best));
			if (better) {
				best = entry.getKey();
				most = score;
			}
		}
		if (!best.isEmpty() || original.isEmpty()) {
			return best;
		}
		// цвета не нашлось вовсе — берём цвет первой строки, как было раньше
		return original.get(0).color();
	}

	/** Цвета, которыми Hypixel набирает ОПИСАНИЕ. При ничьей побеждают они. */
	private static final Set<String> BODY_FIRST = Set.of("gray", "dark_gray");

	/**
	 * Раскладывает перевод на куски, вернув цвета тем, что уцелели дословно.
	 *
	 * @param original куски оригинала в порядке появления
	 * @param translated перевод целиком (без §-кодов)
	 * @param body       цвет тела — им красится всё, что перевелось
	 * @return куски перевода с цветами; склеенные подряд одноцветные не дробятся
	 */
	public static List<Piece> layout(List<Piece> original, String translated, String body) {
		return layout(original, translated, body, Map.of());
	}

	/**
	 * То же, но с подсказкой: как ПЕРЕВЕДЁН каждый цветной кусок.
	 *
	 * <p>Дословно уцелевают числа и английские имена — им цвет возвращается сам.
	 * А переведённое слово найти нечем… если только мы не знаем его перевод.
	 * А мы часто знаем: он лежит в нашем же словаре. «§bSea Creatures» переведено
	 * как «морских существ» — значит место в русской фразе известно, и цвет
	 * возвращается тоже. Замер по корпусу: это добавляет покраску 419 абзацам
	 * сверх 2740, где кусок уцелел дословно.
	 *
	 * @param aliases кусок оригинала -> его перевод из словаря
	 */
	public static List<Piece> layout(List<Piece> original, String translated, String body,
			Map<String, String> aliases) {
		List<Piece> marks = new ArrayList<>(highlights(original, body));
		for (Piece mark : highlights(original, body)) {
			String russian = aliases.get(mark.text());
			if (russian != null && !russian.isBlank() && !russian.equals(mark.text())) {
				marks.add(new Piece(russian.strip(), mark.color()));
			}
		}
		// длинные вперёд — иначе короткий кусок откусит начало длинного
		marks.sort(Comparator.comparingInt((Piece piece) -> piece.text().length()).reversed());
		return laid(marks, translated, body);
	}

	private static List<Piece> laid(List<Piece> marks, String translated, String body) {
		List<Piece> out = new ArrayList<>();
		StringBuilder plain = new StringBuilder();
		int at = 0;
		while (at < translated.length()) {
			Piece hit = null;
			for (Piece mark : marks) {
				if (translated.startsWith(mark.text(), at) && wholeWord(translated, at, mark.text())) {
					hit = mark;
					break;
				}
			}
			if (hit == null) {
				plain.append(translated.charAt(at));
				at++;
				continue;
			}
			if (!plain.isEmpty()) {
				out.add(new Piece(plain.toString(), body));
				plain.setLength(0);
			}
			out.add(new Piece(hit.text(), hit.color()));
			at += hit.text().length();
		}
		if (!plain.isEmpty()) {
			out.add(new Piece(plain.toString(), body));
		}
		return out;
	}

	/**
	 * Подсвеченные куски оригинала — от длинных к коротким.
	 *
	 * <p>Порядок важен: сначала длинные, иначе короткий кусок откусит начало
	 * длинного и раскрасит фразу лоскутами («GOLD» внутри «GOLD and DIAMOND»).
	 */
	private static List<Piece> highlights(List<Piece> original, String body) {
		List<Piece> marks = new ArrayList<>();
		Set<String> seen = new HashSet<>();
		for (Piece piece : original) {
			String core = piece.text().strip();
			if (!worthPainting(core) || piece.color().equals(body)) {
				continue;
			}
			if (seen.add(core)) {
				marks.add(new Piece(core, piece.color()));
			}
		}
		marks.sort(Comparator.comparingInt((Piece piece) -> piece.text().length()).reversed());
		return marks;
	}

	/**
	 * Кусок стоит в переводе ЦЕЛЫМ СЛОВОМ, а не обрывком чужого?
	 *
	 * <p>Без этого «10» из «10%» покрасило бы «10» внутри «100», а короткое
	 * английское имя — свой же кусок внутри русского слова. Границей считаем
	 * всё, что не буква и не цифра: после имени легко идёт кириллица, скобка
	 * или знак процента.
	 */
	private static boolean wholeWord(String text, int at, String piece) {
		int end = at + piece.length();
		boolean leftOk = at == 0 || !Character.isLetterOrDigit(text.charAt(at - 1));
		boolean rightOk = end >= text.length() || !Character.isLetterOrDigit(text.charAt(end));
		return leftOk && rightOk;
	}

	/**
	 * Сколько знаков перевода удалось покрасить не телом. Для отчёта: это и есть
	 * доля вернувшейся подсветки.
	 */
	public static int painted(List<Piece> laid, String body) {
		int sum = 0;
		for (Piece piece : laid) {
			if (!piece.color().equals(body)) {
				sum += piece.text().strip().length();
			}
		}
		return sum;
	}

	/**
	 * Режет РАСКРАШЕННЫЙ перевод на строки заданной ширины, не теряя цвета.
	 *
	 * <p>⚠️ Красить надо ДО переноса, а не после. Если сперва разрезать, а потом
	 * искать куски в каждой строке отдельно, то кусок, разрезанный границей
	 * («Trophy» в конце строки и «Fish» в начале следующей), не найдётся ни
	 * в одной половине — и цвет пропадёт именно там, где перенос и проходит.
	 * Поэтому цвета раздаются один раз по всему абзацу, а здесь куски только
	 * делятся между строками, сохраняя свой цвет.
	 *
	 * @param widths измеритель ширины: сколько пикселей занимает строка. Приходит
	 *               снаружи, потому что шрифт знает только Minecraft, а этот класс
	 *               обязан оставаться проверяемым без игры
	 */
	/**
	 * Режет кусок на слова, НЕ отрывая значок от того, что он помечает.
	 *
	 * <p>⚠️ Значок характеристики — отдельное «слово» («⛏ Mining Speed»), и
	 * обычный перенос по пробелам оставлял его одного в конце строки: на экране
	 * выходило «Повышает ⛏» и строкой ниже «Mining Speed». Читается как обрыв,
	 * причём именно там, где значок и должен пояснять термин.
	 *
	 * <p>Поэтому одиночный значок склеивается со СЛЕДУЮЩИМ словом и переносится
	 * вместе с ним. Буквы и цифры значком не считаются — иначе под правило
	 * попала бы обычная проза.
	 */
	static List<String> words(String text) {
		String[] raw = text.split(" ", -1);
		List<String> out = new ArrayList<>(raw.length);
		for (int i = 0; i < raw.length; i++) {
			String word = raw[i];
			if (isIconOnly(word) && i + 1 < raw.length && !raw[i + 1].isEmpty()) {
				out.add(word + " " + raw[i + 1]);
				i++;
				continue;
			}
			out.add(word);
		}
		return out;
	}

	/** Слово целиком состоит из значков — ни буквы, ни цифры. */
	private static boolean isIconOnly(String word) {
		if (word.isEmpty() || word.length() > 2) {
			return false;
		}
		for (int i = 0; i < word.length(); i++) {
			char symbol = word.charAt(i);
			if (Character.isLetterOrDigit(symbol)) {
				return false;
			}
		}
		return true;
	}

	/**
	 * Кончается ли строка ГОЛЫМ числом — «в радиусе 10», «на 3», «+5,000».
	 *
	 * <p>Считаем числом слово, где есть цифра и нет букв: так проходят
	 * «10», «3», «+5,000», «0.2%», «+8➜12» — и не проходит «10ч» или
	 * «блоков», которые единицу уже несут в себе.
	 */
	static boolean endsWithNumber(CharSequence text) {
		int end = lastWordEnd(text);
		int start = lastWordStart(text, end);
		if (start >= end) {
			return false;
		}
		boolean digit = false;
		for (int i = start; i < end; i++) {
			char symbol = text.charAt(i);
			if (Character.isLetter(symbol)) {
				return false;
			}
			digit |= Character.isDigit(symbol);
		}
		return digit;
	}

	/**
	 * Кончается ли строка ПОДПИСЬЮ — «Перезарядка:», «Стоимость:».
	 *
	 * <p>⚠️ Та же беда, что с числом, только с другой стороны. Значение
	 * подписи — отдельный кусок своего цвета («§8Перезарядка: §a15 с»), и
	 * перенос ставил границу ровно между ними: на экране «Перезарядка:»
	 * висело одной строкой, а «15 с» уезжало на следующую. Подпись без
	 * значения не значит ничего, поэтому пусть строка выйдет шире.
	 *
	 * <p>Двоеточие должно быть В КОНЦЕ слова: так проходит «Перезарядка:»
	 * и не проходит «10:30» или «Ability: Seismic», где двоеточие внутри
	 * фразы и разрыв после него законен.
	 */
	static boolean endsWithLabel(CharSequence text) {
		int end = lastWordEnd(text);
		int start = lastWordStart(text, end);
		if (start >= end || text.charAt(end - 1) != ':') {
			return false;
		}
		// одно только двоеточие подписью не считаем
		for (int i = start; i < end - 1; i++) {
			if (Character.isLetterOrDigit(text.charAt(i))) {
				return true;
			}
		}
		return false;
	}

	/**
	 * Кончается ли строка знаком конца — точкой, восклицанием, двоеточием.
	 *
	 * <p>Нужен, чтобы отличить РАЗРЫВ ВНУТРИ подписи от законного переноса
	 * подписи целиком: после «…даёт эффект.» слово «Способность:» начинает
	 * новую мысль и уехать вниз может, а после «Цена» — не может.
	 */
	static boolean endsSentence(CharSequence text) {
		int end = lastWordEnd(text);
		if (end == 0) {
			return false;
		}
		char last = text.charAt(end - 1);
		return last == '.' || last == '!' || last == '?' || last == ':' || last == '»';
	}

	private static int lastWordEnd(CharSequence text) {
		int end = text.length();
		while (end > 0 && text.charAt(end - 1) == ' ') {
			end--;
		}
		return end;
	}

	private static int lastWordStart(CharSequence text, int end) {
		int start = end;
		while (start > 0 && text.charAt(start - 1) != ' ') {
			start--;
		}
		return start;
	}

	public static List<List<Piece>> wrap(List<Piece> laid, int widthPx, ToWidth widths) {
		List<List<Piece>> out = new ArrayList<>();
		List<Piece> line = new ArrayList<>();
		StringBuilder text = new StringBuilder();
		// ⚠️ Кусок бывает ПРИМЫКАЮЩИМ, и пробел между кусками выдумывать нельзя.
		// Слова режутся по пробелам и склеиваются пробелом заново, а «§5Crystal
		// Hollows§7.» — это два куска подряд БЕЗ пробела: точка своего цвета.
		// Ставя разделитель всегда, мы писали «Crystal Hollows .» — грязь, видная
		// на экране (в живом дампе так вышло у двух подсказок из шести сломанных).
		boolean spaceBefore = true;
		for (Piece piece : laid) {
			boolean firstWord = true;
			for (String word : words(piece.text())) {
				if (word.isEmpty()) {
					continue;
				}
				// вплотную к предыдущему куску — только первое слово куска,
				// и только если пробела не было ни с той, ни с другой стороны
				boolean glued = firstWord && !spaceBefore && !piece.text().startsWith(" ");
				firstWord = false;
				String separator = text.isEmpty() || glued ? "" : " ";
				String candidate = text + separator + word;
				// ⚠️ ПРИМЫКАЮЩИЙ кусок не может НАЧИНАТЬ строку. Запятая после
				// цветного термина — это отдельный кусок своего цвета
				// («§aпредмет питомца§7, но ты можешь…»), и перенос уносил её
				// одну на новую строку: на экране выходило «предмет питомца»
				// и следом «, но ты можешь менять». Пусть строка выйдет на
				// пару пикселей шире — знак препинания обязан остаться
				// при своём слове.
				// ⚠️ Строка не может КОНЧАТЬСЯ голым числом. Число и его единица
				// измерения — разные куски («§a10§7 блоков», «§a3§7 с.»), потому
				// что Hypixel красит число отдельно. Перенос разрывал их, и на
				// экране висело «в радиусе 10» / «блоков.», а в худшем случае
				// «на 3» / «с.» — цифра на одной строке, единица на другой.
				// Приём тот же, что принят выше для запятой: пусть строка выйдет
				// на пару пикселей шире, чем читается «3» в одиночестве.
				// ⚠️ И строка не может НАЧИНАТЬСЯ хвостом подписи — это та же
				// беда, что двумя строками выше, только разрыв приходится
				// ВНУТРЬ подписи, а не после неё. Русская подпись длиннее
				// английской, а ширину мы берём по самой длинной строке
				// ОРИГИНАЛА (чтобы окно не поехало), поэтому в узкой подсказке
				// она перестаёт помещаться:
				//     Hypixel:  «Sell Price» / «6 Coins»
				//     на экране: «Цена» / «продажи:» / «6 монет»
				// У широкой подсказки той же беды нет — вот почему она
				// попадается редко и выглядит случайной.
				// ⚠️ Запрет УЗКИЙ: он снимается, если перед словом стоит знак
				// конца. После «…даёт эффект.» подпись «Способность:» начинает
				// новую мысль, и перенести её целиком как раз правильно.
				boolean labelTail = endsWithLabel(word) && !endsSentence(text);
				if (!text.isEmpty() && !glued && !labelTail
						&& !endsWithNumber(text) && !endsWithLabel(text)
						&& widths.of(candidate) > widthPx) {
					out.add(line);
					line = new ArrayList<>();
					text.setLength(0);
					text.append(word);
					line.add(new Piece(word, piece.color()));
					continue;
				}
				// слово продолжает ту же строку: приклеиваем к последнему куску,
				// если цвет совпал, иначе заводим новый
				text.setLength(0);
				text.append(candidate);
				if (!line.isEmpty() && line.get(line.size() - 1).color().equals(piece.color())) {
					Piece last = line.remove(line.size() - 1);
					line.add(new Piece(last.text() + separator + word, piece.color()));
				} else {
					line.add(new Piece(separator + word, piece.color()));
				}
			}
			if (!piece.text().isEmpty()) {
				spaceBefore = piece.text().endsWith(" ") || piece.text().isBlank();
			}
		}
		if (!line.isEmpty()) {
			out.add(line);
		}
		return out;
	}

	/** Ширина строки в пикселях. Реализацию даёт Minecraft, логике она не нужна. */
	@FunctionalInterface
	public interface ToWidth {
		int of(String text);
	}

	/**
	 * Сколько знаков перевода занимает ЗАГОЛОВОК — или 0, если его отделять нельзя.
	 *
	 * <p><b>Зачем.</b> В подсказке питомца «§bSharp Attitude» стоит своей строкой,
	 * а мод склеивал её с описанием в одно предложение: «Sharp Attitude Морские
	 * существа появляются…». Читается это плохо, и вид подсказки не тот, что
	 * у Hypixel.
	 *
	 * <p><b>Почему без смены ключа.</b> Отрезать заголовок ДО поиска перевода
	 * значило бы поменять ключ абзаца — и 5518 оплаченных переводов перестали бы
	 * находиться. Здесь режется уже НАЙДЕННЫЙ перевод, поэтому ключ не меняется
	 * и платить заново не нужно.
	 *
	 * <p><b>Два признака, и оба обязательны.</b>
	 * <ul>
	 * <li>заголовок выделен ЦВЕТОМ — его цвет отличается от цвета тела. Без этого
	 *     под правило попадает обычная проза: «Grants a random +{n} Farming»
	 *     тоже короткая первая строка, но резать её нельзя;</li>
	 * <li>перевод НАЧИНАЕТСЯ с заголовка — либо дословно (имя осталось
	 *     английским), либо его переводом из словаря. Иначе неизвестно, где
	 *     в русской фразе кончается заголовок, а гадать тут нельзя.</li>
	 * </ul>
	 *
	 * @param variants как заголовок может выглядеть в переводе: оригинал и,
	 *                 если он переводится словарём, его перевод
	 */
	public static int headerCut(String headColor, String body, String translated,
			List<String> variants) {
		if (headColor.equals(body) || translated.isBlank()) {
			return 0;
		}
		for (String variant : variants) {
			String head = variant == null ? "" : variant.strip();
			if (head.isEmpty() || head.length() >= translated.strip().length()) {
				continue;
			}
			if (translated.strip().startsWith(head)) {
				return head.length();
			}
		}
		return 0;
	}

	/** Знак §: в этом классе Minecraft не нужен, код форматирования — обычный символ. */
	private static final char SECTION_SIGN = '§';

	private static final java.util.regex.Pattern CODE =
			java.util.regex.Pattern.compile("§.");

	/**
	 * Где кончается ЗАГОЛОВОК в размеченном переводе — или -1.
	 *
	 * <p>Разметка ставит первым кодом цвет ТЕЛА, а заголовок помечает своим.
	 * Значит заголовок — это первый кусок иного цвета, и кончается он там,
	 * где цвет возвращается к телу.
	 *
	 * <p>⚠️ Возвращаем ПОЗИЦИЮ в строке, а не длину текста: в размеченной
	 * строке заголовок занимает больше знаков, чем его текст, — вместе
	 * с §-кодами. На этом уже обожглись с припиской: вычитая длину текста,
	 * получали хвост от последнего слова отдельной строкой.
	 *
	 * <p>⚠️ Метод жил в {@code Paragraphs}, который завязан на Minecraft, —
	 * и проверить его без игры было НЕЧЕМ. Съехавший заголовок находил игрок
	 * глазами, сравнивая русский скриншот с английским. Здесь логика чистая,
	 * и её гоняет настоящая Java из {@code tools/check_headers.py}.
	 */
	/**
	 * ВСЕ места, где заголовок может кончаться, — от короткого к длинному.
	 *
	 * <p><b>Зачем список, а не одна позиция.</b> Заголовок бывает ДВУХЦВЕТНЫМ:
	 *
	 * <pre>
	 * §7§6Способность: Acupuncture§7 §e§lПКМ§7 Выпускает стрелы…
	 *      ^^^^^^^^^^^^^^^^^^^^^^^^ имя способности     ^^^^^^ клавиша
	 * </pre>
	 *
	 * Одна позиция обрывала заголовок на «Способность: Acupuncture», а в словаре
	 * лежит «Способность: Acupuncture  ПКМ» — сверка не сходилась, и заголовок
	 * оставался слитым с описанием.
	 *
	 * <p>Кандидат — каждый возврат к цвету тела. Перебор продолжается, пока
	 * между цветными кусками стоят ТОЛЬКО пробелы: пошёл текст — заголовок
	 * кончился наверняка. Какой кандидат верный, решает не длина, а совпадение
	 * с переводом первой строки ({@code Paragraphs.header}) — то есть СМЫСЛ.
	 */
	/**
	 * Цвет ТЕЛА размеченного перевода — самый частый код, а не первый.
	 *
	 * <p>⚠️ Здесь стояло {@code translated.substring(0, 2)}, то есть телом
	 * считался код В САМОМ НАЧАЛЕ строки. Пока маркер списка красили тем же
	 * цветом, что и тело («§7∙ §fЗаголовок§7 текст»), это сходилось случайно.
	 * Стоило покрасить «∙» в свой цвет по данным дампа («§8∙ …»), как телом
	 * стал считаться цвет МАРКЕРА — возврата к нему в переводе нет вовсе,
	 * кандидатов на резку получалось НОЛЬ, и заголовок слипался с описанием.
	 * Нашлось только по скриншоту игрока: логика «первый код = тело» выглядит
	 * разумной ровно до первого исключения.
	 *
	 * <p>Считаем ПО КУСКАМ, как и везде в проекте (см. {@code body}): проза
	 * разорвана подсветками на много кусков одного цвета, а подсветка — один-два.
	 * Ничья решается в пользу серого, иначе победитель зависел бы от порядка
	 * обхода — а это ровно тот «весь профиль стал фиолетовым», на котором
	 * проект уже обжигался.
	 */
	public static String bodyCodeOf(String translated) {
		java.util.Map<String, Integer> weight = new java.util.HashMap<>();
		java.util.regex.Matcher codes = CODE.matcher(translated);
		String previous = null;
		while (codes.find()) {
			String code = codes.group();
			if ("klmnor".indexOf(Character.toLowerCase(code.charAt(1))) >= 0) {
				continue; // модификатор цвет не меняет
			}
			// Смежные куски одного цвета — ОДИН кусок: перенос строки чужой,
			// и без этого один цвет считался бы дважды.
			if (code.equals(previous)) {
				continue;
			}
			previous = code;
			weight.merge(code, 1, Integer::sum);
		}
		String best = translated.length() >= 2 ? translated.substring(0, 2) : "§7";
		int top = 0;
		for (java.util.Map.Entry<String, Integer> entry : weight.entrySet()) {
			int count = entry.getValue();
			boolean better = count > top
					|| (count == top && ("§7".equals(entry.getKey()) || "§8".equals(entry.getKey()))
							&& !"§7".equals(best) && !"§8".equals(best));
			if (better) {
				best = entry.getKey();
				top = count;
			}
		}
		return best;
	}

	public static java.util.List<Integer> markedHeadEnds(String translated) {
		java.util.List<Integer> ends = new ArrayList<>(2);
		if (!translated.startsWith("§") || translated.length() < 2) {
			return ends;
		}
		String bodyCode = bodyCodeOf(translated);
		java.util.regex.Matcher codes = CODE.matcher(translated);
		boolean insideHead = false;
		while (codes.find()) {
			String code = codes.group();
			if ("klmnor".indexOf(Character.toLowerCase(code.charAt(1))) >= 0) {
				continue;
			}
			if (!insideHead) {
				if (code.equals(bodyCode)) {
					continue;
				}
				String before = CODE.matcher(translated.substring(0, codes.start()))
						.replaceAll("");
				if (!markersOnly(before)) {
					return ends;
				}
				insideHead = true;
				continue;
			}
			if (!code.equals(bodyCode)) {
				continue;
			}
			ends.add(codes.start());
			// Между этим куском и следующим цветным — только пробелы? Тогда
			// заголовок мог продолжаться, и дальше будет ещё один кандидат.
			// Пошёл текст — заголовок кончился наверняка.
			int next = translated.indexOf('§', codes.end());
			if (next < 0 || !translated.substring(codes.end(), next).isBlank()) {
				break;
			}
			// Остаёмся ВНУТРИ заголовка: следующий цветной код просто пропустится
			// (он не равен цвету тела), а следующий возврат даст новый кандидат.
		}
		return ends;
	}

	public static int markedHeadEnd(String translated) {
		if (!translated.startsWith("§") || translated.length() < 2) {
			return -1;
		}
		// Тот же изъян, что в markedHeadEnds: телом считался ПЕРВЫЙ код,
		// и цветной маркер списка в начале строки ломал резку целиком.
		String bodyCode = bodyCodeOf(translated);
		java.util.regex.Matcher codes = CODE.matcher(translated);
		boolean insideHead = false;
		while (codes.find()) {
			String code = codes.group();
			if ("klmnor".indexOf(Character.toLowerCase(code.charAt(1))) >= 0) {
				continue; // модификатор цвет не меняет
			}
			if (!insideHead) {
				if (code.equals(bodyCode)) {
					continue;
				}
				// ⚠️ Заголовок стоит В САМОМ НАЧАЛЕ: до него не должно быть
				// текста. Без этой проверки правило резало ПРОЗУ с подсвеченным
				// числом — «§7Даёт §6+{n} шоколада§7 и…» превращалось
				// в заголовок «Даёт +{n} шоколада». Замер по корпусу: срабатывало
				// на 3792 абзацах из 3797, то есть почти на всех подряд.
				//
				// ⚠️ МАРКЕР СПИСКА текстом НЕ СЧИТАЕТСЯ. Hypixel ставит пункт
				// как «∙ Class Passive: Doubleshot», заголовком своей строкой,
				// а описание — следующей. Из-за маркера перед заголовком
				// правило отказывало, и на экране выходило слипшееся
				// «∙ Пассивка класса: Doubleshot 50% шанс выпустить вторую
				// стрелу.» — против английского, где заголовок стоит отдельно.
				// Признак маркера берём у ColorLayout, а не заводим свой:
				// копия разошлась бы, как уже расходились знаки списка.
				String before = CODE.matcher(translated.substring(0, codes.start()))
						.replaceAll("");
				if (!markersOnly(before)) {
					return -1;
				}
				insideHead = true;
				continue;
			}
			if (code.equals(bodyCode)) {
				return codes.start(); // цвет вернулся к телу — заголовок кончился
			}
		}
		return -1;
	}

	/**
	 * Кусок состоит только из знаков списка и пробелов?
	 *
	 * <p>Нужно для {@link #markedHeadEnd}: перед заголовком Hypixel ставит
	 * маркер пункта («∙ Class Passive: …»), и он не должен считаться текстом.
	 * Пустая строка тоже подходит — заголовок прямо в начале.
	 */
	private static boolean markersOnly(String text) {
		for (int i = 0; i < text.length(); i++) {
			char symbol = text.charAt(i);
			if (Character.isWhitespace(symbol)) {
				continue;
			}
			if (!ColorLayout.cutMark(String.valueOf(symbol))) {
				return false;
			}
		}
		return true;
	}

	/** Внутренний заголовок в переводе: где начинается и сколько знаков занимает. */
	public record Section(int at, int length) {
	}

	/**
	 * Где в переводе стоят ВНУТРЕННИЕ заголовки — например, зачарования.
	 *
	 * <p><b>Зачем.</b> Hypixel ставит каждое зачарование своей строкой, а под ним
	 * описание, и пустой строкой их не разделяет — значит для нас это ОДИН абзац.
	 * После склейки заголовки втекают в прозу:
	 *
	 * <pre>
	 * было:  §7Bank V
	 *        §7Saves §650%§7 of your coins on death.
	 *        §9Aqua Affinity I
	 *        §7Increases your underwater mining rate.
	 * стало: Bank V Сохраняет 50% твоих монет при смерти. Кроме того, враги
	 *        роняют +2.5 монет при убийстве. Родство с водой I Увеличивает…
	 * </pre>
	 *
	 * Читать это невозможно, и структура, которую задал Hypixel, пропадает.
	 *
	 * <p><b>Почему не отказаться от склейки.</b> Замер по корпусу: в таких абзацах
	 * 123 разные строки, а построчный перевод есть только у 17. Перестав склеивать,
	 * мы получили бы 106 английских строк вместо слипшегося русского — обмен
	 * плохого на худшее, да ещё и с оплатой этих строк заново.
	 *
	 * <p><b>Поэтому режем уже НАЙДЕННЫЙ перевод</b>, ровно как {@link #headerCut}
	 * и {@link #footerCut}: ключ абзаца не меняется, 41 оплаченный перевод остаётся
	 * на месте. Позицию не угадываем — перевод заголовка known из словаря
	 * («Respiration III» → «@enchantment.minecraft.respiration III»), значит место
	 * в русской фразе находится поиском, а не признаком.
	 *
	 * <p>⚠️ Заголовки ищем ПО ПОРЯДКУ, каждый следующий — правее предыдущего.
	 * Иначе «Growth V», встретившееся дважды, дало бы две метки на одном месте.
	 *
	 * <p>⚠️ Ищем по тексту БЕЗ §-кодов, а позицию возвращаем в исходной строке.
	 * Из 41 такого абзаца 4 размечены цветом, и в них поиск по сырой строке
	 * не нашёл бы ничего: между словами стоят коды.
	 *
	 * @param variants на каждый заголовок — как он может выглядеть в переводе:
	 *                 сам по себе и, если словарь его переводит, переводом
	 * @return найденные заголовки по порядку; ненайденные просто пропускаются
	 */
	public static List<Section> sections(String translated, List<List<String>> variants) {
		List<Section> out = new ArrayList<>();
		if (translated == null || translated.isBlank() || variants == null || variants.isEmpty()) {
			return out;
		}

		Undressed text = undress(translated);
		String plain = text.plain();
		int[] where = text.where();

		int from = 0;
		for (List<String> group : variants) {
			int at = -1;
			int length = 0;
			for (String variant : group == null ? List.<String>of() : group) {
				if (variant == null || variant.isBlank()) {
					continue;
				}
				String head = variant.strip();
				int found = plain.indexOf(head, from);
				if (found >= 0 && (at < 0 || found < at)) {
					at = found;
					length = head.length();
				}
			}
			if (at < 0) {
				continue;
			}
			// ⚠️ §-коды ПЕРЕД заголовком забираем в него же: это его цвет, и
			// оставленный в предыдущем куске он покрасил бы чужой хвост.
			int start = where[at];
			while (start >= 2 && translated.charAt(start - 2) == SECTION_SIGN) {
				start -= 2;
			}
			out.add(new Section(start, where[at + length] - start));
			from = at + length;
		}
		return out;
	}

	/**
	 * Текст без §-кодов и карта «позиция в чистом -> позиция в исходном».
	 *
	 * <p>Нужна всем, кто ищет что-то В ПЕРЕВОДЕ, а резать обязан ИСХОДНУЮ строку:
	 * размеченный перевод несёт коды между словами, и поиск по сырой строке
	 * не нашёл бы ничего.
	 */
	/**
	 * Шапку реплики NPC берём ИЗ ОРИГИНАЛА, а не из перевода.
	 *
	 * <p><b>Зачем.</b> Hypixel красит «[NPC]» и ИМЯ по отдельности, причём
	 * у каждого NPC свой цвет: «§e[NPC] §6Blacksmith§f:», «§a[NPC] Sirius§f:»,
	 * «§c[NPC] Mayor Diana§f:». А в наш словарь реплики попали с вики, и там
	 * цвет имени указан лишь у 59% — у остальных шапка сложилась как
	 * «§e[NPC] Имя§f:», то есть имя окрасилось жёлтым от самой метки. На экране
	 * это видно сразу: у половины NPC имя не того цвета, что у Hypixel.
	 *
	 * <p>Данными это не закрыть: вики неполна, а цвет метки тоже бывает разным
	 * (замер по логам: §a — 16, §c — 11, §e — 10). Зато он ЕСТЬ в самой строке,
	 * которую прислал сервер, — значит гадать не нужно вовсе. Тот же принцип,
	 * на котором стоит вся разметка: цвет из оригинала ЭТОЙ строки не ошибается
	 * никогда.
	 *
	 * <p>⚠️ Признак строгий: шапки обоих должны совпасть ЗНАК В ЗНАК после
	 * снятия кодов. Имена NPC мы не переводим, поэтому у реплик они совпадают
	 * всегда, а у чужой строки — никогда, и там ничего не меняется.
	 *
	 * @return перевод с шапкой оригинала либо он же нетронутым
	 */
	public static String swapNpcPrefix(String source, String translated) {
		if (source == null || translated == null) {
			return translated;
		}
		int from = npcHeadEnd(source);
		int to = npcHeadEnd(translated);
		if (from < 0 || to < 0) {
			return translated;
		}
		if (!CODE.matcher(source.substring(0, from)).replaceAll("")
				.equals(CODE.matcher(translated.substring(0, to)).replaceAll(""))) {
			return translated;
		}
		return source.substring(0, from) + translated.substring(to);
	}

	/** Длина шапки «[NPC] Имя: » вместе с кодами, или -1 если это не реплика. */
	private static int npcHeadEnd(String text) {
		if (!CODE.matcher(text).replaceAll("").startsWith(NPC_MARK)) {
			return -1;
		}
		for (int i = 0; i < text.length(); i++) {
			char symbol = text.charAt(i);
			if (symbol == SECTION_SIGN) {
				i++;                      // сам код двоеточием быть не может
				continue;
			}
			if (symbol == ':') {
				int end = i + 1;
				// пробел после двоеточия принадлежит шапке: без него тело
				// перевода приклеилось бы к имени вплотную
				return end < text.length() && text.charAt(end) == ' ' ? end + 1 : end;
			}
		}
		return -1;
	}

	private static final String NPC_MARK = "[NPC] ";

	/**
	 * Ведущий цвет ЗАГОЛОВКА берём из оригинала, а не из разметки перевода.
	 *
	 * <p><b>Зачем.</b> У Hypixel цвет заголовка бывает ДАННЫМИ, а не украшением:
	 * «§8Tiered Bonus: Dominus (0/4)» против «§6Tiered Bonus: Fireproof (2/2)» —
	 * тёмно-серый значит «бонус не набран», золотой «набран». Замер по лору
	 * аукциона: 33 лота серых против 6 золотых. То же у зачарований («Ultimate
	 * Wise V» бывает §d и §7) и у Party Hat, где цветом показан выбор игрока.
	 *
	 * <p>Разметка перевода запоминает цвет ТОГО предмета, с которого её снимали,
	 * и на чужом предмете он врёт. У нас так вышло в 38 записях из 44: разметку
	 * брали с аукционных лотов, где бонус обычно пуст, — и у игрока с набранным
	 * бонусом заголовок выходил серым вместо золотого.
	 *
	 * <p>⚠️ Меняем ТОЛЬКО ведущие коды. Внутренние остаются: заголовок бывает
	 * двухцветным («§6Способность: X §e§lПКМ»), и стереть их значило бы потерять
	 * горячую клавишу. Если у оригинала ведущих кодов нет вовсе (цвет пришёл
	 * стилем компонента), не трогаем ничего — стиль применится и так.
	 *
	 * <p>⚠️ ПУСТОЙ {@code leading} — это НЕ «нечего делать». Цвет приходит
	 * ДВУМЯ путями, и в подсказке предмета он почти всегда в СТИЛЕ компонента,
	 * а §-кодов в тексте нет вовсе (проверено: «gold 'Tiered Bonus: Molten Core
	 * (4/4)'» — ни одного кода). Первая версия на пустом leading возвращала
	 * заголовок как есть — и правка не делала ничего, а игрок прислал тот же
	 * скриншот второй раз. Поэтому ведущие коды перевода снимаем ВСЕГДА:
	 * дальше их место займёт стиль оригинальной строки.
	 *
	 * @param head    вырезанный заголовок перевода, с кодами
	 * @param leading ведущие коды строки оригинала («§6», «§7§l») или пусто,
	 *                если цвет пришёл стилем
	 */
	/**
	 * Что осталось от перевода после заголовка — по ЗНАЧИМЫМ знакам.
	 *
	 * <p>⚠️ Раньше резали по ДЛИНЕ строки заголовка, и это сломалось, как только
	 * заголовок стал перекрашиваться цветом оригинала: подмена ведущих кодов
	 * меняет длину, а рез оставался прежним. У «§7§6Способность: Cleave» снятие
	 * четырёх знаков сдвинуло границу, и в описание уехал хвост слова:
	 * <pre>
	 *   Способность: Cleave
	 *   eave При ударе по существу…       &lt;- «Cl» осталось в заголовке
	 * </pre>
	 * Длина кодов не должна влиять на границу вовсе: считаем ЗНАЧИМЫЕ знаки
	 * заголовка и пропускаем столько же в переводе, глотая коды по дороге.
	 */
	public static String afterHead(String translated, String head) {
		if (translated == null || head == null) {
			return translated;
		}
		String text = translated.strip();
		return text.substring(headEnd(text, head)).strip();
	}

	/**
	 * Граница заголовка в переводе — позиция, с которой начинается описание.
	 *
	 * <p>Отдельно от {@link #afterHead}, потому что нужна ещё и тому, кто ищет
	 * ВОЗВРАТ К ЦВЕТУ ТЕЛА: последний §-код перед этой границей и есть цвет,
	 * которым Hypixel красит описание.
	 */
	public static int headEnd(String translated, String head) {
		if (translated == null || head == null) {
			return 0;
		}
		String text = translated.strip();
		int want = CODE.matcher(head).replaceAll("").strip().length();
		int seen = 0;
		int at = 0;
		while (at < text.length() && seen < want) {
			if (text.charAt(at) == SECTION_SIGN && at + 1 < text.length()) {
				at += 2;
				continue;
			}
			at++;
			seen++;
		}
		return at;
	}

	public static String headWithSourceCodes(String head, String leading) {
		if (head == null) {
			return null;
		}
		if (leading == null) {
			leading = "";
		}
		int at = 0;
		while (at + 1 < head.length() && head.charAt(at) == SECTION_SIGN) {
			at += 2;
		}
		return leading + head.substring(at);
	}

	private record Undressed(String plain, int[] where) {
	}

	private static Undressed undress(String source) {
		StringBuilder clean = new StringBuilder(source.length());
		int[] where = new int[source.length() + 1];
		for (int i = 0; i < source.length(); i++) {
			char symbol = source.charAt(i);
			if (symbol == SECTION_SIGN && i + 1 < source.length()) {
				i++;
				continue;
			}
			where[clean.length()] = i;
			clean.append(symbol);
		}
		where[clean.length()] = source.length();
		return new Undressed(clean.toString(), where);
	}

	/**
	 * Где в переводе начинается каждый ПУНКТ СПИСКА.
	 *
	 * <p><b>Зачем.</b> Список мод склеивать не станет — иначе пункты размажутся
	 * в сплошную строку («▶ Без фильтра Обычный Необычный Редкий…»), читать это
	 * невозможно. Но отказ от склейки означал, что найденный перевод АБЗАЦА
	 * выбрасывается совсем: на живом корпусе так лежат мёртвым грузом
	 * 301 оплаченный перевод, и на экране вместо них английский текст.
	 *
	 * <p><b>Поэтому режем уже НАЙДЕННЫЙ перевод</b>, как {@link #sections}
	 * и {@link #headerCut}: ключ абзаца не меняется, платить заново не нужно.
	 *
	 * <p><b>Почему по маркерам, а не по словарю.</b> Маркер — это СИМВОЛ, и
	 * модель переносит его дословно, как иконку. Замер по корпусу: у всех
	 * 301 абзаца-списка маркеров в переводе РОВНО столько же, сколько строк
	 * с маркером в оригинале — 301 из 301. Поиск же переводов пунктов
	 * по словарю разрезал только 43%: половина пунктов словарю неизвестна,
	 * она куплена лишь в составе абзаца.
	 *
	 * <p>⚠️ Маркеры ищем ПО ПОРЯДКУ, каждый следующий правее предыдущего:
	 * иначе повторный «◼» дал бы две метки на одном месте.
	 *
	 * <p>⚠️ Если маркеров в переводе меньше, чем строк с ними, возвращаем
	 * пустой список — резать наугад нельзя. Лучше оставить абзац как пришёл,
	 * чем разложить пункты по чужим границам.
	 *
	 * @param marks маркеры строк оригинала, ПО ПОРЯДКУ строк; пустая строка —
	 *              «у этой строки маркера нет»
	 * @return позиции в переводе, с которых начинается пункт, по возрастанию;
	 *         первая позиция может быть больше нуля — тогда перед списком
	 *         стоит вступление («Примеры:»)
	 */
	public static List<Integer> listCuts(String translated, List<String> marks) {
		List<Integer> out = new ArrayList<>();
		if (translated == null || translated.isBlank() || marks == null) {
			return out;
		}
		Undressed text = undress(translated);
		String plain = text.plain();

		int from = 0;
		for (String mark : marks) {
			if (mark == null || mark.isBlank()) {
				continue;
			}
			int at = plain.indexOf(mark, from);
			if (at < 0) {
				// Маркер потерялся при переводе — резать наугад нельзя.
				return List.of();
			}
			// ⚠️ §-коды ПЕРЕД маркером забираем в новый пункт: это его цвет,
			// оставленный в предыдущем куске он покрасил бы чужой хвост.
			int start = text.where()[at];
			while (start >= 2 && translated.charAt(start - 2) == SECTION_SIGN) {
				start -= 2;
			}
			out.add(start);
			from = at + mark.length();
		}
		return out;
	}

	/**
	 * Сколько знаков перевода занимает ПРИМЕЧАНИЕ в конце — или 0, если резать нельзя.
	 *
	 * <p><b>Зачем.</b> Hypixel ставит тусклую приписку последней строкой:
	 * «§8The pet must be visible to apply the item!» под обычным описанием.
	 * Пустой строкой она не отделена, поэтому для мода это тот же абзац, и после
	 * склейки приписка втекает в текст: «…в любое время! Питомец должен быть
	 * виден, чтобы применить предмет!» — сплошняком, без паузы, которую делал
	 * Hypixel.
	 *
	 * <p>Признаки те же, что у {@link #headerCut}, только с хвоста: приписка
	 * выделена ЦВЕТОМ (иначе это обычное продолжение прозы) и перевод
	 * ЗАКАНЧИВАЕТСЯ ею — дословно либо переводом из словаря. Режется уже
	 * НАЙДЕННЫЙ перевод, поэтому ключ абзаца не меняется и платить заново
	 * не нужно.
	 *
	 * @param variants как приписка может выглядеть в переводе
	 * @return длина хвоста в знаках
	 */
	public static int footerCut(String tailColor, String body, String translated,
			List<String> variants) {
		if (tailColor.equals(body) || translated.isBlank()) {
			return 0;
		}
		String whole = translated.strip();
		for (String variant : variants) {
			String tail = variant == null ? "" : variant.strip();
			if (tail.isEmpty() || tail.length() >= whole.length()) {
				continue;
			}
			if (whole.endsWith(tail)) {
				return tail.length();
			}
			// ⚠️ Знак в конце Hypixel ставит не всегда одинаково: в словаре
			// «…применить предмет», а на экране «…применить предмет!».
			// Из-за одного восклицательного знака приписка не отрезалась бы.
			String loose = tail.replaceAll("[.!?]+$", "");
			if (!loose.isEmpty() && whole.replaceAll("[.!?]+$", "").endsWith(loose)) {
				return whole.length() - whole.replaceAll("[.!?]+$", "").lastIndexOf(loose);
			}
		}
		return 0;
	}
}
