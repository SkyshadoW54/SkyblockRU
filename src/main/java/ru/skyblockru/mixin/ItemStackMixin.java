package ru.skyblockru.mixin;

import net.minecraft.network.chat.Component;
import net.minecraft.world.item.ItemStack;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfoReturnable;
import ru.skyblockru.config.RuConfig;
import ru.skyblockru.core.TextTranslator;

/** Название предмета — то, что подписано сверху в подсказке и в инвентаре. */
@Mixin(ItemStack.class)
public class ItemStackMixin {

	@Inject(method = "getHoverName", at = @At("RETURN"), cancellable = true)
	private void skyblockru$translateName(CallbackInfoReturnable<Component> info) {
		if (!RuConfig.get().targets.itemName) {
			return;
		}
		Component original = info.getReturnValue();
		Component translated = TextTranslator.translate(original, TextTranslator.SRC_ITEM_NAME);
		if (translated != original) {
			info.setReturnValue(translated);
		}
	}
}
