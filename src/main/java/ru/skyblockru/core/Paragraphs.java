package ru.skyblockru.core;

import net.minecraft.ChatFormatting;
import net.minecraft.client.Minecraft;
import net.minecraft.client.gui.Font;
import net.minecraft.network.chat.Component;
import net.minecraft.network.chat.MutableComponent;
import net.minecraft.network.chat.Style;
import net.minecraft.network.chat.TextColor;

import java.util.ArrayList;
import java.util.Collections;
import java.util.IdentityHashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Set;
import java.util.regex.Pattern;

/**
 * Абзацы подсказок: склеить разрезанную фразу, перевести целиком, разложить заново.
 *
 * <p><b>Зачем.</b> Hypixel присылает описание уже разрезанным на строки, и разрез
 * не совпадает с концом фразы: «…place gold» / «ore. Minions also…». Из-за этого
 * весь вечер лезли однотипные поломки — то материал разорван пополам, то
 * предложение кончается посреди строки, то у одного миньона перенос такой,
 * а у другого другой. Это не разные баги, а один: <b>строка от сервера — кусок
 * вёрстки, а не единица смысла</b>.
 *
 * <p>Плюс перевод получался хуже, чем мог: переводчику запрещалось двигать границу
 * переноса, то есть русскую фразу приходилось втискивать в границы английской.
 *
 * <p><b>Осторожность.</b> Определять «где тут проза, а где характеристики»
 * автоматически ненадёжно — проверено на корпусе, признаки путаются. Поэтому
 * абзац перекладывается ТОЛЬКО если для него есть готовый перевод в словаре.
 * Нет перевода — подсказка остаётся ровно такой, какой пришла, и сломать
 * нечего.
 *
 * <p>Ширину берём по САМОЙ ДЛИННОЙ строке ВСЕЙ подсказки — не одного абзаца.
 * Окно от этого не едет (такая ширина у него уже есть), зато короткий абзац
 * больше не зажимает русскую фразу в свои узкие рамки. Считали по абзацу —
 * «Стоимость: 18 монет» рассыпалось лесенкой на три строки под «Cost»/«18 Coins».
 */
public final class Paragraphs {

	/** Меньше двух строк — склеивать нечего. */
	private static final int MIN_LINES = 2;

	/**
	 * Сколько разных цветов ещё считается «заголовок и описание».
	 * Больше — это разметка: таблица характеристик, список полей.
	 */
	private static final int MAX_HEADER_COLORS = 3;

	/** Запас в пикселях: без него последнее слово иногда не влезает. */
	private static final int WIDTH_SLACK = 2;

	private Paragraphs() {
	}

	/** Кусок подсказки: подряд идущие непустые строки. */
	public record Run(int from, int to) {
		int size() {
			return to - from;
		}
	}

	/** Разбивает список строк на куски по пустым строкам. */
	public static List<Run> runs(List<Component> lines) {
		List<Run> found = new ArrayList<>();
		int start = -1;
		for (int i = 0; i < lines.size(); i++) {
			boolean blank = lines.get(i).getString().trim().isEmpty();
			if (blank) {
				if (start >= 0 && i - start >= MIN_LINES) {
					found.add(new Run(start, i));
				}
				start = -1;
			} else if (start < 0) {
				start = i;
			}
		}
		if (start >= 0 && lines.size() - start >= MIN_LINES) {
			found.add(new Run(start, lines.size()));
		}
		return found;
	}

	/**
	 * Ключ абзаца: строки, склеенные пробелом, без §-кодов.
	 *
	 * <p>Числа НЕ обобщаем: этим занимается сам {@link Translator} при поиске,
	 * и делать это дважды значило бы разойтись с ним в мелочах.
	 */
	public static String key(List<Component> lines, Run run) {
		StringBuilder text = new StringBuilder();
		for (int i = run.from(); i < run.to(); i++) {
			if (!text.isEmpty()) {
				text.append(' ');
			}
			text.append(LegacyText.strip(lines.get(i).getString()).trim());
		}
		return text.toString().trim();
	}

	/**
	 * Перекладывает переведённый абзац по строкам той же ширины.
	 *
	 * <p>⚠️ Цвета раздаются ПО КУСКАМ, а не заливаются цветом первой строки.
	 * Раньше ведущий код первой строки ставился в каждую новую, и подсказка
	 * питомца выходила такой: «§6Pursuit Повышает шанс поймать Trophy Fish
	 * ступеней GOLD и DIAMOND на 10%.» — всё золотое, подсветка чисел и
	 * названий пропала, заголовок слился с прозой. Теперь то, что уцелело
	 * в переводе дословно (число, процент, английское имя), красится своим
	 * прежним цветом, а остальное — цветом ТЕЛА абзаца ({@link ParagraphColors}).
	 *
	 * @param sample любая строка исходного абзаца — с неё берём базовый стиль
	 * @param source строки исходного абзаца целиком: из них берутся куски и цвета
	 */
	public static List<Component> wrap(String translated, int widthPx, Component sample,
			List<Component> source) {
		Font font = Minecraft.getInstance().font;
		Style style = dropHeadModifiers(styleOf(sample), source);

		// ⚠️ ПЕРЕВОД С РАЗМЕТКОЙ — самый точный путь, и он важнее всей механики ниже.
		//
		// Всё, что делает этот класс дальше, — попытка ВОССТАНОВИТЬ цвета, которых
		// в переводе нет: ключ абзаца строится из чистого текста (иначе словарь
		// не совпадёт), и купленные переводы тоже чистые. Отсюда потолок: цвет
		// возвращается только тем кускам, которые уцелели дословно, — числам
		// и английским именам, а переведённое слово подсветку теряет.
		//
		// Но если перевод несёт §-коды САМ, гадать не нужно вовсе: раскладываем
		// ровно по ним. Так уже устроены переводы чата из SkyHanni, и так же
		// будут выглядеть новые переводы абзацев, если переводить их с маркерами
		// цвета — тем же приёмом, каким уже прячутся иконки ({i1}, {i2}).
		if (LegacyText.hasCodes(translated)) {
			return wrapMarked(translated, widthPx, style, font);
		}

		Map<String, Style> palette = new LinkedHashMap<>();
		List<ParagraphColors.Piece> pieces = piecesOf(source, style, palette);
		String body = ParagraphColors.body(pieces);

		// Сперва цвета на весь абзац, и только потом перенос: иначе кусок,
		// разрезанный границей строки, не найдётся ни в одной половине.
		// Вместе с кусками отдаём и их переводы: цвет вернётся не только тому,
		// что уцелело дословно, но и переведённым словам, которые знает словарь.
		List<ParagraphColors.Piece> laid =
				ParagraphColors.layout(pieces, translated, body, aliases(pieces, body));
		Style bodyStyle = palette.getOrDefault(body, style);

		List<Component> out = new ArrayList<>();
		for (List<ParagraphColors.Piece> row
				: ParagraphColors.wrap(laid, widthPx + WIDTH_SLACK, font::width)) {
			MutableComponent line = Component.empty().setStyle(bodyStyle);
			for (ParagraphColors.Piece piece : row) {
				line.append(Component.literal(piece.text())
						.setStyle(palette.getOrDefault(piece.color(), bodyStyle)));
			}
			out.add(line);
		}
		return out;
	}

	/**
	 * Как переведён каждый ПОДСВЕЧЕННЫЙ кусок — по нашему же словарю.
	 *
	 * <p>Это и есть ответ на «почему нельзя просто перенести цвета»: перенести
	 * можно, если знать, во что кусок превратился. Часть таких пар у нас уже
	 * есть — «Sea Creatures» → «морских существ» лежит в словаре, — и по ним
	 * цвет возвращается даже переведённому слову.
	 *
	 * <p>Спрашиваем ТОЛЬКО точный словарь ({@link Translator#lookup}), без
	 * правил и глоссария: правило может позвать само себя, а глоссарий вернёт
	 * полуфразу. Не нашлось — кусок просто останется цветом тела.
	 */
	private static Map<String, String> aliases(List<ParagraphColors.Piece> pieces, String body) {
		Map<String, String> out = new LinkedHashMap<>();
		for (ParagraphColors.Piece piece : pieces) {
			String core = piece.text().strip();
			if (core.length() < 3 || piece.color().equals(body) || out.containsKey(core)) {
				continue;
			}
			Translator.Match found = Translator.lookup(core, TextTranslator.SRC_ITEM_LORE, null);
			if (found != null && !found.text().isBlank()) {
				out.put(core, found.text());
			}
		}
		return out;
	}

	/**
	 * Раскладывает перевод, который САМ несёт §-коды: цвета берутся из него.
	 *
	 * <p>Ничего не угадываем и ничего не ищем в оригинале — разметка уже есть.
	 * Перенос идёт по словам, и цвет каждого куска переезжает на новую строку
	 * вместе с ним ({@link ParagraphColors#wrap}).
	 */
	private static List<Component> wrapMarked(String translated, int widthPx, Style base,
			Font font) {
		Map<String, Style> palette = new LinkedHashMap<>();
		List<ParagraphColors.Piece> pieces = new ArrayList<>();
		LegacyText.parse(translated, base).visit((style, text) -> {
			if (!text.isEmpty()) {
				TextColor color = style.getColor();
				String name = color == null ? "" : color.serialize();
				palette.putIfAbsent(name, style);
				pieces.add(new ParagraphColors.Piece(text, name));
			}
			return Optional.empty();
		}, base);

		List<Component> out = new ArrayList<>();
		for (List<ParagraphColors.Piece> row
				: ParagraphColors.wrap(pieces, widthPx + WIDTH_SLACK, font::width)) {
			MutableComponent line = Component.empty().setStyle(base);
			for (ParagraphColors.Piece piece : row) {
				line.append(Component.literal(piece.text())
						.setStyle(palette.getOrDefault(piece.color(), base)));
			}
			out.add(line);
		}
		return out;
	}

