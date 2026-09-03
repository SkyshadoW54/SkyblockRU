package ru.skyblockru.core;

import net.minecraft.network.chat.Component;
import net.minecraft.world.item.ItemStack;
import ru.skyblockru.config.RuConfig;

/**
 * Название предмета: перевод и сборка перекованного имени.
 *
 * <p>⚠⚠ ПОЧЕМУ ЭТО БОЛЬШЕ НЕ МИКСИН НА {@code getHoverName}. Раньше имя
 * переводилось перехватом {@code ItemStack.getHoverName} на RETURN — то есть
 * подменялось ВСЕМ, кто спрашивает игру, а не только экрану. Замер 03.09 по
 * jar соседей: этот метод зовут <b>115 классов SkyHanni</b> и <b>72
 * Skyblocker</b>.
 *
 * <p>Ломалось это так (жалоба игрока со скриншотами): в Superpairs у SkyHanni
 * есть {@code SuperPairsItemVisibility}, и он ищет в ИМЕНИ английский шаблон
 * («?», «Click any button!») — по нему отличает нажатую карточку от
 * ненажатой. Получая наш перевод, он не находил ничего, и подсветка уже
 * открытых ячеек гасла.
 *
 * <p>Это записанная семья бед: <b>перехват ЧТЕНИЯ достаётся всем</b>. Ровно
 * так мы дважды ломали SkyHanni на табе, и развязка та же — подменять не сам
 * метод, а то, что уходит НА ЭКРАН. Имя предмета человек видит в подсказке,
 * поэтому перевод живёт в её первой строке ({@code TextHooks.translateTooltip}),
 * а соседям достаётся оригинал.
 *
 * <p>⚠ Побочно это ПОЧИНИЛО отрезание имени у абзацев: {@code
 * Paragraphs.nameAside} сравнивает первую строку с именем предмета, а получал
 * переведённое против английского. Замер: у 18% живых блоков имя приходило
 * уже русским, то есть отрезание там не работало вовсе.
 */
public final class ItemName {

	private ItemName() {
	}

	/**
	 * Перевод названия. {@code null} — менять нечего.
	 */
	public static Component translate(ItemStack stack, Component original) {
		if (!RuConfig.get().targets.itemName || original == null) {
			return null;
		}
		Component translated = TextTranslator.translate(original, TextTranslator.SRC_ITEM_NAME);
		if (translated != original) {
			return translated;
		}
		return reforged(stack, original);
	}

	private static Component reforged(ItemStack stack, Component original) {
		if (!RuConfig.get().enabled || !Hypixel.isActive()) {
			return null;
		}
		return Guard.get("item-name-reforge", () -> {
			// ⚠️ Спрашиваем СЕРВЕР, а не форму строки: без этого признака
			// «первое слово + остаток» резал бы и обычные имена, где первое
			// слово частью имени и является. Пусто — префикс не отрезаем,
			// но имя всё равно собираем: к нему мог прилипнуть ХВОСТ
			// прокачки («Hyperion ✪✪✪✪✪»), и без него перевод найдётся.
			boolean reforged = reforgedFlag(stack);
			String plain = LegacyText.strip(original.getString()).trim();
			// ⚠️ Кэш ДО дорогой сборки: она зовёт словарь напрямую, и каждый
			// промах — перебор тысяч правил. Замер игрока: 563 мс в секунду
			// на 12 тысяч вызовов, две трети всего времени кадра.
			String key = (reforged ? "1\u0000" : "0\u0000") + plain;
			String ready = composed().get(key);
			if (ready != null) {
				return NOTHING.equals(ready) ? null
						: Component.literal(ready)
								.withStyle(original.getStyle());
			}
			String name = Reforge.compose(plain, reforged,
					base -> {
						Translator.Match found =
								Translator.lookup(base, TextTranslator.SRC_ITEM_NAME);
						return found == null ? null : found.text();
					},
					Translator::reforgeForms,
					Translator::genderOverride);
			java.util.Map<String, String> cache = composed();
			if (cache.size() >= COMPOSED_MAX) {
				cache.clear();
			}
			cache.put(key,
					name == null ? NOTHING : name);
			if (name == null) {
				return null;
			}
			// Стиль берём у оригинала: цветом заголовка Hypixel показывает
			// РЕДКОСТЬ, и потерять его значило бы соврать о предмете.
			return Component.literal(name).withStyle(original.getStyle());
		}, null);
	}

