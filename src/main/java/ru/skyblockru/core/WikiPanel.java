package ru.skyblockru.core;

import java.util.ArrayList;
import java.util.List;

import net.minecraft.client.Minecraft;
import net.minecraft.client.gui.Font;
import net.minecraft.client.gui.GuiGraphicsExtractor;
import net.minecraft.client.gui.screens.inventory.tooltip.ClientTooltipComponent;
import net.minecraft.client.gui.screens.inventory.tooltip.ClientTooltipPositioner;
import net.minecraft.client.gui.screens.inventory.tooltip.DefaultTooltipPositioner;
import net.minecraft.network.chat.Component;
import net.minecraft.util.FormattedCharSequence;
import net.minecraft.world.item.ItemStack;
import org.joml.Vector2i;
import org.joml.Vector2ic;

/**
 * Справка ОТДЕЛЬНЫМ окном СБОКУ от подсказки предмета.
 *
 * <p><b>Зачем сбоку.</b> Раньше справка дописывалась в ту же подсказку, и она
 * уезжала вниз: описание вещи и пояснение к термину сливались в один длинный
 * столбец, а на высоких подсказках аукциона нижняя часть уходила за край
 * экрана. Игрок попросил второе окно — такое же на вид, но рядом.
 *
 * <p><b>Как.</b> Рисуем ВТОРУЮ подсказку тем же ванильным механизмом, что и
 * первую ({@code GuiGraphicsExtractor.tooltip}), поэтому рамка, фон и шрифт
 * совпадают с игрой сами собой — ничего не срисовываем руками.
 *
 * <p>⚠️ Место выбирает {@link SidePositioner}: справа от основной подсказки,
 * а если там не влезает — слева. Позицию самой подсказки не угадываем,
 * а спрашиваем у ванильного {@link DefaultTooltipPositioner} — он же её
 * и ставит, значит панель приклеена к ней, а не к курсору.
 */
public final class WikiPanel {

	/**
	 * Просвет между окнами.
	 *
	 * <p>Считается от КОНТЕНТА, а не от рамки: и подсказке, и панели фон
	 * добавляет по 4 пикселя с каждой стороны, поэтому визуальный зазор
	 * получается 12 − 4 − 4 = 4 пикселя.
	 */
	private static final int GAP = 12;

	/** Отступ от края экрана, чтобы панель не липла к нему вплотную. */
	private static final int EDGE = 4;

	/**
	 * Больше двух столбцов не показываем.
	 *
	 * <p><b>Почему предел.</b> На мече с двумя десятками зачарований справка
	 * разрасталась на три-четыре столбца, и места им уже не хватало: столбец
	 * вставал ПОВЕРХ подсказки предмета, читались оба вперемешку. Игрок это
	 * и прислал скриншотом.
	 *
	 * <p>⚠️ Что не влезло — не пропадает молча: в конце последнего столбца
	 * стоит строка «…и ещё N». Молчаливое усечение выглядит как «мод знает
	 * только про эти зачарования», а это неправда и чинить такое игроку нечем.
	 */
	private static final int MAX_COLUMNS = 2;

	/**
	 * АВАРИЙНЫЙ предел ширины — не вёрстка.
	 *
	 * <p>⚠️ Строки справки уже свёрстаны РУКАМИ в {@code wiki/<язык>.json}:
	 * автор разбил их по смыслу под ширину подсказки (48–57 знаков). Резать их
	 * второй раз нельзя — выходит двойной перенос: «Особая характеристика
	 * Фермерства:» и отдельной строкой одинокое «повышает», причём справа
	 * остаётся пустое место. Ровно это и вышло на первом заходе при пределе
	 * 200 пикселей, потому что обычная строка справки шире.
	 *
	 * <p>Поэтому предел стоит ЗАВЕДОМО выше любой нормальной строки и
	 * срабатывает лишь тогда, когда строка иначе уехала бы за край экрана.
	 */
	private static final int MAX_WIDTH = 340;

	private WikiPanel() {
	}