	/**
	 * Заголовок абзаца отдельной строкой — или null, если отделять нельзя.
	 *
	 * <p>Признаки и обоснование — в {@link ParagraphColors#headerCut}. Здесь
	 * только сбор данных: цвет первой строки, цвет тела и то, как заголовок
	 * может выглядеть в переводе (сам по себе либо переведённый словарём).
	 *
	 * <p>Строку собираем ЗАНОВО, а не берём исходную: заголовок мог перевестись
	 * («Full Set Bonus:» -> «Бонус комплекта:»), и тогда на экране должен стоять
	 * перевод — но цветом оригинала.
	 */
	private static Component header(List<Component> lines, Run run, String translated,
			String origin, String item) {
		if (run.size() < 2) {
			return null;
		}
		Component first = lines.get(run.from());
		String head = LegacyText.strip(first.getString()).trim();
		if (head.isEmpty()) {
			return null;
		}
		List<String> variants = new ArrayList<>(2);
		variants.add(head);
		Translator.Match own = Translator.lookup(head, origin, item);
		if (own != null) {
			variants.add(own.text());
		}

		// ⚠️ У РАЗМЕЧЕННОГО перевода сравнивать текст бесполезно: он начинается
		// с §-кодов («§7§6Gold's Power§7 Повышает…»), а варианты чистые, и
		// startsWith не совпадёт НИКОГДА. Зато разметка уже сделала главное —
		// пометила заголовок своим цветом, значит граница известна точно.
		// Ровно та же развязка, что у приписки в конце (markedTailStart).
		if (LegacyText.hasCodes(translated)) {
			// ⚠️ Кандидатов НЕСКОЛЬКО: заголовок бывает двухцветным — имя
			// способности одним цветом, горячая клавиша другим
			// («§6Способность: Acupuncture§7 §e§lПКМ§7 Выпускает…»). Одна
			// позиция обрывала его на имени, сверка с переводом первой строки
			// не сходилась, и заголовок оставался слитым с описанием.
			// Какой кандидат верный, решает не длина, а СМЫСЛ — совпадение
			// с тем, что лежит в словаре.
			for (int end : ParagraphColors.markedHeadEnds(translated)) {
				Component made = headerAt(translated, end, variants, first);
				if (made != null) {
					return made;
				}
			}
			// ⚠️ У СЕРОГО заголовка кандидатов по цвету НЕТ ВОВСЕ, и это
			// не сбой разметки: «Growth V» Hypixel красит цветом ТЕЛА, значит
			// возврата к телу в переводе не будет — искать нечего.
			// («Aqua Affinity I» и «Protection V» синие, поэтому у них всё
			// работало, а «Growth V» и «Bank V» слипались с описанием —
			// это записано в граблях про цвет заголовков.)
			//
			// Тогда работает признак ПО ТЕКСТУ: перевод начинается с заголовка
			// дословно либо с его перевода из словаря. Имена зачарований мы
			// не переводим, поэтому для них он совпадает всегда.
			return headerByText(translated, variants, first);
		}

		Map<String, Style> palette = new LinkedHashMap<>();
		List<ParagraphColors.Piece> pieces = piecesOf(
				new ArrayList<>(lines.subList(run.from(), run.to())), first.getStyle(), palette);
		String body = ParagraphColors.body(pieces);
		return headerPlain(translated, variants, first, body);
	}

	/**
	 * Заголовок по ТЕКСТУ — для случая, когда цветом он не выделен.
	 *
	 * <p>Ищем в размеченном переводе начало, которое после снятия §-кодов
	 * совпадает с переводом первой строки. Режем сразу за ним, пропуская коды:
	 * иначе следующий кусок остался бы без своего цвета.
	 *
	 * <p>⚠️ Признак СТРОГИЙ: совпадение с тем, что лежит в словаре. Проза
	 * так не отрезается — у неё перевода первой строки нет, и вариантов
	 * для сверки не будет.
	 */
	private static Component headerByText(String translated, List<String> variants,
			Component first) {
		String plain = LegacyText.strip(translated);
		for (String variant : variants) {
			if (variant == null || variant.isBlank()) {
				continue;
			}
			String want = variant.strip();
			if (!sameText(plain.strip().startsWith(want) ? want : "", want)) {
				continue;
			}
			// переводим позицию из чистого текста в размеченный: считаем
			// столько же ЗНАЧИМЫХ символов, пропуская коды
			int seen = 0;
			int at = 0;
			while (at < translated.length() && seen < want.length()) {
				if (translated.charAt(at) == ChatFormatting.PREFIX_CODE && at + 1 < translated.length()) {
					at += 2;
					continue;
				}
				at++;
				seen++;
			}
			if (seen < want.length()) {
				continue;
			}
			// ⚠️ И здесь цвет из ОРИГИНАЛА: это путь для СЕРОГО заголовка,
			// где кандидатов по цвету нет вовсе, — а разметка перевода всё
			// равно несёт цвет того предмета, с которого её снимали.
			return Component.literal(ParagraphColors.headWithSourceCodes(
							translated.substring(0, at),
							LegacyText.leadingCodes(first.getString())))
					.setStyle(firstPieceStyle(first));
		}
		return null;
	}

	/**
	 * Один кандидат на заголовок: годится ли он.
	 *
	 * <p>⚠️ Пробелы сравниваем МЯГКО. В словаре лежит «Способность: Acupuncture
	 * &nbsp;ПКМ» с двойным пробелом (так шлёт Hypixel), а разметка ставит между
	 * кусками один. Строгая сверка знак в знак не сходилась НИ РАЗУ — та же
	 * грабля, что при разметке цветом, где схлопнутый пробел браковал половину
	 * пачки.
	 */
	private static Component headerAt(String translated, int end, List<String> variants,
			Component first) {
		if (end <= 0) {
			return null;
		}
		// ⚠️ Заголовок обязан быть СОРАЗМЕРЕН первой строке оригинала.
		//
		// Разметка красит не только заголовки: у прозы бывает покрашена первая
		// ФРАЗА целиком («§7§aТы подбираешь ящики на {n}% быстрее§7. §aТы строишь
		// баллисту…»), и по одному цвету её от заголовка не отличить — точка
		// уезжала в начало следующей строки. А вот совпадение с ПЕРВОЙ СТРОКОЙ
		// оригинала (или её переводом из словаря) отличает точно: у прозы такого
		// перевода нет.
		String cutText = LegacyText.strip(translated.substring(0, end)).trim();
		for (String variant : variants) {
			if (variant == null || variant.isBlank()) {
				continue;
			}
			if (sameText(cutText, variant)) {
				// ⚠️ Цвет заголовка берём У ОРИГИНАЛА: у Hypixel он бывает
				// ДАННЫМИ («§8Tiered Bonus (0/4)» против «§6… (2/2)»), а
				// разметка перевода помнит цвет чужого предмета.
				return Component.literal(ParagraphColors.headWithSourceCodes(
								translated.substring(0, end),
								LegacyText.leadingCodes(first.getString())))
						.setStyle(firstPieceStyle(first));
			}
			if (countedHead(cutText, variant)) {
				// ⚠️ Счётчик ДОБИРАЕМ в заголовок, а не оставляем описанию.
				//
				// Hypixel красит «(0/4)» цветом ТЕЛА, поэтому возврат к нему
				// приходится ПЕРЕД счётчиком — а на экране счётчик стоит
				// на строке заголовка. Отрезав по цвету, мы уносили его вниз
				// вместе с описанием: «Бонус полного комплекта: Shadow
				// Assassin» / «(0/4) Даёт +1❁ к силе…». Расширяем рез до конца
				// той части, что совпала с построчным переводом.
				int wider = tailEnd(translated, end, cutText, variant);
				return Component.literal(ParagraphColors.headWithSourceCodes(
								translated.substring(0, wider),
								LegacyText.leadingCodes(first.getString())))
						.setStyle(firstPieceStyle(first));
			}
		}
		return null;
	}

	/**
	 * Куда сдвинуть рез, чтобы забрать счётчик: конец хвоста в переводе.
	 *
	 * <p>Хвост берём из построчного перевода ({@code variant}) — то, что идёт
	 * после совпавшего заголовка, — и ищем его конец в размеченной строке,
	 * пропуская §-коды. Не нашли — оставляем прежний рез: лучше заголовок
	 * без счётчика, чем съеденное описание.
	 */
	private static int tailEnd(String translated, int end, String cutText, String variant) {
		String head = cutText.trim().replaceAll("\\s+", " ");
		String whole = variant.trim().replaceAll("\\s+", " ");
		if (!whole.startsWith(head)) {
			return end;
		}
		String tail = whole.substring(head.length()).trim();
		if (tail.isEmpty()) {
			return end;
		}
		// идём по переводу с позиции реза, сверяя знаки хвоста и пропуская коды
		int at = end;
		int matched = 0;
		while (at < translated.length() && matched < tail.length()) {
			char symbol = translated.charAt(at);
			if (symbol == '§' && at + 1 < translated.length()) {
				at += 2;
				continue;
			}
			char want = tail.charAt(matched);
			if (symbol == want) {
				matched++;
				at++;
				continue;
			}
			if (Character.isWhitespace(symbol)) {
				at++;
				continue;
			}
			if (Character.isWhitespace(want)) {
				matched++;
				continue;
			}
			return end;
		}
		return matched == tail.length() ? at : end;
	}

