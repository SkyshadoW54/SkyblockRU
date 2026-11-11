package ru.skyblockru.mixin;

import net.minecraft.client.gui.GuiGraphicsExtractor;
import net.minecraft.client.gui.screens.inventory.tooltip.TooltipRenderUtil;
import net.minecraft.resources.Identifier;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;
import ru.skyblockru.core.WikiPanel;

/**
 * Узнаёт, где игра НА САМОМ ДЕЛЕ нарисовала подсказку предмета.
 *
 * <p>Рамку подсказки рисует {@code TooltipRenderUtil.extractTooltipBackground}
 * (в 1.21.11 — {@code renderTooltipBackground}), и зовёт его ванильный
 * {@code tooltip} уже ПОСЛЕ всех чужих правок: позиция — от расстановщика,
 * которого мог подменить сосед (SkyBlock Enhancements прижимает подсказку
 * к верху, Stfu переносит её над курсор), размер — по строкам, которые
 * соседи дописали (цены, недостающие зачарования), поза — со сдвигом
 * прокрутки. Здесь видно то, что видит игрок, а не наш расчёт.
 *
 * <p>Перехват только смотрит: аргументы не меняет, рисование не отменяет.
 * Какая рамка — подсказка предмета, решает {@link WikiPanel}: берёт первую
 * за отложенную отрисовку того кадра, где заказана справка.
 */
@Mixin(TooltipRenderUtil.class)
public abstract class TooltipBackgroundMixin {

	@Inject(method = "extractTooltipBackground", at = @At("HEAD"))
	private static void skyblockru$mainBox(GuiGraphicsExtractor extractor,
	                                       int x, int y, int width, int height,
	                                       Identifier style, CallbackInfo info) {
		WikiPanel.observeBackground(extractor, x, y, width, height);
	}
}
