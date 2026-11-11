package ru.skyblockru.core;

import com.mojang.blaze3d.platform.InputConstants;
import net.fabricmc.fabric.api.client.keymapping.v1.KeyMappingHelper;
import net.minecraft.client.KeyMapping;
import net.minecraft.client.Minecraft;
import net.minecraft.resources.Identifier;

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
 *
 * <p>⚠️⚠️ В 26.3 ИГРА УШЛА С GLFW НА SDL (javap 11.10: {@code SDLEventHandler},
 * {@code isKeyDown} читает {@code SDL_GetKeyboardState}). Класса
 * {@code org.lwjgl.glfw.GLFW} в 26.3 нет вовсе, и коды клавиш другие:
 * левый Shift — 340 (GLFW) в 26.2 и 225 (скан-код SDL) в 26.3. Поэтому
 * коды берём ТОЛЬКО из {@code InputConstants.KEY_*}: имена в обеих версиях
 * одни, а значения — константы, и каждая сборка вшивает свои. По той же
 * причине jar 26.2 на 26.3 не годится, даже если бы загрузился: Shift
 * в нём — это 340, а в 26.3 под 340 ничего нет.
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
	private static final KeyMapping.Category CATEGORY =
			KeyMapping.Category.register(
					Identifier.fromNamespaceAndPath("skyblockru", "main"));

	/*
	 * ⚠️ Конструктор БЕЗ типа клавиши — нарочно. Тип в 26.3 переименован
	 * (KEYSYM -> KEYBOARD, а SCANCODE исчез), и этот конструктор сам
	 * подставляет клавиатурный тип своей версии (javap обеих: KEYSYM в 26.2,
	 * KEYBOARD в 26.3). Так регистрации не нужны условные блоки.
	 */

	/** Справка по ТЕРМИНАМ: что такое Magic Find, Pristine, Heat. */
	public static final KeyMapping WIKI = KeyMappingHelper.registerKeyMapping(
			new KeyMapping("key.skyblockru.wiki", InputConstants.KEY_LSHIFT, CATEGORY));

	/** Справка по ЗАЧАРОВАНИЯМ: что делает Lapidary, Prismatic, Flowstate. */
	public static final KeyMapping ENCHANTS = KeyMappingHelper.registerKeyMapping(
			new KeyMapping("key.skyblockru.enchants", InputConstants.KEY_LALT, CATEGORY));

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
			new KeyMapping("key.skyblockru.original", InputConstants.KEY_V, CATEGORY));

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
	 * тогда спрашивать окно про неё нельзя: вернётся мусор. Считаем, что не
	 * зажата. «Нет клавиши» — {@code InputConstants.UNKNOWN}, а не число:
	 * в 26.2 это -1 (GLFW), в 26.3 — 0 (SDL), javap обеих версий.
	 */
	public static boolean down(KeyMapping mapping) {
		Minecraft client = Minecraft.getInstance();
		if (client == null || client.getWindow() == null || mapping == null) {
			return false;
		}
		InputConstants.Key key = KeyMappingHelper.getBoundKeyOf(mapping);
		if (key == null || key.getType() != KEYBOARD
				|| key.getValue() == InputConstants.UNKNOWN.getValue()) {
			return false;
		}
		if (isKeyDown(client, key.getValue())) {
			return true;
		}
		// ⚠️ У Shift, Ctrl и Alt ДВЕ клавиши, левая и правая. Игрок жмёт ту,
		// что под рукой, а в настройках записана одна. Раньше это учитывалось
		// для Shift явно; теперь правило общее для всех парных клавиш.
		int twin = twinOf(key.getValue());
		return twin != InputConstants.UNKNOWN.getValue() && isKeyDown(client, twin);
	}

	// ⚠️ Тип «клавиша клавиатуры» в 26.3 переименован: KEYSYM -> KEYBOARD.
	//? if <26.3 {
	private static final InputConstants.Type KEYBOARD = InputConstants.Type.KEYSYM;
	//?} else
	/*private static final InputConstants.Type KEYBOARD = InputConstants.Type.KEYBOARD;*/

	/**
	 * ⚠️ Окно спрашивается ПО-РАЗНОМУ: до 26.3 `isKeyDown` берёт объект окна
	 * (внутри — glfwGetKey), в 26.3 окна не берёт вовсе — читает общее
	 * состояние клавиатуры SDL. Расходится число аргументов, замена имени
	 * не спасает — поэтому условный блок.
	 */
	private static boolean isKeyDown(Minecraft client, int code) {
		//? if <26.3 {
		return InputConstants.isKeyDown(client.getWindow(), code);
		//?} else
		/*return InputConstants.isKeyDown(code);*/
	}

	/** Парная клавиша: левый Shift ↔ правый Shift и так далее. */
	private static int twinOf(int code) {
		return switch (code) {
			case InputConstants.KEY_LSHIFT -> InputConstants.KEY_RSHIFT;
			case InputConstants.KEY_RSHIFT -> InputConstants.KEY_LSHIFT;
			case InputConstants.KEY_LCONTROL -> InputConstants.KEY_RCONTROL;
			case InputConstants.KEY_RCONTROL -> InputConstants.KEY_LCONTROL;
			case InputConstants.KEY_LALT -> InputConstants.KEY_RALT;
			case InputConstants.KEY_RALT -> InputConstants.KEY_LALT;
			default -> InputConstants.UNKNOWN.getValue();
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
			case InputConstants.KEY_LSHIFT, InputConstants.KEY_RSHIFT -> "Shift";
			case InputConstants.KEY_LCONTROL, InputConstants.KEY_RCONTROL -> "Ctrl";
			case InputConstants.KEY_LALT, InputConstants.KEY_RALT -> "Alt";
			default -> null;
		};
	}
}
