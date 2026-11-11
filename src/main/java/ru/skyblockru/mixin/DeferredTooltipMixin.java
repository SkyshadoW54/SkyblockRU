package ru.skyblockru.mixin;

import net.minecraft.client.gui.GuiGraphicsExtractor;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;
import ru.skyblockru.core.WikiPanel;

/**
 * Рисует справку СРАЗУ ПОСЛЕ подсказки предмета.
 *
 * <p>Подсказку предмета игра не рисует сразу, а откладывает
 * ({@code setTooltipForNextFrame}) и выводит в {@code extractDeferredElements}:
 * {@code nextStratum()}, затем отложенная подсказка (проверено javap: 26.2,
 * 26.1.2; в 1.21.11 тот же метод зовётся {@code renderDeferredElements}).
 * Новый слой ложится поверх ВСЕГО нарисованного раньше — поэтому справка,
 * нарисованная при построении подсказки, при наложении пряталась под неё
 * (11.10, сборка SkyBlock Enhanced).
 *
 * <p>На входе начинаем ловить рамку подсказки предмета
 * ({@code TooltipBackgroundMixin}), на выходе рисуем панель рядом с ней —
 * в том же слое и позже, то есть поверх.
 *
 * <p>Перехват только наблюдает и дорисовывает своё: ничего игры не меняет
 * и чужого не отменяет. Хендлеры без аргументов подходят к обеим сигнатурам
 * ({@code (IIF)V} в 26.x и {@code ()V} в 1.21.11) — Mixin это разрешает,
 * так же устроен {@code ScreenMixin}.
 */
@Mixin(GuiGraphicsExtractor.class)
public abstract class DeferredTooltipMixin {

	@Inject(method = "extractDeferredElements", at = @At("HEAD"))
	private void skyblockru$beforeDeferred(CallbackInfo info) {
		WikiPanel.beforeDeferred((GuiGraphicsExtractor) (Object) this);
	}

	@Inject(method = "extractDeferredElements", at = @At("TAIL"))
	private void skyblockru$afterDeferred(CallbackInfo info) {
		WikiPanel.afterDeferred((GuiGraphicsExtractor) (Object) this);
	}
}