	/**
	 * Перекована ли вещь — с памятью, а не заново на каждый вызов.
	 *
	 * <p>⚠️⚠️ ЗАМЕР ИГРОКА, 31.08: соседние моды зовут {@code getHoverName}
	 * <b>10 368 раз в секунду</b>. На каждом мы спрашивали NBT, а
	 * {@code Items.nbt} делает {@code CustomData.copyTag()} — ПОЛНУЮ копию
	 * тега. У вещи с аукциона он большой: выходили десятки мегабайт мусора
	 * в секунду, а сборка мусора останавливает ВСЕ потоки. Отсюда просадка
	 * до 40 кадров при открытии аукциона в сборке из 88 модов.
	 *
	 * <p>⚠️ Читать без копии нельзя: {@code getUnsafe()} в 26.2 нет
	 * (проверено javap — у {@code CustomData} только {@code copyTag}).
	 * Поэтому уменьшаем не цену чтения, а ЧИСЛО чтений.
	 *
	 * <p>⚠️ Кэш держит ТОЛЬКО признак из NBT, а не готовое имя. Перевод
	 * по-прежнему считается каждый раз, значит смена языка, обновление
	 * словарей из облака и переключение режима действуют сразу — чистить
	 * этот кэш не нужно ни при одном из них. Кэшируй мы имя, пришлось бы
	 * проводить его через все те же ворота, а забытые ворота в этом проекте
	 * уже дважды означали «настройка не действует».
	 *
	 * <p>Ключ — {@code hashItemAndComponents}: тот же приём, что
	 * в {@code ContainerSweepMixin}. Он учитывает и предмет, и компоненты,
	 * поэтому изменившаяся вещь даёт другой ключ и считается заново.
	 */
	private static boolean reforgedFlag(ItemStack stack) {
		int mark;
		try {
			mark = ItemStack.hashItemAndComponents(stack);
		} catch (RuntimeException ignored) {
			// хеш не дался — считаем как раньше, честно и дорого
			return !Items.modifierOf(stack).isBlank();
		}
		Boolean ready = REFORGED.get(mark);
		if (ready != null) {
			return ready;
		}
		boolean reforged = !Items.modifierOf(stack).isBlank();
		// Потолок у любой памяти обязателен: без него набор растёт всю
		// сессию. Переполнился — начинаем заново, данные не теряются.
		if (REFORGED.size() >= REFORGED_MAX) {
			REFORGED.clear();
		}
		REFORGED.put(mark, reforged);
		return reforged;
	}

	private static final java.util.Map<Integer, Boolean> REFORGED =
			new java.util.concurrent.ConcurrentHashMap<>();

	private static final int REFORGED_MAX = 20_000;

	/**
	 * Готовые имена — по паре «имя + перекована ли».
	 *
	 * <p>⚠️⚠️ ЗАМЕР ИГРОКА, 01.09: сборка имени стоила <b>563 мс в секунду</b>
	 * на 12 тысяч вызовов — две трети времени. При том же числе вызовов
	 * {@code TextTranslator.translate} стоил 43 мс, потому что у него есть
	 * кэши; а {@link Reforge#compose} спрашивает словарь НАПРЯМУЮ, и каждый
	 * промах — перебор тысяч правил.
	 *
	 * <p>⚠️ Кэш выведен ИЗ СЛОВАРЯ, поэтому обязан умирать вместе с ним:
	 * перезагрузка из облака и смена режима поднимают поколение
	 * ({@link TextTranslator#cacheGeneration}), и набор сбрасывается сам.
	 * Иначе игрок включил бы полный перевод, а имена остались бы прежними —
	 * записанная беда «настройка не действует».
	 */
	private static final java.util.Map<String, String> COMPOSED =
			new java.util.concurrent.ConcurrentHashMap<>();

	private static final int COMPOSED_MAX = 20_000;

	private static final String NOTHING = "\u0000нечего";

	private static volatile int generation = -1;

	private static java.util.Map<String, String> composed() {
		int now = TextTranslator.cacheGeneration();
		if (now != generation) {
			generation = now;
			COMPOSED.clear();
		}
		return COMPOSED;
	}
}
