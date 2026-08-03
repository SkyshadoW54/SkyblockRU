package ru.skyblockru.core;

import java.util.ArrayList;
import java.util.List;

/**
 * Куда встают столбцы справки — ЧИСТАЯ АРИФМЕТИКА, без Minecraft.
 *
 * <p><b>Зачем отдельным классом.</b> Ровно затем же, зачем в проекте отдельно
 * живёт {@link ColorLayout}: логику, которую нельзя проверить без запуска игры,
 * проверить не удастся НИКОГДА — а сюда достаточно передать числа. Прогоняет её
 * настоящей Java {@code python tools/check_wiki_layout.py}, до сборки и без
 * захода в игру.
 *
 * <p><b>Что решаем.</b> На мече с двумя десятками зачарований справка не влезает
 * в один столбец. Раньше каждый столбец искал себе место сам, зная лишь «сколько
 * занято слева»; не влезший справа зажимался по краю экрана — то есть уезжал
 * ОБРАТНО ВЛЕВО, на подсказку предмета, и читались оба вперемешку.
 *
 * <p>Правило теперь одно и оно про ДАННЫЕ, а не про вид: <b>столбец не смеет
 * накрыть подсказку и не смеет вылезти за экран</b>. Если места нет — столбца
 * нет, а о непоказанном говорится вслух.
 */
public final class PanelLayout {

	private PanelLayout() {
	}

	/**
	 * Раскладка столбцов по горизонтали.
	 *
	 * <p>Варианты пробуются по порядку, побеждает первый, вместивший ВСЕ
	 * столбцы. Все три читаются слева направо, поэтому выбор между ними —
	 * вопрос свободного места, а не удобства чтения:
	 * <ol>
	 *   <li>подряд СПРАВА от подсказки — привычнее всего, окна стоят рядом;
	 *   <li>ПО БОКАМ: первый слева, второй справа, подсказка между ними;
	 *   <li>подряд СЛЕВА — когда курсор у правого края и справа места нет.
	 * </ol>
	 *
	 * <p>Не вместила ни одна — берём вместившую больше: один столбец из двух
	 * лучше, чем ни одного.
	 *
	 * @param screenWidth ширина экрана в единицах интерфейса (масштаб уже учтён)
	 * @param mainX       левый край содержимого подсказки предмета
	 * @param mainWidth   ширина содержимого подсказки предмета
	 * @param gap         просвет между окнами
	 * @param edge        отступ от края экрана
	 * @param widths      ширина содержимого каждого столбца
	 * @return X для каждого столбца; список КОРОЧЕ списка ширин, если места
	 *         хватило не всем
	 */
	public static List<Integer> place(int screenWidth, int mainX, int mainWidth,
			int gap, int edge, List<Integer> widths) {
		if (widths.isEmpty()) {
			return List.of();
		}
		int mainRight = mainX + mainWidth;
		List<List<Integer>> plans = List.of(
				run(mainRight + gap, screenWidth - edge, gap, widths),
				sides(screenWidth, mainX, mainRight, gap, edge, widths),
				leftRun(mainX, gap, edge, widths));
		List<Integer> best = List.of();
		for (List<Integer> plan : plans) {
			if (plan.size() == widths.size()) {
				return plan;
			}
			if (plan.size() > best.size()) {
				best = plan;
			}
		}
		return best;
	}

	/** Столбцы подряд слева направо от {@code from}, пока влезают до {@code until}. */
	private static List<Integer> run(int from, int until, int gap, List<Integer> widths) {
		List<Integer> out = new ArrayList<>();
		int cursor = from;
		for (int width : widths) {
			if (cursor + width > until) {
				break;
			}
			out.add(cursor);
			cursor += width + gap;
		}
		return out;
	}

	/**
	 * Всё слева от подсказки, но порядок чтения сохраняем: первый столбец —
	 * самый левый. Поэтому сперва считаем, сколько их влезет, и только потом
	 * раскладываем от левого края вправо.
	 */
	private static List<Integer> leftRun(int mainX, int gap, int edge, List<Integer> widths) {
		int total = 0;
		int fits = 0;
		for (int width : widths) {
			int grown = total == 0 ? width : total + gap + width;
			if (mainX - gap - grown < edge) {
				break;
			}
			total = grown;
			fits++;
		}
		return run(mainX - gap - total, mainX - gap, gap, widths.subList(0, fits));
	}

	/** Первый столбец слева от подсказки, второй справа — подсказка посередине. */
	private static List<Integer> sides(int screenWidth, int mainX, int mainRight,
			int gap, int edge, List<Integer> widths) {
		if (widths.size() != 2) {
			return List.of();
		}
		int left = mainX - gap - widths.get(0);
		int right = mainRight + gap;
		if (left < edge || right + widths.get(1) > screenWidth - edge) {
			return List.of();
		}
		return List.of(left, right);
	}

	/**
	 * Накрывает ли раскладка подсказку предмета — то, ради чего всё затевалось.
	 *
	 * <p>Отдельным методом, потому что проверять надо не «правильные ли числа»,
	 * а именно это свойство: на скриншоте игрока столбец лёг поверх подсказки,
	 * и с виду всё было «нарисовано».
	 */
	public static boolean overlaps(int mainX, int mainWidth, List<Integer> places,
			List<Integer> widths) {
		int mainRight = mainX + mainWidth;
		for (int i = 0; i < places.size(); i++) {
			int from = places.get(i);
			int to = from + widths.get(i);
			if (from < mainRight && to > mainX) {
				return true;
			}
		}
		return false;
	}
}
