package ru.skyblockru.mixin;

import net.minecraft.network.chat.Component;
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
}
