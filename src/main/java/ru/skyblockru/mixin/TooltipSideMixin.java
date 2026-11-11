package ru.skyblockru.mixin;

import net.minecraft.client.gui.GuiGraphicsExtractor;
import net.minecraft.client.gui.screens.inventory.AbstractContainerScreen;
import net.minecraft.world.inventory.Slot;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.Shadow;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;
import ru.skyblockru.core.WikiPanel;

/**
 * Заказывает справку ОТДЕЛЬНЫМ окном сбоку от подсказки предмета.
 *
 * <p>Точка выбрана так: {@code extractTooltip} — это и есть место, где игра
 * ставит подсказку предмета под курсором (проверено по байткоду: читает
 * {@code hoveredSlot} и зовёт {@code setTooltipForNextFrame}). Значит на
 * выходе из него подсказка уже заказана, а справка для того же предмета
 * уже приготовлена {@code ItemTooltipCallback}.
 *
 * <p>⚠️ Здесь панель только ЗАКАЗЫВАЕТСЯ, а не рисуется. Подсказку предмета
 * игра выводит позже и последней, на новом слое — нарисованное здесь
 * оказалось бы ПОД ней (11.10, сборка SkyBlock Enhanced: справка пряталась
 * за подсказку). Рисует {@code DeferredTooltipMixin} — сразу после неё.
 *
 * <p>⚠️ Своё окно — не дописывание строк в чужую подсказку: подсказка
 * предмета остаётся ровно такой, какой была.
 */
@Mixin(AbstractContainerScreen.class)
public abstract class TooltipSideMixin {

	@Shadow
	protected Slot hoveredSlot;

	@Inject(method = "extractTooltip", at = @At("TAIL"))
	private void skyblockru$sidePanel(GuiGraphicsExtractor extractor,
	                                  int mouseX, int mouseY, CallbackInfo info) {
		Slot slot = this.hoveredSlot;
		if (slot == null || !slot.hasItem()) {
			return;
		}
		WikiPanel.request(extractor, slot.getItem(), mouseX, mouseY);
	}
}