	/**
	 * Заголовок со СЧЁТЧИКОМ, который Hypixel красит цветом ТЕЛА.
	 *
	 * <p>«§6Full Set Bonus: True Dwarf §7(2/4)» — имя золотое, счётчик серый.
	 * Разметка перевода повторяет это, поэтому вырезается «Бонус полного
	 * комплекта: True Dwarf» БЕЗ счётчика, а построчный перевод строки идёт
	 * со счётчиком: «…True Dwarf (2/4)». Строгая сверка не сходилась, резка
	 * отменялась, и заголовок слипался с описанием — на экране «Бонус полного
	 * комплекта: True Dwarf (2/4) Даёт +50…».
	 *
	 * <p>⚠️ Ослабление УЗКОЕ и намеренно: принимаем префикс, только если
	 * остаток НЕ СОДЕРЖИТ БУКВ — то есть это счётчик, скобки или число.
	 * У прозы хвост всегда со словами, и она по-прежнему не режется.
	 */
	private static boolean countedHead(String cutText, String variant) {
		String head = cutText.trim().replaceAll("\\s+", " ");
		String whole = variant.trim().replaceAll("\\s+", " ");
		if (head.isEmpty() || head.length() >= whole.length() || !whole.startsWith(head)) {
			return false;
		}
		// ⚠️ Дырки убираем ДО проверки на буквы: в «({n}/{n})» стоит латинская
		// «n», и без этого остаток считался словом, а заголовок не резался.
		// Первая версия правки на этом и споткнулась — счётчик со ЗНАЧЕНИЕМ
		// («(2/4)») резался, а с ДЫРКОЙ («({n}/{n})») нет, хотя это одна
		// и та же строка до и после подстановки чисел.
		String tail = whole.substring(head.length()).replaceAll("\\{[ns]\\}", "");
		for (int i = 0; i < tail.length(); i++) {
			if (Character.isLetter(tail.charAt(i))) {
				return false;
			}
		}
		return true;
	}

	/** Пробелы схлопнуты: «Acupuncture  ПКМ» и «Acupuncture ПКМ» — одно и то же. */
	private static boolean sameText(String left, String right) {
		return left.trim().replaceAll("\s+", " ")
				.equals(right.trim().replaceAll("\s+", " "));
	}

	/**
	 * Заголовок у НЕразмеченного перевода — прежний путь по цвету и тексту.
	 */
	private static Component headerPlain(String translated, List<String> variants,
			Component first, String body) {
		int cut = ParagraphColors.headerCut(leadingColor(first), body, translated, variants);
		if (cut <= 0) {
			return null;
		}
		return Component.literal(translated.strip().substring(0, cut)).setStyle(firstPieceStyle(first));
	}

	/** Числа и подстановки в скелете строки — всё это «одно и то же место». */
	private static final Pattern SHAPE_NUMBER = Pattern.compile("\\{[ns]\\}|\\d[\\d,.]*");

	/** Слово в скелете: любое, лишь бы стояло на том же месте. */
	private static final Pattern SHAPE_WORD = Pattern.compile("[\\p{L}][\\p{L}'-]*");

	/**
	 * Форма строки: «47.4% ○ 652,431 votes | Diana» -> «#% ○ # W | W».
	 *
	 * <p>Смысл в том, чтобы РАЗНЫЕ строки одной таблицы дали ОДИН скелет:
	 * содержимое у них своё, а расстановка чисел и слов общая.
	 */
	private static String shapeOf(String line) {
		String text = SHAPE_NUMBER.matcher(LegacyText.strip(line).trim()).replaceAll("#");
		text = SHAPE_WORD.matcher(text).replaceAll("W");
		return text.replaceAll("\\s+", " ");
	}

	/**
	 * Похож ли кусок на ТАБЛИЦУ: три и более строк одной формы.
	 *
	 * <p>Порог держим высоким нарочно. Две одинаковые строки бывают и в прозе
	 * («Даёт +5 к силе.» / «Даёт +5 к защите.»), а вот три подряд — это уже
	 * столбцы. Плюс требуем, чтобы такая форма покрывала больше половины
	 * куска: иначе одна случайная пара утащила бы весь абзац.
	 *
	 * <p>⚠️ В скелете обязано быть ЧИСЛО. Без этого условия под правило попала
	 * бы обычная проза с одинаковым началом предложений, а таблицы без чисел
	 * в игре не встречаются — колонка всегда что-то считает.
	 */
	private static boolean looksLikeTable(List<Component> lines, Run run) {
		Map<String, Integer> shapes = new LinkedHashMap<>();
		int rows = 0;
		for (int i = run.from(); i < run.to(); i++) {
			String text = LegacyText.strip(lines.get(i).getString()).trim();
			if (text.isEmpty()) {
				continue;
			}
			rows++;
			shapes.merge(shapeOf(text), 1, Integer::sum);
		}
		if (rows < 3) {
			return false;
		}
		for (Map.Entry<String, Integer> shape : shapes.entrySet()) {
			if (shape.getValue() >= 3 && shape.getValue() * 10 >= rows * 6
					&& shape.getKey().indexOf('#') >= 0) {
				return true;
			}
		}
		return false;
	}

	/**
	 * Строка-заголовок зачарования: «Growth V», «Aqua Affinity I», «Bank V».
	 *
	 * <p>⚠️ Признак чисто механический — имя и римский уровень, БЕЗ ничего больше.
	 * Одиночную такую строку от имени предмета не отличить («Sharpness I» против
	 * «Sheep Minion I»), и в проекте это уже записано в граблях. Спасает то, что
	 * заголовок засчитывается только при ДВУХ И БОЛЕЕ таких строках в одном абзаце:
	 * у имени предмета такой формы не бывает, оно в абзаце одно и стоит первым.
	 *
	 * <p>Проверено на корпусе: под признак попали 47 разных строк в 43 абзацах,
	 * и все 47 — настоящие зачарования, ни одного ложного.
	 */
	private static final Pattern ENCHANT_HEAD = Pattern.compile("^[A-Z][A-Za-z' -]*\\s[IVXLC]+$");

	/**
	 * Строка — заголовок зачарования?
	 *
	 * <p><b>Сперва спрашиваем ДАННЫЕ, а признак по форме оставляем запасным.</b>
	 * Hypixel кладёт в NBT предмета готовый список: {@code enchantments:
	 * {bane_of_arthropods:6, champion:10, sharpness:7}} — имена каноничные,
	 * уровни числами. Это факт от сервера, а не догадка по виду текста.
	 *
	 * <p>⚠️ Зачем это понадобилось. Признак «имя + римский уровень» ловит
	 * КОЛЛЕКЦИИ: «Ice IV», «Mushroom II», ступени миньонов и уровни выглядят
	 * ровно так же. В граблях записано, чем это кончилось — 179 абзацев разом
	 * потеряли соответствие, правку откатили, и там же сказано: «чинить надо
	 * с другой стороны». Вот она: у коллекции нет `enchantments`, и по данным
	 * она не пройдёт никогда.
	 *
	 * <p>⚠️ <b>Данные ДОБАВЛЯЮТ уверенности, но не отнимают её.</b> Пустой
	 * список НЕ означает «заголовков нет»: у 76 предметов из 87 собранных
	 * {@code enchantments} отсутствует вовсе, и трактуй мы это как запрет —
	 * любой предмет, чьи зачарования сервер не положил в NBT, перестал бы
	 * резаться на секции. Это регресс, а выигрыш недоказан: прежний признак
	 * на корпусе дал 47 попаданий из 47 без единого ложного.
	 *
	 * <p>Поэтому список работает как ФИЛЬТР и только когда он не пуст: если
	 * сервер перечислил зачарования предмета, то строка «Raw Mutton VIII»
	 * среди них не значится и заголовком не будет. Замер по живому дампу:
	 * строк вида «Имя IV», которые зачарованиями НЕ являются, — 1340
	 * (коллекции «Melon Slice VII», уровни «Farming Level XXIV», истребители
	 * «Revenant Horror III», эссенции). Прежний признак принимал их все.
	 *
	 * <p>⚠️ Сравниваем по БУКВАМ, без регистра и разделителей: в NBT лежит
	 * {@code bane_of_arthropods}, на экране «Bane of Arthropods VI», а
	 * {@code ULTIMATE_CHIMERA} показывается как «Ultimate Chimera V». Проверено
	 * на живых данных: из 44 имён в NBT сошлись с экраном все, что вообще
	 * встречались отдельными строками.
	 */
	private static boolean enchantHead(String line) {
		if (line.isEmpty() || !ENCHANT_HEAD.matcher(line).matches()) {
			return false;
		}
		Set<String> known = ENCHANTS.get();
		if (known == null || known.isEmpty()) {
			return true;
		}
		int space = line.lastIndexOf(' ');
		// ⚠️ Спрашиваем TermMatch.serverKnows, а не known.contains: сервер
		// пишет УЛЬТИМАТИВНЫЕ зачарования с префиксом («ultimate_wisdom»
		// против экранного «Wisdom II»), и прямая сверка их не находит.
		//
		// Игрок прислал нагрудник, где «Wisdom II» с описанием остались
		// английскими посреди переведённого блока: заголовком строка не
		// признавалась, секция не вырезалась, и КУПЛЕННЫЙ перевод —
		// он лежит в 96-paragraphs.json — не спрашивался ни разу.
		//
		// ⚠️ Это ТРЕТИЙ раз, когда правило про префикс доводят до одного места
		// и забывают про другое: сперва сверка словарей, потом справка по Alt,
		// теперь резка на секции. Признак живёт в TermMatch — звать надо его,
		// а не писать проверку заново.
		return space > 0
				&& TermMatch.serverKnows(known, bareName(line.substring(0, space)));
	}

	/** Имя без регистра и разделителей: «Bane of Arthropods» -> «baneofarthropods». */
	public static String bareName(String name) {
		StringBuilder out = new StringBuilder(name.length());
		for (int i = 0; i < name.length(); i++) {
			char symbol = name.charAt(i);
			if (Character.isLetterOrDigit(symbol)) {
				out.append(Character.toLowerCase(symbol));
			}
		}
		return out.toString();
	}

