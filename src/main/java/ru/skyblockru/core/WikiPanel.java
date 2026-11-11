package ru.skyblockru.core;

import java.util.ArrayList;
import java.util.List;

import net.minecraft.client.Minecraft;
import net.minecraft.client.gui.Font;
import net.minecraft.client.gui.GuiGraphicsExtractor;
import net.minecraft.client.gui.screens.inventory.tooltip.ClientTooltipComponent;
import net.minecraft.client.gui.screens.inventory.tooltip.DefaultTooltipPositioner;
import net.minecraft.client.gui.screens.inventory.tooltip.TooltipRenderUtil;
import net.minecraft.network.chat.Component;
import net.minecraft.util.FormattedCharSequence;
import net.minecraft.world.item.ItemStack;
import org.joml.Matrix3x2f;
import org.joml.Vector2f;
import org.joml.Vector2ic;

/**
 * Справка ОТДЕЛЬНЫМ окном СБОКУ от подсказки предмета.
 *
 * <p><b>Зачем сбоку.</b> Раньше справка дописывалась в ту же подсказку, и она
 * уезжала вниз: описание вещи и пояснение к термину сливались в один длинный
 * столбец, а на высоких подсказках аукциона нижняя часть уходила за край
 * экрана. Игрок попросил второе окно — такое же на вид, но рядом.
 *
 * <p><b>Как.</b> Окно рисуем САМИ, но ванильными деталями: рамка —
 * {@code TooltipRenderUtil}, строки — {@code ClientTooltipComponent}, ровно
 * то, из чего игра собирает свою подсказку. Поэтому рамка, фон и шрифт
 * совпадают с игрой сами собой — ничего не срисовываем руками.
 *
 * <p>⚠️⚠️ <b>НЕ через {@code GuiGraphicsExtractor.tooltip}</b>, хотя до 11.10
 * было именно так. В этот метод встают соседи, и в сборке SkyBlock Enhanced
 * справка уезжала ПОД подсказку предмета (снимок игрока). Замер по байткоду
 * jar из сборки:
 * <ul>
 *   <li>SkyBlock Enhancements ({@code TooltipScrollGuiGraphicsMixin}) при
 *       включённой прокрутке подсказок выкидывает расстановщик позиции у
 *       ЛЮБОЙ подсказки и ставит свой (ванильный плюс прижим к верху). Наш
 *       столбец вставал у курсора — прямо на подсказку предмета;
 *   <li>он же сбрасывает прокрутку, когда у подсказки сменилась первая
 *       строка, — наши столбцы через тот же метод сбивали её каждый кадр;
 *   <li>Stfu ({@code Tooltips}) зажимает любую подсказку по краям экрана,
 *       а прижатую к левому краю переносит НАД курсор.
 * </ul>
 * Им всем нужна подсказка ПРЕДМЕТА; наше окно — не их забота, и рисовать
 * его мимо их перехватов честнее, чем угадывать, что они с ним сделают.
 * Сторожит {@code tools/check_neighbours.py} (свои окна).
 *
 * <p>⚠️⚠️ <b>Рисуем ПОСЛЕ подсказки предмета.</b> Игра её откладывает
 * ({@code setTooltipForNextFrame}) и выводит в {@code extractDeferredElements}
 * последней, на НОВОМ слое ({@code nextStratum}): всё нарисованное раньше
 * оказывается ПОД ней. Пока окна не пересекались, этого не было видно; стоило
 * соседу сдвинуть подсказку — и справка пряталась. Поэтому заказ делает
 * {@code TooltipSideMixin} ({@link #request}), а рисует
 * {@code DeferredTooltipMixin} на выходе из отложенной отрисовки.
 *
 * <p>⚠️ <b>Место подсказки предмета не угадываем.</b> Соседи её двигают
 * (прижим к верху, прокрутка, перенос над курсор) и дописывают строки (цены,
 * недостающие зачарования), а прежний расчёт ванильным расстановщиком по
 * нашим размерам этого не знал. Берём рамку, которую игра РЕАЛЬНО нарисовала
 * ({@code TooltipBackgroundMixin}), вместе со сдвигом прокрутки. Расчёт
 * остался запасным путём — если рамку поймать не удалось.
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

	/**
	 * Заказ на панель в этом кадре.
	 *
	 * <p>⚠️ Кадр узнаём по ХОЛСТУ: игра создаёт его заново на каждый кадр
	 * (проверено javap: 26.2 — {@code Gui.extractRenderState}, 26.1.2 —
	 * {@code GameRenderer.extractGui}, 1.21.11 — {@code GameRenderer.render}).
	 * Заказ прошлого кадра с чужим холстом не совпадёт уже никогда — и панель
	 * от предмета, с которого курсор ушёл, не мелькнёт.
	 */
	private record Request(GuiGraphicsExtractor extractor, ItemStack stack,
	                       int mouseX, int mouseY) {
	}

	/** Где стоит СОДЕРЖИМОЕ подсказки предмета: левый верх и размер. */
	private record Box(int x, int y, int width, int height) {
	}

	private static Request request;

	/** Идёт отложенная отрисовка того кадра, для которого есть заказ. */
	private static boolean deferred;

	/**
	 * Поза холста на входе в отложенную отрисовку.
	 *
	 * <p>Рамку подсказки игра рисует уже внутри сдвига: SkyBlock Enhancements
	 * так прокручивает длинную подсказку. Пересчитав рамку из позы на момент
	 * рисования в эту, получаем место, где подсказку ВИДНО, — в тех же
	 * единицах, в каких потом рисуем свою панель.
	 */
	private static Matrix3x2f base;

	/** Рамка подсказки предмета, пойманная в этом кадре; нет — {@code null}. */
	private static Box mainBox;

	/** Рисуем своё окно — свои рамки за подсказку предмета не принимаем. */
	private static boolean drawing;

	private WikiPanel() {
	}

	/**
	 * Заказывает панель для предмета под курсором — рисовать ещё рано.
	 *
	 * <p>Зовётся на выходе из построения подсказки предмета: она к этому
	 * моменту только ЗАКАЗАНА, а нарисована будет позже, в отложенной
	 * отрисовке. Там же, сразу за ней, встанет и панель.
	 *
	 * @param hovered предмет под курсором; справка готовится при построении
	 *                подсказки, и {@link Wiki} отдаст её только для ТОГО ЖЕ
	 *                предмета — иначе показали бы пояснение от соседнего слота
	 */
	public static void request(GuiGraphicsExtractor extractor, ItemStack hovered,
	                           int mouseX, int mouseY) {
		if (extractor == null || Wiki.panelFor(hovered) == null) {
			return;
		}
		request = new Request(extractor, hovered, mouseX, mouseY);
	}

	/** Вход в отложенную отрисовку: начинаем ждать рамку подсказки предмета. */
	public static void beforeDeferred(GuiGraphicsExtractor extractor) {
		Request ready = request;
		mainBox = null;
		base = null;
		deferred = ready != null && ready.extractor() == extractor;
		if (deferred) {
			base = new Matrix3x2f(extractor.pose());
		}
	}

	/**
	 * Игра рисует рамку подсказки — если это подсказка предмета, запоминаем,
	 * где она встала.
	 *
	 * <p>⚠️ Зовётся на КАЖДУЮ рамку подсказки в игре, поэтому первым делом —
	 * дешёвая проверка флага. Берём первую рамку отложенной отрисовки: это
	 * и есть отложенная подсказка предмета (картинки внутри неё рисуются уже
	 * после её рамки).
	 */
	public static void observeBackground(GuiGraphicsExtractor extractor,
	                                     int x, int y, int width, int height) {
		if (!deferred || drawing || mainBox != null) {
			return;
		}
		Request ready = request;
		if (ready == null || ready.extractor() != extractor || base == null) {
			return;
		}
		Guard.run("wiki panel: main tooltip box",
				() -> mainBox = onBase(extractor, x, y, width, height));
	}

	/** Рамку из позы на момент рисования — в позу, в которой рисуем панель. */
	private static Box onBase(GuiGraphicsExtractor extractor,
	                          int x, int y, int width, int height) {
		Matrix3x2f toBase = new Matrix3x2f(base).invert().mul(extractor.pose());
		Vector2f from = toBase.transformPosition(x, y, new Vector2f());
		Vector2f to = toBase.transformPosition(x + width, y + height, new Vector2f());
		if (!Float.isFinite(from.x) || !Float.isFinite(from.y)
				|| !Float.isFinite(to.x) || !Float.isFinite(to.y)) {
			return null;
		}
		return new Box(Math.round(Math.min(from.x, to.x)), Math.round(Math.min(from.y, to.y)),
				Math.round(Math.abs(to.x - from.x)), Math.round(Math.abs(to.y - from.y)));
	}

	/** Выход из отложенной отрисовки: подсказка предмета нарисована — наша очередь. */
	public static void afterDeferred(GuiGraphicsExtractor extractor) {
		deferred = false;
		Request ready = request;
		if (ready == null || ready.extractor() != extractor) {
			return;
		}
		Box main = mainBox;
		request = null;
		mainBox = null;
		base = null;
		drawing = true;
		try {
			// Своей панелью экран ронять нельзя: она приятная добавка,
			// а не то, ради чего игрок открыл меню.
			Guard.run("wiki panel", () -> draw(extractor, ready, main));
		} finally {
			drawing = false;
		}
	}

	/** Раскладывает справку по столбцам и рисует их рядом с подсказкой предмета. */
	private static void draw(GuiGraphicsExtractor extractor, Request ready, Box caught) {
		Wiki.Panel panel = Wiki.panelFor(ready.stack());
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

		// ⚠️ Рамка подсказки предмета — та, что игра нарисовала в этом кадре.
		// Запасной путь — расчёт ванильным расстановщиком по нашим размерам:
		// так панель стояла до 11.10, и рядом с ванильной подсказкой он верен.
		Box main = caught != null ? caught : predicted(ready, panel, screenWidth, screenHeight);

		List<Integer> widths = new ArrayList<>();
		for (List<FormattedCharSequence> column : columns) {
			widths.add(widthOf(column, font));
		}
		List<Integer> places = PanelLayout.place(
				screenWidth, main.x(), main.width(), GAP, EDGE, widths);

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

		for (int i = 0; i < places.size(); i++) {
			drawColumn(extractor, font, columns.get(i), places.get(i), main.y(), screenHeight);
		}
	}

	/**
	 * Где встала бы ВАНИЛЬНАЯ подсказка предмета — запасной путь.
	 *
	 * <p>Спрашиваем тот самый расстановщик, которым её ставит игра, с размерами,
	 * посчитанными при построении подсказки. Чужие сдвиги и дописанные
	 * строки он не знает — поэтому только когда настоящую рамку не поймали.
	 */
	private static Box predicted(Request ready, Wiki.Panel panel,
	                             int screenWidth, int screenHeight) {
		Vector2ic at = DefaultTooltipPositioner.INSTANCE.positionTooltip(
				screenWidth, screenHeight, ready.mouseX(), ready.mouseY(),
				panel.mainWidth(), panel.mainHeight());
		return new Box(at.x(), at.y(), panel.mainWidth(), panel.mainHeight());
	}

	/**
	 * Рисует один столбец — так же, как игра рисует подсказку.
	 *
	 * <p>Повторяет ванильный {@code tooltip} по байткоду (26.2, 26.1.2,
	 * 1.21.11 одинаковы): высота — сумма строк, у одной строки на 2 меньше;
	 * рамка вокруг содержимого; под первой строкой лишние 2 пикселя.
	 *
	 * <p>⚠️ X приходит готовым из {@link PanelLayout} и здесь НЕ правится:
	 * зажим по краю экрана — ровно то, из-за чего столбец уезжал под подсказку.
	 * По высоте поджать можно и нужно: столбец бывает длиннее подсказки.
	 *
	 * @param top верх подсказки предмета: два окна на одной линии читаются
	 *            как одно целое
	 */
	private static void drawColumn(GuiGraphicsExtractor extractor, Font font,
	                               List<FormattedCharSequence> rows, int x, int top,
	                               int screenHeight) {
		List<ClientTooltipComponent> lines = new ArrayList<>(rows.size());
		int width = 0;
		int height = rows.size() == 1 ? -2 : 0;
		for (FormattedCharSequence row : rows) {
			ClientTooltipComponent line = ClientTooltipComponent.create(row);
			lines.add(line);
			width = Math.max(width, line.getWidth(font));
			height += line.getHeight(font);
		}
		int y = top;
		if (y + height > screenHeight - EDGE) {
			y = screenHeight - height - EDGE;
		}
		y = Math.max(EDGE, y);

		TooltipRenderUtil.extractTooltipBackground(extractor, x, y, width, height, null);
		int lineY = y;
		for (int i = 0; i < lines.size(); i++) {
			ClientTooltipComponent line = lines.get(i);
			line.extractText(extractor, font, x, lineY);
			lineY += line.getHeight(font) + (i == 0 ? 2 : 0);
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
}
