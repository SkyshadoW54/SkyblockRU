package ru.skyblockru.mixin;

import com.llamalad7.mixinextras.injector.ModifyExpressionValue;
import net.minecraft.client.gui.components.BossHealthOverlay;
import net.minecraft.network.chat.Component;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import ru.skyblockru.config.RuConfig;
import ru.skyblockru.core.TextTranslator;

/**
 * Полоса босса сверху экрана — у Hypixel через неё идут таймеры событий
 * и здоровье боссов. Переводится в ТОЧКЕ ОТРИСОВКИ.
 *
 * <p>⚠️ До 17.09 перевод стоял на {@code BossEvent.getName} (чтение) —
 * и доставался всем, кто спрашивает имя полосы у игры. Замер по сборке
 * SkyBlock Enhanced 5.2.11 (константный пул jar): {@code LerpingBossEvent
 * .getName} читают SkyHanni ({@code BossbarData} — по тексту полосы он узнаёт
 * босса и событие) и Skyblocker ({@code BossHealthOverlayMixin}), Odin читает
 * {@code BossEvent.getName} ({@code BloodCamp}). Та же семья, что таб, имя
 * предмета, заголовок окна, боковая панель и надпись над сущностью.
 *
 * <p>Здесь подмена живёт ровно до экрана: {@code extractRenderState} зовёт
 * {@code getName()} у каждой полосы и тут же отдаёт текст на отрисовку.
 * Мы меняем значение между вызовом и отрисовкой — сосед, спросивший полосу
 * сам, получит оригинал Hypixel.
 *
 * <p>⚠️ Прежний довод «имя ставится ещё и конструктором, поэтому перехватывать
 * надо чтение, а не {@code setName}» здесь не нужен вовсе: точка отрисовки
 * видит любое имя, откуда бы оно ни пришло.
 *
 * <p>Имя метода: в 26.x {@code extractRenderState}, в 1.21.11 {@code render}
 * (проверено javap по обоим jar) — та же пара, что у таба, замена
 * в Stonecutter общая.
 */
@Mixin(BossHealthOverlay.class)
public abstract class BossHealthOverlayMixin {

	@ModifyExpressionValue(method = "extractRenderState",
			at = @At(value = "INVOKE",
					target = "Lnet/minecraft/client/gui/components/LerpingBossEvent;"
							+ "getName()Lnet/minecraft/network/chat/Component;"))
	private Component skyblockru$bossBar(Component name) {
		if (name == null || !RuConfig.get().enabled || !RuConfig.get().targets.bossBar) {
			return name;
		}
		Component translated = TextTranslator.translate(name, TextTranslator.SRC_BOSS_BAR);
		return translated == null ? name : translated;
	}
}
