package ru.skyblockru.mixin;

import net.minecraft.network.chat.Component;
import net.minecraft.world.entity.Entity;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfoReturnable;
import ru.skyblockru.config.RuConfig;
import ru.skyblockru.core.TextTranslator;

/**
 * Надписи над сущностями. На Hypixel это главным образом «голограммы» —
 * невидимые стойки для брони с текстом: таймеры, здоровье мобов, вывески у NPC.
 */
@Mixin(Entity.class)
public class EntityMixin {

	@Inject(method = "getCustomName", at = @At("RETURN"), cancellable = true)
	private void skyblockru$nameTag(CallbackInfoReturnable<Component> info) {
		if (!RuConfig.get().targets.nameTag) {
			return;
		}
		Component original = info.getReturnValue();
		if (original == null) {
			return;
		}
		Component translated = TextTranslator.translate(original, TextTranslator.SRC_NAME_TAG);
		if (translated != original) {
			info.setReturnValue(translated);
		}
	}
}
