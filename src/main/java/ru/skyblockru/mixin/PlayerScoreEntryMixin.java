package ru.skyblockru.mixin;

import net.minecraft.network.chat.Component;
import net.minecraft.world.scores.PlayerScoreEntry;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfoReturnable;
import ru.skyblockru.config.RuConfig;
import ru.skyblockru.core.TextTranslator;

/**
 * Строки боковой панели.
 *
 * <p>Раньше я переводил их через префиксы команд — так Hypixel собирал сайдбар
 * годами. В 26.x у каждой строки счёта есть собственный компонент, и рисуется
 * именно он, а префиксы остаются пустыми. Поэтому перевод до сайдбара
 * не доходил вовсе: ни «Кошелёк», ни дата, ни задание.
 */
@Mixin(PlayerScoreEntry.class)
public class PlayerScoreEntryMixin {

	@Inject(method = "ownerName", at = @At("RETURN"), cancellable = true)
	private void skyblockru$sidebarLine(CallbackInfoReturnable<Component> info) {
		if (!RuConfig.get().targets.scoreboard) {
			return;
		}
		Component original = info.getReturnValue();
		if (original == null) {
			return;
		}
		Component translated = TextTranslator.translate(original, TextTranslator.SRC_SCOREBOARD);
		if (translated != original) {
			info.setReturnValue(translated);
		}
	}
}
