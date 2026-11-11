package ru.skyblockru.mixin;

import com.llamalad7.mixinextras.injector.ModifyExpressionValue;
import net.minecraft.network.chat.Component;
import net.minecraft.network.chat.MutableComponent;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.ModifyVariable;
import ru.skyblockru.hook.OverlayHooks;

/**
 * То же, что {@link HudMixin}, но для 26.1, где класс зовётся {@code Gui}.
 *
 * <p>⚠️ Методы и их сигнатуры в обеих версиях ОДИНАКОВЫ — проверено javap
 * по обоим jar: {@code setOverlayMessage}, {@code setTitle}, {@code setSubtitle}
 * на месте. Различается только имя класса, поэтому обёртка отличается
 * ровно одной строкой, а тело живёт в {@code OverlayHooks}.
 */
@Mixin(targets = "net.minecraft.client.gui.Gui")
public class GuiMixin {

	@ModifyVariable(method = "setOverlayMessage", at = @At("HEAD"), argsOnly = true)
	private Component skyblockru$actionBar(Component message) {
		return OverlayHooks.actionBar(message);
	}

	@ModifyVariable(method = "setTitle", at = @At("HEAD"), argsOnly = true)
	private Component skyblockru$title(Component message) {
		return OverlayHooks.title(message);
	}

	@ModifyVariable(method = "setSubtitle", at = @At("HEAD"), argsOnly = true)
	private Component skyblockru$subtitle(Component message) {
		return OverlayHooks.title(message);
	}

	/**
	 * Строка боковой панели — ВЫЗОВ внутри отрисовки, а не метод чтения.
	 *
	 * <p>⚠️ Цель — лямбда {@code displayScoreboardSidebar}: игра собирает
	 * каждую строку в ней ({@code ownerName} + {@code formatNameForTeam})
	 * и кладёт в запись отрисовки. Имя лямбды — синтетическое и своё
	 * у каждой версии: в 26.x {@code lambda$displayScoreboardSidebar$1},
	 * в 1.21.11 маппинги его не знают, там {@code method_55439}; подставляет
	 * Stonecutter. Что имя на месте, сторожит {@code check_mixin_gate}.
	 *
	 * <p>Почему не {@code PlayerScoreEntry.ownerName} / {@code PlayerTeam
	 * .getPlayerPrefix}: их читают соседи (skyblock-api, Skyblocker, SkyHanni,
	 * MarketGuard), и наш перевод ломал им разбор панели — см. OverlayHooks.
	 */
	@ModifyExpressionValue(method = "lambda$displayScoreboardSidebar$1",
			at = @At(value = "INVOKE", target = "Lnet/minecraft/world/scores/PlayerTeam;formatNameForTeam(Lnet/minecraft/world/scores/Team;Lnet/minecraft/network/chat/Component;)Lnet/minecraft/network/chat/MutableComponent;"))
	private MutableComponent skyblockru$sidebarLine(MutableComponent line) {
		return OverlayHooks.sidebarLine(line);
	}

	/** Заголовок боковой панели — тоже в точке отрисовки, по той же причине. */
	@ModifyExpressionValue(method = "displayScoreboardSidebar",
			at = @At(value = "INVOKE", target = "Lnet/minecraft/world/scores/Objective;getDisplayName()Lnet/minecraft/network/chat/Component;"))
	private Component skyblockru$sidebarTitle(Component title) {
		return OverlayHooks.sidebarTitle(title);
	}
}