	/**
	 * Рисует панель, если для предмета под курсором есть справка.
	 *
	 * @param hovered предмет под курсором; справка готовится при построении
	 *                подсказки, и {@link Wiki} отдаст её только для ТОГО ЖЕ
	 *                предмета — иначе показали бы пояснение от соседнего слота
	 */
	public static void render(GuiGraphicsExtractor extractor, ItemStack hovered,
	                          int mouseX, int mouseY) {
		Wiki.Panel panel = Wiki.panelFor(hovered);
		if (panel == null) {
			return;
		}
		Minecraft client = Minecraft.getInstance();
		if (client == null || client.font == null) {
			return;
		}
		Font font = client.font;

		List<FormattedCharSequence> parts = new ArrayList<>();
		List<Integer> breaks = new ArrayList<>();
		for (Component line : panel.lines()) {
			String text = line.getString();
			// ⚠️ Запоминаем, где кончается статья: резать столбец можно ТОЛЬКО
			// по этим местам. Разорванная посередине статья читается как две
			// разные, а это хуже длинного столбца.
			if (text.startsWith(SEPARATOR)) {
				breaks.add(parts.size());
			}
			if (text.isEmpty()) {
				// Пустая строка — это отступ между статьями, и переносить её
				// нечего: font.split вернул бы для неё пустой список, а отступ
				// пропал бы вместе с ним.
				parts.add(FormattedCharSequence.EMPTY);
				continue;
			}
			for (FormattedCharSequence row : font.split(line, MAX_WIDTH)) {
				parts.add(row);
			}
		}
		if (parts.isEmpty()) {
			return;
		}

		// ⚠️ Высоту экрана берём МАСШТАБИРОВАННУЮ. Игрок редко играет
		// на масштабе 1: на 2 и 3 экран в единицах интерфейса вдвое-втрое
		// ниже, и справка, которая на 1 помещалась, уезжает за край. Здесь
		// это учитывается само — считаем в тех же единицах, в каких рисуем.
		int screenHeight = client.getWindow().getGuiScaledHeight();
		int screenWidth = client.getWindow().getGuiScaledWidth();
		List<List<FormattedCharSequence>> columns =
				split(parts, breaks, screenHeight, font);

		try {
			// ⚠️ Позицию основной подсказки спрашиваем У ВАНИЛЬНОГО позиционера —
			// того самого, который её и ставит. Раньше это делал каждый столбец
			// сам внутри себя, и знать, где встал сосед, было неоткуда: второй
			// столбец не влезал справа, зажим по краю экрана двигал его обратно
			// ВЛЕВО — ровно на подсказку, — и он оказывался под ней.
			Vector2ic main = DefaultTooltipPositioner.INSTANCE.positionTooltip(
					screenWidth, screenHeight, mouseX, mouseY,
					panel.mainWidth(), panel.mainHeight());

			List<Integer> widths = new ArrayList<>();
			for (List<FormattedCharSequence> column : columns) {
				widths.add(widthOf(column, font));
			}
			List<Integer> places = PanelLayout.place(
					screenWidth, main.x(), panel.mainWidth(), GAP, EDGE, widths);

			// Не поместившийся столбец не рисуем вовсе: половина окна под чужой
			// подсказкой хуже, чем его отсутствие. Зато говорим об этом вслух.
			int shown = 0;
			for (int i = 0; i < places.size(); i++) {
				shown += columns.get(i).size();
			}
			int hidden = hiddenArticles(breaks, parts.size(), shown);
			if (hidden > 0 && !places.isEmpty()) {
				List<FormattedCharSequence> last = columns.get(places.size() - 1);
				last.add(Component
						.translatable("skyblockru.wiki.more", hidden)
						.withStyle(net.minecraft.ChatFormatting.GRAY)
						.getVisualOrderText());
			}

			// ⚠️ ЕДИНСТВЕННОЕ МЕСТО, где версии расходятся по-настоящему.
			//
			// В 1.21.6+ и 26.x отрисовка берёт List<ClientTooltipComponent>,
			// а в 1.21.5 и ниже — List<FormattedCharSequence> и позиционер
			// ПОСЛЕ списка. Ради этого весь класс и переведён на строки:
			// компоненты — обёртка над теми же строками, и оборачивать их
			// можно в последний момент, а не тащить сквозь всю раскладку.
			for (int i = 0; i < places.size(); i++) {
				var positioner = new FixedPositioner(places.get(i), main.y());
				//? if >=1.21.6 {
				List<ClientTooltipComponent> wrapped = new ArrayList<>();
				for (FormattedCharSequence row : columns.get(i)) {
					wrapped.add(ClientTooltipComponent.create(row));
				}
				extractor.tooltip(font, wrapped, mouseX, mouseY, positioner, null);
				//?} else
				/*extractor.renderTooltip(font, columns.get(i), positioner, mouseX, mouseY);*/
			}
		} catch (RuntimeException ignored) {
			// Своей панелью экран ронять нельзя: она приятная добавка,
			// а не то, ради чего игрок открыл меню.
		}
	}