	/**
	 * Перевод абзаца ПО ОТДЕЛЬНЫМ ЗАЧАРОВАНИЯМ — запасной путь, когда целого нет.
	 *
	 * <p><b>Зачем.</b> Абзац зачарований склеивается из НАБОРА, который стоит
	 * на предмете: «Bank V + Aqua Affinity I + Growth V + Protection V» — один
	 * ключ, а «Bank V + Growth VI + Protection VI + Rejuvenate V» — уже другой.
	 * Наборов столько, сколько игроки собрали, то есть ключ у каждого предмета
	 * почти свой. Покупать перевод на каждую комбинацию — путь без дна: корпус
	 * растёт бесконечно, а на экране всё равно английский, потому что именно
	 * этого набора мы ещё не видели.
	 *
	 * <p><b>Почему это ничего не стоит.</b> Переводы ОТДЕЛЬНЫХ зачарований уже
	 * куплены и лежат в корпусе своими абзацами: «Growth VI Grants +{n} ❤
	 * Health.», «Protection VI Grants +{n} ❈ Defense.» и так далее. Значит любую
	 * комбинацию можно собрать из готовых кусков, не заплатив ни разу.
	 *
	 * <p>⚠️ Путь именно ЗАПАСНОЙ: сюда попадаем только когда перевода всего
	 * абзаца нет. Пока он есть — работает как раньше, и 6128 оплаченных
	 * переводов ничего не теряют. Ключ каждой секции строится тем же
	 * {@link #key}, что и ключ абзаца, поэтому совпадает с корпусом без правок.
	 *
	 * <p>⚠️ Секция, для которой перевода нет, остаётся КАК ПРИШЛА. Половина
	 * русского лучше, чем ничего: у Hypixel зачарования и так идут отдельными
	 * блоками, и английский блок среди русских выглядит ровно как непереведённый
	 * блок, а не как поломка.
	 *
	 * @return готовые строки или null, если собрать нечего
	 */
	private static List<Component> bySections(List<Component> lines, Run run,
			String origin, String item, int widthPx) {
		List<Integer> heads = new ArrayList<>();
		for (int i = run.from(); i < run.to(); i++) {
			String line = LegacyText.strip(lines.get(i).getString()).trim();
			if (enchantHead(line)) {
				heads.add(i);
			}
		}
		if (heads.size() < 2) {
			return null;
		}

		List<Component> out = new ArrayList<>();
		boolean translated = false;
		// Текст до первого заголовка — не наше дело, оставляем как есть.
		for (int i = run.from(); i < heads.get(0); i++) {
			out.add(lines.get(i));
		}
		for (int h = 0; h < heads.size(); h++) {
			int from = heads.get(h);
			int to = h + 1 < heads.size() ? heads.get(h + 1) : run.to();
			Run part = new Run(from, to);
			String key = key(lines, part);
			Translator.Match found = key.isEmpty()
					? null : Translator.lookupParagraph(key, origin, item);
			if (found == null) {
				for (int i = from; i < to; i++) {
					out.add(lines.get(i));
				}
				continue;
			}
			translated = true;
			List<Component> source = new ArrayList<>(lines.subList(from, to));
			// Заголовок — своей строкой, как его прислал Hypixel; остальное переносим.
			String text = found.text();
			Component headLine = header(lines, part, text, origin, item);
			if (headLine != null) {
				out.add(headLine);
				text = restBody(text, headLine.getString());
			}
			if (!text.isBlank()) {
				out.addAll(wrap(text, widthPx, lines.get(from), source));
			}
		}
		return translated ? out : null;
	}

	/**
	 * Абзац из нескольких зачарований — каждое своей строкой, как у Hypixel.
	 *
	 * <p>Обоснование и замеры — в {@link ParagraphColors#sections}. Здесь только
	 * сбор данных: какие строки абзаца являются заголовками, как каждый может
	 * выглядеть в переводе и каким стилем его красить.
	 *
	 * <p>⚠️ Цвет заголовка берём У ЕГО СТРОКИ, а не общий. В живом дампе
	 * «Aqua Affinity I» и «Protection V» синие, а «Bank V» и «Growth V» —
	 * СЕРЫЕ, как описания. То есть цветом заголовки не опознать и одним цветом
	 * их красить нельзя: надо отдать каждому стиль его собственной строки.
	 *
	 * @param headTaken первую строку уже забрал {@link #header} — второй раз её
	 *                  в заголовки не берём
	 * @return готовые строки или null, если это не абзац зачарований
	 */
	private static List<Component> sectioned(List<Component> lines, Run run, String text,
			String origin, String item, int widthPx, List<Component> original,
			boolean headTaken) {
		List<Component> heads = new ArrayList<>();
		List<List<String>> variants = new ArrayList<>();
		int first = run.from() + (headTaken ? 1 : 0);
		int total = 0;
		for (int i = run.from(); i < run.to(); i++) {
			String line = LegacyText.strip(lines.get(i).getString()).trim();
			if (!enchantHead(line)) {
				continue;
			}
			total++;
			if (i < first) {
				// этот заголовок уже вырезал header — второй раз не берём
				continue;
			}
			List<String> group = new ArrayList<>(2);
			group.add(line);
			Translator.Match own = Translator.lookup(line, origin, item);
			if (own != null) {
				group.add(own.text());
			}
			heads.add(lines.get(i));
			variants.add(group);
		}
		// ⚠️ Признак «это абзац ЗАЧАРОВАНИЙ» — не меньше двух заголовков — считаем
		// по ВСЕМУ абзацу, а режем только то, что осталось после header.
		//
		// Раньше порог стоял на списке ПОСЛЕ вычета забранного заголовка, и абзац
		// ровно из двух зачарований не резался вовсе: первое («Growth V») вставало
		// своей строкой, второе («Защита V») слипалось с описанием предыдущего —
		// «Даёт +75 ❤ к здоровью. Защита V Даёт +20 ❈ к защите.» На экране это
		// худший из видов: половина абзаца разложена верно, половина сплошняком,
		// и выглядит как случайный сбой.
		//
		// Ослабить сам признак нельзя: одиночная строка «Sharpness I» неотличима
		// от имени предмета «Sheep Minion I» — это записанная грабля, и правка
		// по ней уже стоила проекту 179 абзацев.
		if (total < 2 || heads.isEmpty()) {
			return null;
		}

		List<ParagraphColors.Section> found = ParagraphColors.sections(text, variants);
		// ⚠️ Порог найденных секций оставляем прежним там, где header ничего
		// не забирал: старый путь не меняется вовсе. А когда заголовок уже
		// отрезан, одной секции достаточно — их и осталось столько.
		if (found.size() < (headTaken ? 1 : 2)) {
			return null;
		}

		List<Component> out = new ArrayList<>();
		// Хвост описания, оставшийся ПЕРЕД первым найденным заголовком: он
		// принадлежит предыдущему зачарованию (или вступлению абзаца).
		int firstAt = found.get(0).at();
		if (firstAt > 0) {
			String intro = text.substring(0, firstAt).strip();
			if (!intro.isEmpty()) {
				out.addAll(wrap(intro, widthPx, lines.get(run.from()), original));
			}
		}
		for (int i = 0; i < found.size(); i++) {
			ParagraphColors.Section part = found.get(i);
			int bodyFrom = part.at() + part.length();
			int bodyTo = i + 1 < found.size() ? found.get(i + 1).at() : text.length();
			if (bodyFrom > text.length()) {
				break;
			}
			out.add(Component.literal(text.substring(part.at(), Math.min(bodyFrom, text.length())).strip())
					.setStyle(styleOf(heads.get(i))));
			if (bodyTo > bodyFrom) {
				String body = text.substring(bodyFrom, Math.min(bodyTo, text.length())).strip();
				if (!body.isEmpty()) {
					out.addAll(wrap(body, widthPx, heads.get(i), original));
				}
			}
		}
		return out.isEmpty() ? null : out;
	}

	/**
	 * ПРИМЕЧАНИЕ в конце абзаца — своей строкой, как его прислал Hypixel.
	 *
	 * <p>«§8The pet must be visible to apply the item!» стоит последней строкой
	 * под описанием и пустой строкой от него не отделено — значит для нас это
	 * тот же абзац. После склейки приписка втекала в текст сплошняком, и пауза,
	 * которую делал Hypixel, пропадала.
	 *
	 * <p>Режем уже НАЙДЕННЫЙ перевод, поэтому ключ не меняется. Признаки те же,
	 * что у заголовка: цвет отличается от тела и перевод кончается припиской.
	 */
	private static int footerStart(List<Component> lines, Run run, String translated,
			String origin, String item) {
		if (run.size() < 2) {
			return -1;
		}
		Component last = lines.get(run.to() - 1);
		String tail = LegacyText.strip(last.getString()).trim();
		if (tail.isEmpty()) {
			return -1;
		}
		List<String> variants = new ArrayList<>(2);
		variants.add(tail);
		Translator.Match own = Translator.lookup(tail, origin, item);
		if (own != null) {
			variants.add(own.text());
		}

		Map<String, Style> palette = new LinkedHashMap<>();
		List<ParagraphColors.Piece> pieces = piecesOf(
				new ArrayList<>(lines.subList(run.from(), run.to())),
				lines.get(run.from()).getStyle(), palette);
		String body = ParagraphColors.body(pieces);

		// ⚠️ РАЗМЕЧЕННЫЙ перевод режем по его же кодам, а не по тексту.
		//
		// Сравнение с вариантами тут не работает: перевод несёт §-коды
		// («…в любое время! §8Питомец должен быть виден…§7»), а варианты чистые,
		// и хвост не совпадает никогда. Зато разметка уже сделала главное —
		// пометила приписку своим цветом. Значит граница известна точно:
		// последний §-код, отличный от цвета тела.
		if (LegacyText.hasCodes(translated)) {
			return markedTailStart(translated);
		}

		int cut = ParagraphColors.footerCut(leadingColor(last), body, translated, variants);
		if (cut <= 0 || cut >= translated.strip().length()) {
			return -1;
		}
		return translated.strip().length() - cut;
	}

	/**
	 * Где в РАЗМЕЧЕННОМ переводе начинается приписка своим цветом.
	 *
	 * <p>Ищем с конца: последний участок, покрашенный НЕ цветом тела и тянущийся
	 * до самого конца строки. Если такого нет — резать нечего.
	 *
	 * @return позиция §-кода приписки или -1
	 */
	private static final java.util.regex.Pattern CODE =
			java.util.regex.Pattern.compile("§.");

