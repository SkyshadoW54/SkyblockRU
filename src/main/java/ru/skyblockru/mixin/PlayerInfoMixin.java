package ru.skyblockru.mixin;

import net.minecraft.client.multiplayer.PlayerInfo;
import net.minecraft.network.chat.Component;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfoReturnable;
import ru.skyblockru.config.RuConfig;
import ru.skyblockru.core.TextTranslator;

/** Строки внутри списка игроков — у Hypixel это не только ники, но и целые панели статистики. */
@Mixin(PlayerInfo.class)
public class PlayerInfoMixin {

	@Inject(method = "getTabListDisplayName", at = @At("RETURN"), cancellable = true)
	private void skyblockru$tabName(CallbackInfoReturnable<Component> info) {
		// ⚠️ Общий выключатель спрашиваем ЗДЕСЬ, а не полагаемся на translate:
		// проверка внутри него есть, но полагаться на неё в новом пути — тот же
		// недосмотр, из-за которого подвал таба оставался русским после
		// /skyblockru off. Завёл путь перевода — проведи по нему все ворота.
		if (!RuConfig.get().enabled || !RuConfig.get().targets.tabList) {
			return;
		}
		Component original = info.getReturnValue();
		if (original == null) {
			return;
		}
		Component translated = TextTranslator.translate(original, TextTranslator.SRC_TAB);
		if (translated != original) {
			info.setReturnValue(translated);
		}
	}
}
