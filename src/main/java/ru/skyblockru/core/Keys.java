package ru.skyblockru.core;

import com.mojang.blaze3d.platform.InputConstants;
import net.fabricmc.fabric.api.client.keymapping.v1.KeyMappingHelper;
import net.minecraft.client.KeyMapping;
import net.minecraft.client.Minecraft;
import net.minecraft.resources.Identifier;
import org.lwjgl.glfw.GLFW;

/**
 * Клавиши мода — НАСТРАИВАЕМЫЕ, из обычного меню управления Minecraft.
 *
 * <p><b>Зачем.</b> Раньше Shift был зашит в код намертво
 * ({@code InputConstants.isKeyDown(window, GLFW_KEY_LEFT_SHIFT)}), и если
 * у игрока эта клавиша не работает или занята другим модом — справку было
 * не открыть ВООБЩЕ, никак. Возможность, которую нельзя переназначить,
 * для части игроков просто отсутствует.
 *
 * <p>Теперь обе клавиши регистрируются как обычные привязки игры: они видны
 * в «Настройки → Управление» своей категорией и переназначаются там же.
 * Ничего своего для этого писать не пришлось.
 *
 * <p>⚠️ Спрашиваем ТЕКУЩУЮ привязку ({@code getBoundKeyOf}), а не
 * {@code getDefaultKey()}. Иначе переназначение игрока не подействовало бы:
 * в меню он поменял бы клавишу, а мод продолжал слушать прежнюю — и это
 * ровно тот вид поломки, которую никто не свяжет с настройками.
 *
 * <p>⚠️ Сигнатуры проверены javap по клиентскому jar 26.2, а не взяты
 * из примеров: здесь конструктор принимает {@code KeyMapping.Category},
 * а не строку, как в 1.21. Примеры из интернета тут не собираются.
 */
public final class Keys {

	/**
	 * Своя категория в меню управления — чтобы обе клавиши лежали вместе.
	 *
	 * <p>⚠️ {@code fromNamespaceAndPath}, а НЕ {@code Identifier.of}: в 26.2
	 * метода {@code of} нет (проверено javap). Примеры под 1.21 тут не собираются,
	 * и это уже второе такое место в одном классе — первым был конструктор
	 * {@code KeyMapping}, берущий {@code Category} вместо строки.
	 */
	//? if >=1.21.9 {
	private static final KeyMapping.Category CATEGORY =
			KeyMapping.Category.register(
					Identifier.fromNamespaceAndPath("skyblockru", "main"));
	//?} else
	/*private static final String CATEGORY = "key.category.skyblockru.main";*/

	/** Справка по ТЕРМИНАМ: что такое Magic Find, Pristine, Heat. */
	public static final KeyMapping WIKI = KeyMappingHelper.registerKeyMapping(
			new KeyMapping("key.skyblockru.wiki", InputConstants.Type.KEYSYM,
					GLFW.GLFW_KEY_LEFT_SHIFT, CATEGORY));

	/** Справка по ЗАЧАРОВАНИЯМ: что делает Lapidary, Prismatic, Flowstate. */
	public static final KeyMapping ENCHANTS = KeyMappingHelper.registerKeyMapping(
			new KeyMapping("key.skyblockru.enchants", InputConstants.Type.KEYSYM,
					GLFW.GLFW_KEY_LEFT_ALT, CATEGORY));

	/**
	 * ПОКАЗАТЬ ОРИГИНАЛ: пока держишь — подсказка английская, как её прислал
	 * Hypixel.
	 *
	 * <p><b>Зачем.</b> Гайды, вики и аукцион — на английском, и игроку время
	 * от времени нужно свериться с исходной формулировкой. До сих пор для
	 * этого приходилось выключать мод целиком (`/skyblockru off`) и включать
	 * обратно; приём подсмотрен у чужого мода, где ту же роль играет Shift.
	 *
	 * <p>⚠️ Shift и Alt у нас ЗАНЯТЫ справкой, поэтому взята свободная V.
	 * Ванильная игра её не использует, а если она занята другим модом —
	 * привязка переназначается в «Настройки → Управление», как и остальные.
	 *
	 * <p>⚠️ Сбор данных при этом НЕ отключается: мод по-прежнему записывает
	 * строки в дамп. Иначе игрок, разглядывающий оригинал, молча переставал
	 * бы пополнять корпус — а это ровно те подсказки, которые ему интересны.
	 */
	public static final KeyMapping ORIGINAL = KeyMappingHelper.registerKeyMapping(
			new KeyMapping("key.skyblockru.original", InputConstants.Type.KEYSYM,
					GLFW.GLFW_KEY_V, CATEGORY));

	/** Держит ли игрок клавишу «показать оригинал» прямо сейчас. */
	public static boolean showingOriginal() {
		return down(ORIGINAL);
	}

	private Keys() {
	}

	/**
	 * Загружает класс, чтобы статические поля успели зарегистрироваться.
	 *
	 * <p>Клавиши обязаны быть заявлены при инициализации мода: позже игра
	 * список уже построила, и новая привязка в меню не появится.
	 */
	public static void register() {
		// Само обращение к классу и есть регистрация — тела не требуется.
	}