	/**
	 * Где кончается ЗАГОЛОВОК в размеченном переводе — или -1.
	 *
	 * <p>Зеркало {@link #markedTailStart}: разметка ставит первым кодом цвет
	 * ТЕЛА, а заголовок помечает своим. Значит заголовок — это первый кусок
	 * иного цвета, и кончается он там, где цвет возвращается к телу.
	 *
	 * <p>⚠️ Возвращаем ПОЗИЦИЮ в строке, а не длину текста: в размеченной
	 * строке заголовок занимает больше знаков, чем его текст, — вместе
	 * с §-кодами. На этом уже обожглись с припиской: вычитая длину текста,
	 * получали хвост от последнего слова отдельной строкой.
	 */
	private static int markedHeadEnd(String translated) {
		// Логика живёт в ParagraphColors — там чистая логика без Minecraft,
		// и её можно прогнать настоящей Java БЕЗ игры (check_headers.py).
		// Пока правило сидело здесь, проверить его было нечем, и съехавший
		// заголовок находил игрок глазами на скриншоте.
		return ParagraphColors.markedHeadEnd(translated);
	}

	private static int markedTailStart(String translated) {
		// Цвет ТЕЛА размеченный перевод несёт первым кодом — его ставит разметка
		// (color_lore.wrap_spans), и им же возвращается текст после каждого куска.
		if (!translated.startsWith("§") || translated.length() < 2) {
			return -1;
		}
		String bodyCode = translated.substring(0, 2);
		java.util.regex.Matcher codes = CODE.matcher(translated);
		int lastOther = -1;
		while (codes.find()) {
			String code = codes.group();
			// модификаторы (§l жирный, §o курсив) цвет не меняют — приписку не начинают
			if ("klmnor".indexOf(Character.toLowerCase(code.charAt(1))) >= 0) {
				continue;
			}
			// ⚠️ Код БЕЗ текста после себя пропускаем: разметка закрывает каждый
			// кусок цветом тела, и такой хвостовой «§7» в самом конце строки
			// обнулял находку — приписка переставала находиться вовсе.
			if (CODE.matcher(translated.substring(codes.end())).replaceAll("").isBlank()) {
				continue;
			}
			lastOther = code.equals(bodyCode) ? -1 : codes.start();
		}
		return lastOther;
	}

	/**
	 * Записывает раскраску абзаца в дамп — набор случаев для проверки без игры.
	 *
	 * <p>Это ровно тот приём, что уже спас правило склейки: логика вынесена
	 * в класс без Minecraft ({@link ParagraphColors}), а живые случаи копятся
	 * в дампе, и {@code tools/check_paragraph_colors.py} прогоняет по ним ту же
	 * логику ДО сборки. Без записи проверять было бы нечего: цвет живёт стилями
	 * компонента и в обычный дамп не попадает.
	 */
	private static void noteColors(String key, List<Component> original, Style base,
			String translated, String item) {
		Map<String, Style> palette = new LinkedHashMap<>();
		List<ParagraphColors.Piece> pieces = piecesOf(original, base, palette);
		List<String> colors = new ArrayList<>(pieces.size());
		List<String> texts = new ArrayList<>(pieces.size());
		for (ParagraphColors.Piece piece : pieces) {
			colors.add(piece.color());
			texts.add(piece.text());
		}
		UnknownStrings.recordParagraphColors(key, colors, texts, translated, item);
	}

	/**
	 * Куски исходного абзаца: текст и его цвет.
	 *
	 * <p>⚠️ Каждую строку сперва прогоняем через {@link LegacyText#parse}, и это
	 * не лишний шаг: цвет приходит ДВУМЯ путями. В боковой панели и чате Hypixel
	 * пишет §-код внутри текста, а подсказку предмета собирает сам Minecraft —
	 * там цвет лежит в стиле компонента. Разбор приводит оба пути к одному виду.
	 *
	 * @param palette попутно запоминаем, каким стилем красить цвет с таким именем:
	 *                разбирать имя обратно в {@code TextColor} не нужно
	 */
	/**
	 * Стиль строки — по её ПЕРВОМУ КУСКУ, а не по корню.
	 *
	 * <p>⚠️ {@code getStyle()} отдаёт стиль КОРНЯ компонента, а весь цвет
	 * и начертание Hypixel вешает на КУСКИ. В проекте это уже записано
	 * (из-за той же ошибки в {@code piecesOf} каждая строка давала один кусок,
	 * а описание «Automated Shipping» уезжало в фиолетовый) — но в резке
	 * секций осталось.
	 *
	 * <p>Чем это видно на экране: у корня цвета нет, поэтому серое описание
	 * зачарования выходило БЕЛЫМ, а флаги вроде жирности подхватывались
	 * по наследству от родителя — в оригинале их нет вовсе (проверено
	 * по {@code dump/paragraph-colors.json}: у «Bank V» все куски «gray»,
	 * пометки «+b» нет ни одной).
	 *
	 * <p>Пустая строка или строка без кусков — возвращаем корень, хуже
	 * от этого не станет.
	 */
	private static Style styleOf(Component line) {
		Style[] first = {null};
		line.visit((style, text) -> {
			if (first[0] == null && !text.isBlank()) {
				first[0] = style;
			}
			return Optional.empty();
		}, Style.EMPTY);
		return first[0] == null ? line.getStyle() : first[0];
	}

	private static List<ParagraphColors.Piece> piecesOf(List<Component> source, Style base,
			Map<String, Style> palette) {
		List<ParagraphColors.Piece> out = new ArrayList<>();
		for (Component line : source) {
			// ⚠️ Обходим строку ПО КУСКАМ (visit), а не берём её текст целиком.
			// Сперва тут стояло LegacyText.parse(line.getString(), line.getStyle()) —
			// и это молча теряло все цвета: getString() склеивает текст без стилей,
			// а getStyle() отдаёт стиль КОРНЯ, а не кусков. Каждая строка давала
			// ровно один кусок, телом абзаца становился цвет корня, и описание
			// «Automated Shipping» уезжало в фиолетовый, которого в оригинале нет.
			line.visit((style, text) -> {
				if (text.isBlank()) {
					return Optional.empty();
				}
				// §-коды внутри куска разбираем дополнительно: в подсказке цвет
				// приходит стилем, а в чате и панели — кодом внутри текста.
				LegacyText.parse(text, style).visit((inner, part) -> {
					if (!part.isBlank()) {
						TextColor color = inner.getColor();
						String name = color == null ? "" : color.serialize();
						palette.putIfAbsent(name, inner);
						out.add(new ParagraphColors.Piece(part, name));
					}
					return Optional.empty();
				}, style);
				return Optional.empty();
			}, base);
		}
		return out;
	}


	/**
	 * Убирает из куска первую строку, если это ИМЯ ПРЕДМЕТА.
	 *
	 * <p>В подсказке имя стоит первой строкой и пустой строкой от описания
	 * не отделено — значит {@link #runs} склеит его с первым абзацем. А дальше
	 * беда: перенос абзаца размажет имя по прозе, оно потеряет свою строку
	 * и свой цвет. По именам ищут вещи на аукционе, трогать их нельзя вовсе.
	 *
	 * <p>Признак не гадательный: у подсказки предмета первая строка — это
	 * отображаемое имя, оно же приходит к нам в {@code item}.
	 *
	 * @return кусок без имени, либо null — если после имени переносить нечего
	 */
	private static Run nameAside(List<Component> lines, Run run, String item) {
		if (run.from() != 0 || item == null || item.isBlank()) {
			return run;
		}
		String first = LegacyText.strip(lines.get(0).getString()).trim();
		if (!first.equals(LegacyText.strip(item).trim())) {
			return run;
		}
		// ⚠️ ЗДЕСЬ ХОЧЕТСЯ СДЕЛАТЬ ИСКЛЮЧЕНИЕ ДЛЯ КНИГИ ЗАЧАРОВАНИЯ — НЕ НАДО.
		//
		// У книги имя предмета и заголовок абзаца совпадают («Aqua Affinity I»),
		// поэтому отрезание имени оставляет голое «Increases your underwater
		// mining rate.», а в корпусе абзац лежит ВМЕСТЕ с заголовком — перевод
		// есть, но мод его не спрашивает. Соблазн понятен: не отрезать имя,
		// если оно выглядит как «название + римский уровень».
		//
		// Пробовал — стало хуже. Под этот признак попадают предметы коллекций
		// («Ice IV», «Mushroom II»), уровни и миньоны: 179 абзацев разом
		// потеряли соответствие. Это та же грань, что уже записана в граблях:
		// «Sharpness I» и «Sheep Minion I» по одиночной строке не отличить.
		//
		// Чинить надо с другой стороны — переводом описаний зачарований
		// отдельными ключами (tools/split_enchant_sections.py), а не признаком
		// по форме имени.
		Run without = new Run(1, run.to());
		return without.size() >= MIN_LINES ? without : null;
	}

	/**
	 * Цвет, с которого строка НАЧИНАЕТСЯ.
	 *
	 * <p>⚠️ Цвет приходит ДВУМЯ путями, и знать надо оба.
	 *
	 * <p>В боковой панели и в чате Hypixel пишет §-код прямо в текст — это
	 * записано в граблях и проверено дампом. А вот подсказку предмета собирает
	 * сам Minecraft, и цвет там лежит в СТИЛЕ компонента; §-кодов может
	 * не быть вовсе. Мы смотрели только на коды — и в магазине пара
	 * «Cost» серый / «10 Coins» золотой выглядела одноцветной: кусок
	 * склеивался в абзац, а перенос красил всё серым цветом первой строки.
	 * Золото пропадало, и счётчик потери цвета об этом даже не знал.
	 *
	 * <p>Обе стороны приводим к одному виду — названию цвета, — иначе
	 * «§7Текст» и такой же серый из стиля считались бы разными цветами
	 * и абзацы перестали бы переводиться вообще.
	 *
	 * @return название цвета, либо "" — цвет по умолчанию
	 */
	/**
	 * Стиль ПЕРВОГО КУСКА строки, а не корня.
	 *
	 * <p>⚠️ {@code getStyle()} отдаёт стиль КОРНЯ компонента, и у подсказки он
	 * обычно пуст: цвет лежит на кусках. Именно поэтому заголовок «Tiered Bonus»
	 * оставался серым — стиль, которым мы его красили, не нёс цвета вовсе.
	 * Та же грабля уже стоила проекту фиолетового описания «Automated Shipping».
	 */
	private static Style firstPieceStyle(Component line) {
		return line.<Style>visit((style, text) ->
						text.isBlank() ? Optional.empty() : Optional.of(style),
				Style.EMPTY).orElse(line.getStyle());
	}

