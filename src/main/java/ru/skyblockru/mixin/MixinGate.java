package ru.skyblockru.mixin;

import java.util.List;
import java.util.Map;
import java.util.Set;

import org.objectweb.asm.tree.ClassNode;
import org.objectweb.asm.tree.MethodNode;
import org.spongepowered.asm.mixin.extensibility.IMixinConfigPlugin;
import org.spongepowered.asm.mixin.extensibility.IMixinInfo;
import org.spongepowered.asm.service.MixinService;

/**
 * Какой миксин применять — решаем по тому, ЧТО ЕСТЬ В ЭТОЙ ВЕРСИИ ИГРЫ.
 *
 * <p><b>Зачем.</b> Надписи над хотбаром живут в классе, который в 26.2 зовётся
 * {@code Hud}, а в 26.1 — {@code Gui}. Оба миксина лежат в jar, но применять
 * надо ровно один: у второго целевого класса нет вовсе, и Mixin честно упал бы
 * с ошибкой ещё при запуске.
 *
 * <p>⚠️ Проверяем НАЛИЧИЕ МЕТОДА, а не класса и не номер версии игры. Номер —
 * это догадка («в 26.1 наверняка Gui»); наличие класса — тоже факт, но НЕ ТОТ,
 * и он уже стоил краша на старте.
 *
 * <p><b>Как ломалось.</b> В 26.2 существуют ОБА класса: {@code Hud} с нашими
 * методами и {@code Gui} — совсем другой, надписей над хотбаром в нём нет.
 * Привратник спрашивал «есть ли класс {@code Gui}», получал честное «да»
 * и пропускал {@code GuiMixin}. Тот при {@code defaultRequire: 1} падал
 * с {@code InvalidInjectionException}, и игра не запускалась ВООБЩЕ:
 *
 * <pre>
 *   javap 26.2:    Gui — класс есть, setOverlayMessage НЕТ
 *                  Hud — setOverlayMessage, setTitle, setSubtitle
 *   javap 26.1.2:  Gui — setOverlayMessage ЕСТЬ
 *                  Hud — класса нет вовсе
 * </pre>
 *
 * <p>Метод и есть то, от чего зависит перехват, — значит спрашивать надо
 * про него. Тогда на 26.1 включается {@code GuiMixin}, на 26.2 —
 * {@code HudMixin}, и переименуй Mojang класс снова, привратник разберётся
 * сам: он смотрит на то, что перехватывает, а не на вывеску.
 *
 * <p>⚠️ Смотрим через сервис Mixin, а не {@code Class.forName}: на этом этапе
 * классы игры ещё не загружены, и обычный поиск дал бы ложное «нет».
 *
 * <p><b>⚠️ А на ОБФУСЦИРОВАННЫХ версиях спрашивать бессмысленно, и это
 * замерено.</b> Имена в вопросе — официальные Mojang, а в рантайме у игрока
 * их нет: Loom при сборке переводит цели миксина в промежуточные имена,
 * а обычная строка внутри этого класса остаётся как была. Видно по jar:
 *
 * <pre>
 *   1.21.11  GuiMixin   -> net/minecraft/class_329, method_1758   ОТРЕМАПЛЕН
 *            MixinGate  -> "net.minecraft.client.gui.Gui"          строка, как есть
 * </pre>
 *
 * Поэтому оба перехвата получали «нет» и выключались, а в лог уходило
 * {@code NO OVERLAY HOOK} — крупные заголовки на 1.21.11 оставались
 * английскими. Полоса над хотбаром при этом работала и сбивала с толку:
 * её переводит второй путь, событие {@code MODIFY_GAME} в {@code TextHooks}.
 *
 * <p>Развязка: у обфусцированных версий jar собирается ПОД ОДНУ версию, и там
 * выбор известен ещё при сборке — класс надписей всегда {@code Gui}. Спрашивать
 * рантайм нужно только в 26.x, где 26.1 и 26.2 идут ОДНИМ jar.
 *
 * <p>⚠️ Решение ПЕЧАТАЕТСЯ в лог, и молчаливого «оба выключены» быть не может.
 * Проверка, тихо вернувшая false, выключает перехват целиком — а надписи над
 * хотбаром просто останутся английскими, и искать причину будет не по чему.
 * Это записанное правило проекта: у любого отказа должен быть голос.
 */
public class MixinGate implements IMixinConfigPlugin {

