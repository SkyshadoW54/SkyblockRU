package ru.skyblockru.mixin;

import net.minecraft.network.chat.Component;
import net.minecraft.world.BossEvent;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfoReturnable;
import ru.skyblockru.config.RuConfig;
import ru.skyblockru.core.TextTranslator;

/** Полоса босса сверху экрана — у Hypixel через неё идут таймеры событий и здоровье боссов. */
@Mixin(BossEvent.class)
public class BossEventMixin {

	/**
	 * ⚠️ Перехватываем ЧТЕНИЕ имени, а не {@code setName}.
	 *
	 * <p>Раньше стоял {@code setName}, и полоса мигала английским: имя ставится
	 * ещё и КОНСТРУКТОРОМ (проверено по классу 26.2 — там {@code BossEvent(UUID,
	 * Component, ...)}), а он {@code setName} не зовёт. Полоса появлялась
	 * по-английски и становилась русской только со следующим обновлением
	 * от сервера.
	 *
	 * <p>Чтение покрывает оба случая разом. Стоит это дёшево: уже переведённая
	 * строка не найдётся в словаре и осядет в кэше промахов.
	 */
	@Inject(method = "getName", at = @At("RETURN"), cancellable = true)
	private void skyblockru$bossBar(CallbackInfoReturnable<Component> info) {
		if (!RuConfig.get().targets.bossBar) {
			return;
		}
		Component name = info.getReturnValue();
		if (name == null) {
			return;
		}
		Component translated = TextTranslator.translate(name, TextTranslator.SRC_BOSS_BAR);
		if (translated != name) {
			info.setReturnValue(translated);
		}
	}
}