	private static String leadingColor(Component line) {
		// §-код рисуется поверх стиля начиная со своего места, поэтому
		// ведущий код и есть цвет первой буквы.
		//
		// Через TextColor, а не через имя самого кода: так обе ветки дают
		// ОДНУ И ТУ ЖЕ строку для одного цвета, и «§7» не считается отличным
		// от серого, пришедшего стилем. Жирный и курсив сюда не попадают —
		// fromLegacyFormat отдаёт для них null, и мы идём дальше по коду.
		String codes = LegacyText.leadingCodes(line.getString());
		for (int i = 0; i + 1 < codes.length(); i += 2) {
			ChatFormatting format = ChatFormatting.getByCode(codes.charAt(i + 1));
			TextColor color = format == null ? null : TextColor.fromLegacyFormat(format);
			if (color != null) {
				return color.serialize();
			}
		}
		// кода нет — цвет пришёл стилем компонента
		return line.visit((style, text) -> {
			if (text.isBlank()) {
				return Optional.empty();
			}
			TextColor color = style.getColor();
			return Optional.of(color == null ? "" : color.serialize());
		}, Style.EMPTY).orElse("");
	}

	/**
	 * Цвета строк куска, по одному на строку.
	 *
	 * <p>Отдельным шагом, потому что решение по ним принимает {@link ColorLayout},
	 * который про Minecraft не знает вовсе — и потому проверяется без игры.
	 */
	private static List<String> colorsOf(List<Component> lines, Run run) {
		List<String> out = new ArrayList<>(run.size());
		for (int i = run.from(); i < run.to(); i++) {
			// «!» на конце — внутри строки цвет МЕНЯЕТСЯ. Это отличает прозу
			// с подсвеченным словом от размеченной пары: у пары каждая строка
			// одноцветна целиком. Признак нужен решению, поэтому едет вместе
			// с цветом одной строкой — так его видит и запись в дамп.
			out.add(leadingColor(lines.get(i)) + (uniform(lines.get(i)) ? "" : "!"));
		}
		return out;
	}

	/**
	 * Абзац-СПИСОК: каждый пункт своей строкой, как его прислал Hypixel.
	 *
	 * <p><b>Зачем.</b> Список склеивать нельзя — пункты размажутся в сплошную
	 * строку. Но {@code apply} при отказе ВЫБРАСЫВАЛ найденный перевод совсем,
	 * и на живом корпусе так лежат мёртвым грузом 301 оплаченный перевод: на
	 * экране английский текст, за который заплачено.
	 *
	 * <p>Обоснование резки и замеры — в {@link ParagraphColors#listCuts}. Здесь
	 * только сбор данных: где маркеры и каким стилем красить каждый пункт.
	 *
	 * <p>⚠️ <b>Если ВСЕ строки переводятся построчно — не вмешиваемся.</b>
	 * Так устроен фильтр сортировки («▶ A to Z / Z to A / Lowest Rarity»):
	 * каждая его строка лежит в словаре отдельной записью, построчный путь
	 * переводит их точнее, и подменять его разрезанным абзацем незачем.
	 * Резка нужна там, где построчного перевода НЕТ — иначе строка останется
	 * английской, хотя перевод куплен.
	 *
	 * <p>⚠️ Стиль пункта берём У ЕГО СТРОКИ, а не общий на всех: у списка
	 * выбора выбранный пункт покрашен иначе прочих, и заливка одним цветом
	 * стёрла бы ровно тот признак, ради которого Hypixel его красит.
	 *
	 * @param markers знаки строк абзаца по порядку — те же, по которым
	 *                {@link ColorLayout} и отказал в склейке
	 * @return готовые строки или null, если резать нечего или незачем
	 */
	private static List<Component> listed(List<Component> lines, Run run, String text,
			List<String> markers, String origin, String item, int widthPx,
			List<Component> original) {
		boolean gap = false;
		for (int i = run.from(); i < run.to(); i++) {
			String line = LegacyText.strip(lines.get(i).getString()).strip();
			if (!line.isEmpty() && Translator.lookup(line, origin, item) == null) {
				gap = true;
				break;
			}
		}
		if (!gap) {
			return null;
		}

		// ⚠️ Режем ТОЛЬКО по тому знаку, из-за которого абзац и признан списком.
		// Брать все маркеры подряд нельзя: markersOf считает маркером любой
		// не-буквенный символ, и туда попадают «{» от дырки «{n}» и «(» от
		// скобки — резка по ним разложила бы пункты по случайным местам.
		// Поймала это проверка check_list_cuts.py: «ждали „{“, а кусок
		// начинается „n}:§e {n}%“».
		String mark = ColorLayout.repeatedMarker(markers);
		// ⚠️ Резать можно только по НАСТОЯЩЕМУ списочному знаку. Для отказа
		// в склейке годится любой повторяющийся («{» у строк «{n} частей:»,
		// «-» у дефиса), и это правильно: ошибка там дёшева — строки переведутся
		// построчно. А разрез по «{» уехал бы в середину фразы, потому что дырка
		// «{n}» встречается и там. Разницу объясняет ColorLayout.listMark.
		if (mark == null || !ColorLayout.cutMark(mark)) {
			return null;
		}
		// ⚠️ Режем по ВСЕМ списочным знакам куска, а не по одному повторяющемуся.
		//
		// Список бывает помечен ДВУМЯ знаками разом: у бонуса сезонов Hypixel
		// ставит «✦» текущему сезону и «✧» остальным трём. Беря только
		// повторяющийся, мы резали по «✧» и приклеивали текущий сезон к чужому
		// пункту — на экране «✧ Autumn» и «✦ Winter» слипались в одну строку.
		// Тот же случай, что «▶» у выбранного пункта фильтра, только знака два.
		//
		// Прочие знаки (буквы, «{», «-») сюда не попадают: каждый проходит
		// через cutMark, то есть должен быть маркером выбора или значком
		// приватной зоны.
		// ⚠️ Маркер ищем ВМЕСТЕ С ПРОБЕЛОМ, если он стоял за ним в оригинале.
		//
		// Знак «+» помечает пункт перечня («+ Start with a Grappling Hook»),
		// но он же значит «плюс» перед числом («+ +20✯ Magic Find»). Поиск
		// маркеров идёт ПО ПОРЯДКУ, каждый следующий правее предыдущего, —
		// и второй «+» внутри «+20» перехватывал очередь: разрез уезжал
		// в середину, на экране появлялся пустой пункт «+», число вставало
		// своей строкой, а хвост перечня слипался в одну кашу.
		// Игрок прислал это скриншотом меню привилегий Bingo.
		//
		// «Маркер + пробел» отличает их точно: у пункта за знаком идёт пробел,
		// у числа — цифра. Признак берём ИЗ ОРИГИНАЛА, а не угадываем.
		List<String> only = new ArrayList<>(markers.size());
		for (int i = 0; i < markers.size(); i++) {
			String marker = markers.get(i);
			if (!ColorLayout.cutMark(marker)) {
				only.add("");
				continue;
			}
			String line = LegacyText.strip(lines.get(run.from() + i).getString()).strip();
			only.add(line.startsWith(marker + " ") ? marker + " " : marker);
		}

		List<Integer> cuts = ParagraphColors.listCuts(text, only);
		// Один маркер в самом начале резать нечего: пункт всего один.
		if (cuts.isEmpty() || (cuts.size() == 1 && cuts.get(0) == 0)) {
			return null;
		}

		List<Component> owners = new ArrayList<>();
		for (int i = 0; i < only.size() && run.from() + i < run.to(); i++) {
			if (!only.get(i).isEmpty()) {
				owners.add(lines.get(run.from() + i));
			}
		}

		List<Component> out = new ArrayList<>();
		// Вступление перед первым пунктом («Примеры:», «Требование:») — своей строкой.
		int firstAt = cuts.get(0);
		if (firstAt > 0) {
			String intro = text.substring(0, firstAt).strip();
			if (!intro.isEmpty()) {
				// ⚠️ ВСТУПЛЕНИЕ СПИСКА тоже начинается с ЗАГОЛОВКА, и его надо
				// отделить своей строкой — как у обычного абзаца. У Hypixel
				// «Full Set Bonus: Vivacious Darkness (0/4)» стоит отдельно,
				// а описание («Costs 2⸎ Soulflow per 5s in combat…») под ним.
				// Без этого они слипались: резка списка делит только ПУНКТЫ,
				// а всё до первого маркера уходило одним куском.
				Component headLine = header(lines, run, intro, origin, item);
				if (headLine != null) {
					out.add(headLine);
					intro = restBody(intro, headLine.getString());
				}
				if (!intro.isBlank()) {
					out.addAll(wrap(intro, widthPx, lines.get(run.from()), original));
				}
			}
		}
		for (int i = 0; i < cuts.size(); i++) {
			int to = i + 1 < cuts.size() ? cuts.get(i + 1) : text.length();
			if (cuts.get(i) >= text.length()) {
				break;
			}
			String piece = text.substring(cuts.get(i), Math.min(to, text.length())).strip();
			if (piece.isEmpty()) {
				continue;
			}
			Component owner = i < owners.size() ? owners.get(i) : lines.get(run.from());
			out.addAll(wrap(piece, widthPx, owner, original));
		}
		return out.isEmpty() ? null : out;
	}