	private static final org.slf4j.Logger LOG =
			org.slf4j.LoggerFactory.getLogger("SkyblockRU");

	/**
	 * Миксин -> целевой класс и МЕТОД, без которого он бессмыслен.
	 *
	 * <p>Метод один на все три перехвата: {@code setTitle} и {@code setSubtitle}
	 * живут там же, где {@code setOverlayMessage} (проверено javap по обоим jar).
	 */
	private static final Map<String, String[]> NEEDS = Map.of(
			"ru.skyblockru.mixin.HudMixin",
			new String[] {"net.minecraft.client.gui.Hud", "setOverlayMessage"},
			"ru.skyblockru.mixin.GuiMixin",
			new String[] {"net.minecraft.client.gui.Gui", "setOverlayMessage"});

	/** Перехват для версий, где класс надписей зовётся {@code Gui}. */
	private static final String GUI_MIXIN = "ru.skyblockru.mixin.GuiMixin";

	/** Сработал ли хоть один из перехватов надписей — чтобы пожаловаться, если нет. */
	private static boolean overlayHooked;

	@Override
	public void onLoad(String mixinPackage) {
	}

	@Override
	public String getRefMapperConfig() {
		return null;
	}

	@Override
	public boolean shouldApplyMixin(String targetClassName, String mixinClassName) {
		String[] needed = NEEDS.get(mixinClassName);
		if (needed == null) {
			return true;
		}
		boolean ok = applies(mixinClassName, needed);
		// ⚠️ Прежняя запись читалась как «метод есть -> skip» и сбивала с толку:
		// слово «has» было частью шаблона, а не результатом. Печатаем ЦЕЛЬ
		// и решение, не притворяясь, что нашли метод.
		LOG.info("overlay mixin {}: target {}#{} -> {}", mixinClassName,
				needed[0], needed[1], ok ? "APPLY" : "skip");
		overlayHooked |= ok;
		return ok;
	}

	/**
	 * Применять ли этот перехват надписей.
	 *
	 * <p>Вопрос один, а способов ответить два, и выбор между ними — не вкус:
	 *
	 * <ul>
	 *   <li><b>26.1+</b> — обе версии идут ОДНИМ jar, значит решить можно только
	 *       в рантайме. Спрашиваем МЕТОД, от которого зависит перехват: в 26.2
	 *       класс {@code Gui} существует, но {@code setOverlayMessage} в нём нет.
	 *   <li><b>обфусцированные</b> — jar собирается под одну версию, и класс там
	 *       всегда {@code Gui}. Спрашивать рантайм нечем: имена в вопросе
	 *       официальные Mojang, а классы игры переименованы (см. javadoc класса).
	 * </ul>
	 */
	private static boolean applies(String mixinClassName, String[] needed) {
		//? if >=26.1 {
		return hasMethod(needed[0], needed[1]);
		//?} else
		/*return GUI_MIXIN.equals(mixinClassName);*/
	}

	@Override
	public void acceptTargets(Set<String> myTargets, Set<String> otherTargets) {
		// ⚠️ Зовётся ПОСЛЕ опроса всех миксинов конфига. Если ни один из двух
		// не подошёл, надписи над хотбаром молча останутся английскими —
		// говорим об этом громко, пока причина ещё видна.
		if (!overlayHooked && !NEEDS.isEmpty()) {
			LOG.error("NO OVERLAY HOOK: neither Hud nor Gui exposes"
					+ " setOverlayMessage. Action bar and titles stay English."
					+ " Check the class names for this Minecraft version.");
		}
	}

	private static boolean hasMethod(String className, String method) {
		try {
			ClassNode node = MixinService.getService()
					.getBytecodeProvider()
					.getClassNode(className.replace('.', '/'));
			if (node == null || node.methods == null) {
				return false;
			}
			for (MethodNode found : node.methods) {
				if (method.equals(found.name)) {
					return true;
				}
			}
			return false;
		} catch (Exception | LinkageError ignored) {
			// класса в этой версии нет — значит миксин не наш
			return false;
		}
	}

	@Override
	public List<String> getMixins() {
		return null;
	}

	@Override
	public void preApply(String targetClassName, ClassNode targetClass,
			String mixinClassName, IMixinInfo mixinInfo) {
	}

	@Override
	public void postApply(String targetClassName, ClassNode targetClass,
			String mixinClassName, IMixinInfo mixinInfo) {
	}
}