	/**
	 * Зажата ли клавиша ПРЯМО СЕЙЧАС.
	 *
	 * <p>⚠️ Не {@code KeyMapping.isDown()}: тот считает нажатия, дошедшие
	 * до игрового ввода, а подсказка строится на ЭКРАНЕ (инвентарь, аукцион),
	 * где ввод перехватывает сам экран и до привязок не доходит. Поэтому
	 * спрашиваем окно напрямую — как и раньше со Shift, только клавишу теперь
	 * берём из настроек, а не из константы.
	 *
	 * <p>⚠️ Клавиша может быть НЕ НАЗНАЧЕНА вовсе (игрок снял привязку) —
	 * тогда {@code getValue()} даёт GLFW_KEY_UNKNOWN, и спрашивать окно про
	 * него нельзя: вернётся мусор. Считаем, что не зажата.
	 */
	public static boolean down(KeyMapping mapping) {
		Minecraft client = Minecraft.getInstance();
		if (client == null || client.getWindow() == null || mapping == null) {
			return false;
		}
		InputConstants.Key key = KeyMappingHelper.getBoundKeyOf(mapping);
		if (key == null || key.getType() != InputConstants.Type.KEYSYM
				|| key.getValue() == GLFW.GLFW_KEY_UNKNOWN) {
			return false;
		}
		// ⚠️ ОКНО передаётся ПО-РАЗНОМУ. В 1.21.9+ и 26.x `isKeyDown` берёт
		// сам объект окна, а в 1.21.8 и ниже — его дескриптор (long). Замена
		// имени тут не спасает: расходится ТИП аргумента, поэтому условный блок.
		//? if >=1.21.9 {
		var handle = client.getWindow();
		//?} else
		/*var handle = client.getWindow().getWindow();*/
		if (InputConstants.isKeyDown(handle, key.getValue())) {
			return true;
		}
		// ⚠️ У Shift, Ctrl и Alt ДВЕ клавиши, левая и правая. Игрок жмёт ту,
		// что под рукой, а в настройках записана одна. Раньше это учитывалось
		// для Shift явно; теперь правило общее для всех парных клавиш.
		int twin = twinOf(key.getValue());
		return twin != GLFW.GLFW_KEY_UNKNOWN
				&& InputConstants.isKeyDown(handle, twin);
	}

	/** Парная клавиша: левый Shift ↔ правый Shift и так далее. */
	private static int twinOf(int code) {
		return switch (code) {
			case GLFW.GLFW_KEY_LEFT_SHIFT -> GLFW.GLFW_KEY_RIGHT_SHIFT;
			case GLFW.GLFW_KEY_RIGHT_SHIFT -> GLFW.GLFW_KEY_LEFT_SHIFT;
			case GLFW.GLFW_KEY_LEFT_CONTROL -> GLFW.GLFW_KEY_RIGHT_CONTROL;
			case GLFW.GLFW_KEY_RIGHT_CONTROL -> GLFW.GLFW_KEY_LEFT_CONTROL;
			case GLFW.GLFW_KEY_LEFT_ALT -> GLFW.GLFW_KEY_RIGHT_ALT;
			case GLFW.GLFW_KEY_RIGHT_ALT -> GLFW.GLFW_KEY_LEFT_ALT;
			default -> GLFW.GLFW_KEY_UNKNOWN;
		};
	}

	/**
	 * Название клавиши для приглашения: «Shift — подробности».
	 *
	 * <p>⚠️ У ПАРНЫХ клавиш сторону НЕ показываем. Minecraft локализует
	 * {@code LEFT_SHIFT} как «Shift слева», и приглашение читалось
	 * «Shift слева — подробности» — будто правый Shift не подойдёт. А он
	 * подойдёт: {@link #down} спрашивает и парную клавишу ({@link #twinOf}),
	 * то есть сторона не имеет значения вовсе. Показывать её значит обещать
	 * ограничение, которого нет.
	 *
	 * <p>Короткие имена берём латиницей: «Shift», «Ctrl», «Alt» одинаковы
	 * в любом языке игры, и переводить их незачем. Для остальных клавиш
	 * оставляем то, что даёт сама игра — там сторон не бывает.
	 */
	public static String label(KeyMapping mapping) {
		InputConstants.Key key = KeyMappingHelper.getBoundKeyOf(mapping);
		if (key == null) {
			return "?";
		}
		String paired = pairedName(key.getValue());
		return paired != null ? paired : key.getDisplayName().getString();
	}

	/** Короткое имя парной клавиши — без указания стороны. */
	private static String pairedName(int code) {
		return switch (code) {
			case GLFW.GLFW_KEY_LEFT_SHIFT, GLFW.GLFW_KEY_RIGHT_SHIFT -> "Shift";
			case GLFW.GLFW_KEY_LEFT_CONTROL, GLFW.GLFW_KEY_RIGHT_CONTROL -> "Ctrl";
			case GLFW.GLFW_KEY_LEFT_ALT, GLFW.GLFW_KEY_RIGHT_ALT -> "Alt";
			default -> null;
		};
	}
}