	/**
	 * Знак в начале каждой строки — если это НЕ буква и не цифра.
	 *
	 * <p>Одинаковый знак у нескольких строк («✔», «▶», «◼») означает СПИСОК,
	 * а список нельзя склеивать в абзац ни при каком цвете: перенос размажет
	 * пункты в сплошной текст. Буквы и цифры сюда не идут — под такое правило
	 * попала бы обычная проза.
	 */
	private static List<String> markersOf(List<Component> lines, Run run) {
		List<String> out = new ArrayList<>(run.size());
		for (int i = run.from(); i < run.to(); i++) {
			String text = LegacyText.strip(lines.get(i).getString()).trim();
			out.add(text.isEmpty() || !isMarkerChar(text.charAt(0))
					? "" : text.substring(0, 1));
		}
		return out;
	}

	/**
	 * Годится ли символ в маркер строки.
	 *
	 * <p>⚠️ «Не буква и не цифра» — признак НЕПОЛНЫЙ. Hypixel берёт под значки
	 * буквы чужих алфавитов: у удочки крючок, леска и грузило помечены «ථ»
	 * (сингальская), «ꨃ» (чамская) и «࿉» (тибетский знак) — в его шрифте это
	 * картинки, а для Java первые две обычные БУКВЫ. Маркер не опознавался,
	 * три строки склеивались в две, и на экране выходило
	 * «◎ Крючок НЕТ ✧ Леска НЕТ / ◉ Грузило НЕТ» вместо трёх строк.
	 *
	 * <p>Расширяем узко: латиница, кириллица и цифры маркером не считаются
	 * по-прежнему — иначе под правило попала бы обычная проза.
	 */
	private static boolean isMarkerChar(char symbol) {
		if (Character.isDigit(symbol) || Character.isWhitespace(symbol)) {
			return false;
		}
		if (!Character.isLetter(symbol)) {
			return true;
		}
		Character.UnicodeScript script = Character.UnicodeScript.of(symbol);
		return script != Character.UnicodeScript.LATIN
				&& script != Character.UnicodeScript.CYRILLIC
				&& script != Character.UnicodeScript.COMMON;
	}

	/**
	 * Остаток перевода после отрезанного заголовка — СО СВОИМ цветом.
	 *
	 * <p>⚠️ Рез идёт по длине заголовка, и §-код, стоявший сразу за ним,
	 * уходит ВНУТРЬ заголовка. Остаток остаётся голым и красится базовым
	 * стилем, то есть цветом ПЕРВОЙ строки — а первой стоит заголовок:
	 * <pre>
	 *   перевод: §9Защита V§7 Даёт §a+20❈ к защите§7.
	 *   заголовок: «§9Защита V§7»      остаток: « Даёт §a+20…»  ← кода нет
	 *   на экране: «Даёт» СИНЕЕ, хотя у Hypixel «Grants» серое
	 * </pre>
	 * Возврат к телу как раз и есть последний код заголовка — его и ставим
	 * в начало остатка. У заголовка без возврата («§7Growth V») это тот же
	 * серый, так что правка ничего не меняет там, где и так было верно.
	 */
	private static String restBody(String translated, String head) {
		String rest = afterHead(translated, head);
		if (rest.isEmpty() || rest.startsWith(String.valueOf(ChatFormatting.PREFIX_CODE))) {
			return rest;
		}
		// ⚠️ Код возврата ищем в ИСХОДНОМ переводе, а не в строке заголовка.
		//
		// Заголовок к этому месту уже ПЕРЕКРАШЕН (ведущие коды сняты, чтобы цвет
		// пришёл от сервера), и его последний код может исчезнуть вовсе. Раньше
		// брали именно оттуда — и «Даёт» снова посинело у всех зачарований
		// с цветным заголовком: «§9Защита V§7 Даёт…» теряло тот самый §7.
		// В самом переводе он на месте, надо только знать границу.
		String source = translated.strip();
		int end = ParagraphColors.headEnd(source, head);
		String last = "";
		for (int i = 0; i + 1 < end; i++) {
			if (source.charAt(i) == ChatFormatting.PREFIX_CODE) {
				last = source.substring(i, i + 2);
			}
		}
		return last.isEmpty() ? rest : last + rest;
	}

	/**
	 * Что осталось от перевода после заголовка — считаем по ЗНАЧИМЫМ знакам.
	 *
	 * <p>⚠️ Раньше резали по ДЛИНЕ строки заголовка, и это сломалось, как только
	 * заголовок стал перекрашиваться: подмена ведущих кодов меняет длину, а рез
	 * остаётся прежним. У «§7§6Способность: Cleave» снятие четырёх знаков кода
	 * сдвинуло границу — и в описание уехал хвост слова:
	 * <pre>
	 *   Способность: Cleave
	 *   eave При ударе по существу…      &lt;- «Cl» осталось в заголовке
	 * </pre>
	 * Игрок прислал это скриншотом. Длина кодов вообще не должна влиять
	 * на границу, поэтому считаем ЗНАЧИМЫЕ знаки заголовка и пропускаем
	 * столько же в переводе, а коды по дороге проглатываем.
	 */
	private static String afterHead(String translated, String head) {
		return ParagraphColors.afterHead(translated, head);
	}

	/**
	 * Базовый стиль абзаца без ЖИРНОСТИ и КУРСИВА заголовка.
	 *
	 * <p>Базовый стиль берётся у ПЕРВОЙ строки — а первой обычно стоит
	 * заголовок, и у зачарований он жирный («§lWisdom V»). Дальше этот стиль
	 * применяется ко всему абзацу, и описание тоже выходит жирным: игрок
	 * прислал шлем, где так «поехал» весь текст под «Wisdom V».
	 *
	 * <p>Снимаем ТОЛЬКО когда помеченного меньше половины: у строки, целиком
	 * набранной жирным (предупреждения Hypixel), всё остаётся как было.
	 * Тот же приём и тот же порог, что у {@code TextTranslator.dropOddModifiers},
	 * где так же снимается зачёркивание рамки.
	 */
	private static Style dropHeadModifiers(Style base, List<Component> source) {
		if (!base.isBold() && !base.isItalic()) {
			return base;
		}
		int[] all = {0};
		int[] bold = {0};
		int[] italic = {0};
		for (Component line : source) {
			line.visit((style, text) -> {
				String core = text.strip();
				if (core.isEmpty()) {
					return Optional.empty();
				}
				all[0] += core.length();
				if (style.isBold()) {
					bold[0] += core.length();
				}
				if (style.isItalic()) {
					italic[0] += core.length();
				}
				return Optional.empty();
			}, Style.EMPTY);
		}
		if (all[0] == 0) {
			return base;
		}
		Style out = base;
		if (base.isBold() && bold[0] * 2 < all[0]) {
			out = out.withBold(false);
		}
		if (base.isItalic() && italic[0] * 2 < all[0]) {
			out = out.withItalic(false);
		}
		return out;
	}

	/** Строка целиком одного цвета? */
	private static boolean uniform(Component line) {
		java.util.List<String> seen = new ArrayList<>();
		line.visit((style, text) -> {
			if (!text.isBlank()) {
				TextColor color = style.getColor();
				seen.add(color == null ? "" : color.serialize());
			}
			return Optional.empty();
		}, Style.EMPTY);
		if (seen.stream().distinct().count() > 1) {
			return false;
		}
		// §-коды внутри текста visit не видит: цвет там живёт в самой строке
		String raw = line.getString();
		int codes = 0;
		for (int i = 0; i + 1 < raw.length(); i++) {
			if (raw.charAt(i) == ChatFormatting.PREFIX_CODE && TextColor.fromLegacyFormat(
					ChatFormatting.getByCode(raw.charAt(i + 1))) != null) {
				codes++;
			}
		}
		return codes <= (LegacyText.leadingCodes(raw).isEmpty() ? 0 : 1);
	}

	/** Ширина самой длинной строки абзаца — её и держим. */
	public static int width(List<Component> lines, Run run) {
		Font font = Minecraft.getInstance().font;
		int widest = 0;
		// ⚠️ Ширину берём по ВСЕЙ подсказке, а не по одному абзацу.
		//
		// Раньше считали только строки самого абзаца — и короткий абзац зажимал
		// перевод в свои узкие рамки. Живой пример: в магазине «Cost» / «18 Coins»
		// две короткие строки, а «Стоимость: 18 монет» длиннее — и рассыпалось
		// на три строки лесенкой, хотя подсказка на экране широкая: её держат
		// имя предмета и строка про обмен.
		//
		// По всей подсказке — ровно тот компромисс, который нужен: окно НЕ едет
		// (эта ширина у него уже есть), но и втискивать русскую фразу в чужие
		// узкие границы больше не приходится. Ровно ради этого абзацы и делались.
		for (Component line : lines) {
			widest = Math.max(widest, font.width(line));
		}
		return widest;
	}

	/**
	 * Переводит подсказку абзацами.
	 *
	 * <p>Возвращает строки, которые СДЕЛАЛ САМ. Пустой набор — ничего не заменили.
	 *
	 * <p>Зачем набор, а не просто «да/нет»: после нас по этим же строкам идёт
	 * построчный переводчик. Наш русский текст он, понятно, не переведёт, зато
	 * запишет в дамп как «непереведённое» — и дамп после большого прогона
	 * заполнится нашим же переводом, а счётчик непереведённого раздуется.
	 * Плюс при включённом glossaryPass глоссарий залез бы внутрь готовой фразы
	 * и подменил бы имя, которое мы нарочно оставили английским.
	 *
	 * <p>Сравниваем по ССЫЛКЕ, а не по индексу: замена меняет длину списка,
	 * и номера строк разъезжаются, а объект остаётся собой.
	 *
	 * <p>Идём с конца: при движении сверху вниз границы следующих кусков
	 * разъехались бы.
	 */
	public static Set<Component> apply(List<Component> lines, String origin, String item) {
		return apply(lines, origin, item, null);
	}

