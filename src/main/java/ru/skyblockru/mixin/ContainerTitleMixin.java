package ru.skyblockru.mixin;

import net.minecraft.client.gui.GuiGraphicsExtractor;
import net.minecraft.client.gui.screens.inventory.AbstractContainerScreen;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;
import ru.skyblockru.core.TitleSwap;

/**
 * Заголовок окна-контейнера («Fast Travel», «Auction House») — перевод
 * живёт РОВНО НА ВРЕМЯ ОТРИСОВКИ, а всё остальное время в поле лежит
 * оригинал Hypixel.
 *
 * <p>⚠️⚠️ ЗАЧЕМ ТАК, А НЕ ПРОЩЕ. Раньше заголовок переводился в конструкторе
 * {@code Screen} подменой поля {@code title} — то есть НАВСЕГДА, для всех, кто
 * его прочитает. А читают его соседи: Modern Warp Menu опознаёт меню быстрого
 * перемещения так (проверено по байткоду, не предположено):
 * <pre>
 *   WarpMenuListener:  ContainerScreen.getTitle()
 *                       -&gt; GameCheckUtils.determineOpenMenu(Component)
 *                       -&gt; component.getString().equals("Fast Travel")
 * </pre>
 * Получая «Быстрое перемещение», он не узнавал экран и показывал ванильный
 * сундук с головами вместо карты островов. Жалоба пришла скриншотами от двух
 * игроков сборки SkyBlock Enhanced.
 *
 * <p>⚠️ ЭТО ЧЕТВЁРТЫЙ СЛУЧАЙ ОДНОЙ СЕМЬИ: перехват того, что соседи читают
 * у игры, достаётся и им. Так мы дважды ломали таб SkyHanni (строки и поля
 * шапки) и один раз имя предмета ({@code getHoverName}, 0.2.29). Каждый раз
 * чинили МЕСТО, а не признак, — поэтому беда возвращалась в новом месте.
 *
 * <p>⚠️ ЦЕЛЬ — ОТРИСОВКА ЗАГОЛОВКА, А НЕ ОБЩИЙ РЕНДЕР, и это замер, а не вкус:
 * {@code AbstractContainerScreen.extractRenderState} НЕ ЗОВЁТ super (проверено
 * javap по jar 26.2), поэтому перехват на {@code Screen} до сундука не дошёл бы
 * вовсе — молча, как уже бывало с целями миксинов.
 *
 * <p>⚠️⚠️ ПОЛЕ ЗДЕСЬ НЕ ТЕНЕВОЕ, И ЭТО НЕ СТИЛЬ, А ТРЕБОВАНИЕ MIXIN.
 * {@code title} объявлено в {@code Screen}, а {@code @Shadow} ищет поле ТОЛЬКО
 * в самом целевом классе. Первая версия падала при запуске игры:
 * <pre>
 *   InvalidMixinException: @Shadow field title was not located in the target
 *   class AbstractContainerScreen
 * </pre>
 * Поэтому подмена живёт в {@link ScreenMixin} (он видит поле), а сюда приходит
 * через {@link TitleSwap}. Компиляция этого не проверяет — цели и поля Mixin
 * разрешает при загрузке класса.
 *
 * <p>⚠️ Имя метода внутри {@code @Inject} — СТРОКА, и компиляция её не читает.
 * Здесь она в форме 26.x; для 1.21.x Stonecutter заменяет её на
 * {@code renderLabels}. Сторожит {@code tools/check_mixin_gate.py}.
 */
@Mixin(AbstractContainerScreen.class)
public abstract class ContainerTitleMixin {

	@Inject(method = "extractLabels", at = @At("HEAD"))
	private void skyblockru$titleOn(GuiGraphicsExtractor extractor, int mouseX, int mouseY,
	                                CallbackInfo info) {
		((TitleSwap) this).skyblockru$showTranslatedTitle();
	}

	/** Возвращает полю оригинал: подмена нужна была только экрану. */
	@Inject(method = "extractLabels", at = @At("RETURN"))
	private void skyblockru$titleOff(GuiGraphicsExtractor extractor, int mouseX, int mouseY,
	                                 CallbackInfo info) {
		((TitleSwap) this).skyblockru$restoreOriginalTitle();
	}
}
