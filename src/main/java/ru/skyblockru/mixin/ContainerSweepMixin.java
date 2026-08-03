package ru.skyblockru.mixin;

import java.util.Set;

import net.minecraft.client.Minecraft;
import net.minecraft.client.gui.screens.inventory.AbstractContainerScreen;
import net.minecraft.world.inventory.Slot;
import net.minecraft.world.item.Item;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.item.TooltipFlag;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;
import ru.skyblockru.config.RuConfig;
import ru.skyblockru.core.Wiki;

/**
 * Читает описания ВСЕХ предметов открытого меню, не дожидаясь наведения мышки.
 *
 * <p><b>Зачем.</b> Мод узнаёт текст только когда игрок наводит курсор: подсказка
 * строится в этот момент, тогда же она попадает в дамп. Значит собранное
 * зависело от того, на что игрок навёлся, — а в меню аукциона 54 предмета, и
 * водить по ним мышкой ради сбора бессмысленно. Отсюда вечное «в дампе этой
 * строки нет» на очевидные вещи.
 *
 * <p><b>Как.</b> Имитировать наведение не нужно: подсказка целиком строится из
 * {@link ItemStack}, а стеки открытого меню лежат в {@code menu.slots}.
 * Достаточно попросить у каждого его строки — сработает наш обычный путь
 * (сбор, цвета, снимок подсказки), потому что он висит на том же событии
 * {@code ItemTooltipCallback}, которое вызывает построение подсказки.
 *
 * <p>⚠️ Обходим НЕ при открытии, а по тику: содержимое меню приходит с сервера
 * пакетами и в первый миг пусто. И запоминаем уже прочитанное — иначе каждый
 * тик заново перемалывали бы полсотни подсказок.
 *
 * <p><b>⚠️ ЭТОТ ОБХОД ДЁРГАЕТ НЕ ТОЛЬКО НАС.</b> {@code getTooltipLines} —
 * общая точка: на ней висят обработчики ВСЕХ модов, которые слушают
 * {@code ItemTooltipCallback} (REI, JEI, Skyblocker, NEU). Пока мод стоял один
 * у одного игрока, это была наша забота о своей производительности; с раздачей
 * другим людям она становится чужой: наш сбор заставляет их моды работать над
 * предметами, на которые игрок не наводил.
 *
 * <p>Отсюда две меры, и обе про соседей, а не про нас:
 * <ul>
 *   <li><b>память МЕЖДУ экранами.</b> Раньше список прочитанного жил в объекте
 *       экрана, то есть открыл сундук десять раз — десять полных обходов.
 *       Теперь помним глобально, и повторное открытие не стоит ничего;</li>
 *   <li><b>порция за проход.</b> Раньше все 54 слота перемалывались в ОДИН
 *       тик — вместе со всеми чужими обработчиками, то есть заметным всплеском.
 *       Теперь по горстке, а остальное на следующих тиках.</li>
 * </ul>
 *
 * <p>⚠️ Ключ памяти — {@link ItemStack#hashItemAndComponents(ItemStack)}
 * (метод найден javap по jar 26.2, а не по памяти). Прежний ключ «имя +
 * количество» слаб: у двух РАЗНЫХ зачарованных книг имя и количество
 * совпадают, а лор отличается — вторую мы бы не прочитали и не собрали.
 */
@Mixin(AbstractContainerScreen.class)
public abstract class ContainerSweepMixin {

	/**
	 * Что уже прочитали — ОДИН набор на всю сессию, а не на экран.
	 *
	 * <p>Хранит хеш предмета вместе с компонентами: разные книги, разные
	 * прокачки и разные счётчики внутри лора дают разные значения, значит
	 * новое мы всё равно прочитаем.
	 */
	private static final Set<Integer> SKYBLOCKRU$SEEN = java.util.concurrent.ConcurrentHashMap.newKeySet();

	/**
	 * Потолок памяти. Упереться в него на живой игре трудно (это десятки тысяч
	 * РАЗНЫХ предметов), но у любого потолка должен быть предел роста — иначе
	 * набор растёт всю сессию. При переполнении просто начинаем заново: данные
	 * уже собраны, потеряется лишь право не перечитывать.
	 */
	private static final int MAX_SEEN = 40_000;

	private int skyblockru$ticks;

	/** Раз в полсекунды: содержимое меню подгружается и меняется постепенно. */
	private static final int SWEEP_EVERY = 10;

	/**
	 * Сколько НОВЫХ предметов читаем за один проход.
	 *
	 * <p>Уже прочитанные пропускаются мгновенно и в счёт не идут, поэтому
	 * полный сундук закрывается за пару секунд, а всплеска нет: в каждом тике
	 * чужие обработчики получают горстку вызовов, а не полсотни разом.
	 */
	private static final int PER_SWEEP = 8;

	@Inject(method = "containerTick", at = @At("TAIL"))
	private void skyblockru$sweep(CallbackInfo info) {
		if (!RuConfig.get().enabled || !RuConfig.get().targets.itemLore
				|| !RuConfig.get().sweepContainers) {
			return;
		}
		if (++this.skyblockru$ticks % SWEEP_EVERY != 0) {
			return;
		}
		AbstractContainerScreen<?> screen = (AbstractContainerScreen<?>) (Object) this;
		Minecraft client = Minecraft.getInstance();
		if (client.level == null || client.player == null) {
			return;
		}
		// ⚠️ На время обхода справка не готовится: подсказки этих предметов
		// никто не видит, а последний обойдённый затирал бы пояснение для того,
		// на который игрок реально навёл, — и панель сбоку показывала бы чужое.
		Wiki.sweeping(true);
		try {
			int read = 0;
			for (Slot slot : screen.getMenu().slots) {
				if (read >= PER_SWEEP) {
					// Остальное на следующем проходе: всплеск вызовов бьёт
					// не только по нам, но и по чужим обработчикам подсказок.
					break;
				}
				ItemStack stack = slot.getItem();
				if (stack.isEmpty()) {
					continue;
				}
				int mark;
				try {
					mark = ItemStack.hashItemAndComponents(stack);
				} catch (RuntimeException ignored) {
					continue;
				}
				if (!SKYBLOCKRU$SEEN.add(mark)) {
					continue;
				}
				if (SKYBLOCKRU$SEEN.size() > MAX_SEEN) {
					SKYBLOCKRU$SEEN.clear();
					SKYBLOCKRU$SEEN.add(mark);
				}
				read++;
				try {
					// Строки нам не нужны — важен САМ вызов: на нём висит
					// ItemTooltipCallback, а значит сбор, цвета и снимок подсказки.
					stack.getTooltipLines(Item.TooltipContext.of(client.level),
							client.player, TooltipFlag.NORMAL);
				} catch (RuntimeException ignored) {
					// битый предмет — не повод ронять экран
				}
			}
		} finally {
			Wiki.sweeping(false);
		}
	}
}