	/**
	 * То же, но с ДАННЫМИ о зачарованиях предмета из NBT.
	 *
	 * @param enchants нормализованные имена зачарований, которые сервер
	 *                 объявил у этого предмета, либо <b>null</b>, если NBT
	 *                 прочитать не удалось. Разница важна: пустой набор значит
	 *                 «зачарований нет» (и заголовков быть не может), а null —
	 *                 «не знаем», и тогда работает прежний признак по форме.
	 */
	public static Set<Component> apply(List<Component> lines, String origin, String item,
			Set<String> enchants) {
		ENCHANTS.set(enchants);
		try {
			return applyInner(lines, origin, item);
		} finally {
			ENCHANTS.remove();
		}
	}

	/**
	 * Зачарования текущего предмета — на время разбора одной подсказки.
	 *
	 * <p>Через ThreadLocal, а не параметром: признак заголовка спрашивают
	 * {@code bySections} и {@code sectioned} из глубины разбора, и тащить
	 * набор через шесть сигнатур значило бы переписать их все ради одного
	 * поля. Подсказка строится в клиентском потоке и целиком, поэтому
	 * значение живёт ровно один вызов и снимается в finally.
	 */
	private static final ThreadLocal<Set<String>> ENCHANTS = new ThreadLocal<>();

	private static Set<Component> applyInner(List<Component> lines, String origin, String item) {
		Set<Component> made = Collections.newSetFromMap(new IdentityHashMap<>());

		// ⚠️ Выключатель и «только на Hypixel/в SkyBlock» проверяем ЗДЕСЬ ТОЖЕ.
		//
		// Их проверял только построчный переводчик, а абзацы шли мимо — и после
		// /skyblockru off вся подсказка становилась английской, кроме абзацев,
		// которые упрямо оставались русскими. Игрок выключил перевод, а он
		// наполовину жив: выглядит как «мод сломался», а не как «я его выключил».
		if (!ru.skyblockru.config.RuConfig.get().enabled || !Hypixel.isActive()) {
			return made;
		}

		List<Run> runs = runs(lines);
		for (int r = runs.size() - 1; r >= 0; r--) {
			Run run = nameAside(lines, runs.get(r), item);
			if (run == null) {
				continue;
			}
			String source = key(lines, run);
			if (source.isEmpty()) {
				continue;
			}
			Translator.Match match = Translator.lookupParagraph(source, origin, item);
			// ⚠️ Цвета записываем ДО проверки перевода, а не после.
			//
			// Это ИСТОЧНИК ДАННЫХ для разметки, и собирать его надо для КАЖДОГО
			// абзаца, который Hypixel показал. Раньше запись стояла ниже, после
			// «перевод найден» — то есть цвета копились только там, где мод и так
			// справлялся, а для непереведённых их не было ВОВСЕ. Ровно они и нужны:
			// пока у абзаца нет разметки, мод вынужден угадывать цвет по уцелевшим
			// кускам, и переведённое слово подсветку теряет. Чем полнее этот файл,
			// тем меньше остаётся угадывания — и тем ближе «мод не гадает никогда».
			noteColors(source, new ArrayList<>(lines.subList(run.from(), run.to())),
					lines.get(run.from()).getStyle(),
					match == null ? "" : match.text(), item);
			if (match == null) {
				// ⚠️ ЗАПАСНОЙ ПУТЬ: абзаца целиком нет, но он мог быть склеен
				// из НЕСКОЛЬКИХ зачарований, и каждое переведено по отдельности
				// ещё когда-то. Комбинаций у игроков столько, что покупать
				// перевод на каждую бессмысленно, — а собрать из готовых кусков
				// можно даром.
				List<Component> pieces = bySections(lines, run, origin, item, width(lines, run));
				if (pieces == null || pieces.isEmpty()) {
					continue;
				}
				for (int i = run.to() - 1; i >= run.from(); i--) {
					lines.remove(i);
				}
				lines.addAll(run.from(), pieces);
				made.addAll(pieces);
				continue;
			}

			// ⚠️ РАЗНОЦВЕТНЫЙ кусок не трогаем.
			//
			// Перенос склеивает абзац в одну строку и красит её кодами ПЕРВОЙ
			// строки. У прозы это незаметно — она одноцветная. А у пары
			// «подпись / значение» цвета разные: в магазине «Cost» серый,
			// а «4 Coins» золотой, и после переноса золото пропадало.
			//
			// Признак хороший, потому что это ДАННЫЕ от сервера, а не догадка
			// по виду текста: разные ведущие цвета у соседних строк — верный
			// знак, что перед нами не проза, а размеченная пара. Такие строки
			// переведёт построчный проход, и каждая сохранит свой цвет.
			List<String> colors = colorsOf(lines, run);
			List<String> markers = markersOf(lines, run);
			ColorLayout.Verdict verdict = ColorLayout.decide(
					colors, markers, ru.skyblockru.config.RuConfig.get().mergeHeaderRuns);
			// ⚠️ ТАБЛИЦУ склеивать нельзя — даже когда перевод куплен.
			//
			// «47.4% ○ 652,431 votes | Diana» и ещё четыре такие строки — это
			// столбцы, а не проза. Списочного знака у них нет, цвет одинаковый,
			// поэтому обе прежние защиты их пропускали: кусок склеивался,
			// перенос раскладывал его по ширине, и имена уезжали к чужим
			// процентам — «479,359 голосов | / Finnegan 12.3% ○ 168,974».
			//
			// Признак — ПОВТОР ФОРМЫ, а не вид текста: у трёх и более строк
			// совпадает скелет (числа и слова заменены на метки). Проверено
			// на всём корпусе: 15 кусков из 6221, и все до одного таблицы —
			// прайсы, списки мудростей, результаты выборов.
			if (verdict.merge() && looksLikeTable(lines, run)) {
				verdict = new ColorLayout.Verdict(false, "строки одной формы — это таблица");
			}
			// Раскладку пишем ВСЕГДА, не только при отказе: файл нужен как набор
			// случаев для проверки, и «что склеилось и не сломалось» в нём
			// не менее важно, чем «что защитили».
			UnknownStrings.recordColors(colors, markers, verdict.merge(), verdict.reason(), source);
			if (!verdict.merge()) {
				// ⚠️ СПИСОК — не беда, а правильный отказ: склеив его, мы бы
				// размазали пункты в сплошную строку («▶ Без фильтра Обычный
				// Необычный Редкий…»), читать это невозможно. Жаловаться на
				// такое значит слать игроку предупреждение, в котором нечего
				// чинить, а от таких перестают читать и настоящие.
				//
				// ⚠️ Но и ВЫБРАСЫВАТЬ найденный перевод не надо, а раньше он
				// выбрасывался: «пункты переводятся построчно» верно не всегда.
				// Замер по корпусу: 301 абзац-список имеет купленный перевод,
				// и у 191 из них хоть одна строка построчно НЕ закрыта — на
				// экране она оставалась английской при оплаченном переводе.
				// Режем перевод обратно по маркерам (ParagraphColors.listCuts),
				// а где построчно закрыто всё — не вмешиваемся вовсе.
				if (verdict.reason().contains("список")) {
					List<Component> items = listed(lines, run, match.text(), markers,
							origin, item, width(lines, run),
							new ArrayList<>(lines.subList(run.from(), run.to())));
					if (items != null) {
						for (int i = run.to() - 1; i >= run.from(); i--) {
							lines.remove(i);
						}
						lines.addAll(run.from(), items);
						made.addAll(items);
					}
					continue;
				}
				Diagnostics.colorGuard(source);
				continue;
			}
			int widthPx = width(lines, run);
			// Отдаём ВСЕ строки абзаца, а не только первую: из них берутся цвета
			// кусков, иначе перевод зальётся одним цветом (см. ParagraphColors).
			List<Component> original = new ArrayList<>(lines.subList(run.from(), run.to()));
			// Заголовок оставляем СВОЕЙ строкой, как его прислал Hypixel:
			// «§bSharp Attitude» над описанием, а не внутри предложения.
			// Режем уже НАЙДЕННЫЙ перевод, поэтому ключ не меняется.
			List<Component> wrapped = new ArrayList<>();
			String text = match.text();
			Component headLine = header(lines, run, text, origin, item);
			if (headLine != null) {
				wrapped.add(headLine);
				text = restBody(text, headLine.getString());
			}
			// Приписку в конце тоже отделяем — до переноса, иначе она размажется
			// по строкам вместе с прозой и паузы не останется.
			// ⚠️ Режем по ПОЗИЦИИ, а не по длине текста приписки.
			//
			// В размеченном переводе приписка занимает больше знаков, чем её
			// текст: вместе с §-кодами. Вычитая длину текста, я оставлял хвост
			// от последнего слова — на экране получалось «время! Пи» отдельной
			// строкой, а следом полная приписка.
			int tailAt = footerStart(lines, run, text, origin, item);
			Component footLine = null;
			if (tailAt > 0 && tailAt < text.length()) {
				footLine = LegacyText.parse(text.substring(tailAt),
						lines.get(run.to() - 1).getStyle());
				text = text.substring(0, tailAt).strip();
			}
			// ⚠️ Абзац из НЕСКОЛЬКИХ зачарований раскладываем ПО СЕКЦИЯМ, а не
			// сплошняком: у Hypixel каждое стоит своей строкой, а склейка втекала
			// заголовки в прозу («…при убийстве. Родство с водой I Увеличивает
			// скорость добычи под водой. Рост V Даёт…»). Режется уже НАЙДЕННЫЙ
			// перевод, поэтому ключ не меняется и платить заново не нужно.
			// Не наш случай — sectioned вернёт null, и всё идёт как раньше.
			List<Component> parts = sectioned(lines, run, text, origin, item,
					widthPx, original, headLine != null);
			if (parts != null) {
				wrapped.addAll(parts);
			} else {
				wrapped.addAll(wrap(text, widthPx, lines.get(run.from()), original));
			}
			if (footLine != null) {
				wrapped.add(footLine);
			}
			if (wrapped.isEmpty()) {
				continue;
			}
			for (int i = run.to() - 1; i >= run.from(); i--) {
				lines.remove(i);
			}
			lines.addAll(run.from(), wrapped);
			made.addAll(wrapped);
		}
		return made;
	}
}