	/**
	 * Сколько СТАТЕЙ не попало на экран.
	 *
	 * <p>Считаем статьи, а не строки: игроку важно «сколько зачарований я не
	 * вижу», а не «сколько строк отрезано». Начало статьи — либо самое начало
	 * справки, либо место, где стоит разделитель.
	 */
	private static int hiddenArticles(List<Integer> breaks, int total, int shown) {
		if (shown >= total) {
			return 0;
		}
		int all = breaks.size() + 1;
		int visible = 1;
		for (int point : breaks) {
			if (point < shown) {
				visible++;
			}
		}
		return Math.max(0, all - visible);
	}


	/** Такой же разделитель, каким {@link Wiki} отбивает статьи друг от друга. */
	private static final String SEPARATOR = "-".repeat(17);

	/** Высота строки подсказки — ванильная, подсмотрена в GuiGraphicsExtractor. */
	private static final int LINE = 10;

	/** Запас на рамку и поля окна сверху и снизу. */
	private static final int FRAME = 16;

	/**
	 * Режет справку на столбцы, чтобы она влезла по высоте.
	 *
	 * <p><b>Зачем.</b> На предмете с десятком зачарований справка выходит длиннее
	 * экрана и уползает за край: видно только начало. Игрок это и заметил —
	 * причём на масштабе интерфейса 2–3, где места по высоте вдвое-втрое меньше,
	 * чем на 1.
	 *
	 * <p>⚠️ Режем ТОЛЬКО по границам статей (перед разделителем). Разорвать
	 * статью посередине — хуже, чем оставить столбец длинным: пояснение
     * превратится в два обрывка без начала и конца.
	 *
	 * <p>⚠️ Если ОДНА статья длиннее экрана, дробить её всё равно не станем:
	 * вернём как есть. Пусть лучше уедет вниз одна статья, чем развалится
	 * каждая.
	 */
	private static List<List<FormattedCharSequence>> split(
			List<FormattedCharSequence> parts, List<Integer> breaks,
			int screenHeight, Font font) {
		List<List<FormattedCharSequence>> columns = new ArrayList<>();
		int fits = Math.max(1, (screenHeight - EDGE * 2 - FRAME) / LINE);
		if (parts.size() <= fits) {
			columns.add(parts);
			return columns;
		}
		int from = 0;
		while (from < parts.size()) {
			// ⚠️ Набрали предел — останавливаемся, хвост не берём. Место для
			// третьего столбца на экране обычно есть только поверх подсказки,
			// а это хуже, чем честное «…и ещё N» внизу второго.
			if (columns.size() == MAX_COLUMNS) {
				break;
			}
			int limit = from + fits;
			if (limit >= parts.size()) {
				columns.add(new ArrayList<>(parts.subList(from, parts.size())));
				break;
			}
			// Ищем последнюю границу статьи, которая ещё влезает.
			int cut = -1;
			for (int point : breaks) {
				if (point > from && point <= limit) {
					cut = point;
				}
			}
			if (cut <= from) {
				// Границы нет — статья сама длиннее столбца. Не дробим её.
				cut = limit;
				for (int point : breaks) {
					if (point > from) {
						cut = point;
						break;
					}
				}
				if (cut <= from) {
					cut = parts.size();
				}
			}
			columns.add(new ArrayList<>(parts.subList(from, Math.min(cut, parts.size()))));
			from = cut;
		}
		return columns;
	}

	/** Ширина самой длинной строки столбца — на неё сдвигается следующий. */
	private static int widthOf(List<FormattedCharSequence> column, Font font) {
		int width = 0;
		for (FormattedCharSequence row : column) {
			width = Math.max(width, font.width(row));
		}
		return width;
	}

	/**
	 * Ставит столбец в уже посчитанное место.
	 *
	 * <p>⚠️ X приходит готовым из {@link #layout} и здесь НЕ правится: зажим
	 * по краю экрана — ровно то, из-за чего столбец уезжал под подсказку.
	 * Раз место выбрано с учётом всех окон сразу, двигать его поздно и незачем.
	 *
	 * @param x   левый край содержимого столбца
	 * @param top верх основной подсказки: два окна на одной линии читаются
	 *            как одно целое
	 */
	private record FixedPositioner(int x, int top) implements ClientTooltipPositioner {

		@Override
		public Vector2ic positionTooltip(int guiWidth, int guiHeight,
		                                 int mouseX, int mouseY, int width, int height) {
			// По высоте поджать можно и нужно: столбец бывает длиннее подсказки.
			int y = top;
			if (y + height > guiHeight - EDGE) {
				y = guiHeight - height - EDGE;
			}
			return new Vector2i(x, Math.max(EDGE, y));
		}
	}
}
