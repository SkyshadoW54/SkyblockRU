package ru.skyblockru.mixin;

import net.minecraft.network.chat.Component;
import net.minecraft.world.scores.DisplaySlot;
import net.minecraft.world.scores.Objective;
import net.minecraft.world.scores.Scoreboard;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfoReturnable;
import ru.skyblockru.config.RuConfig;
import ru.skyblockru.core.Hypixel;
import ru.skyblockru.core.TextTranslator;

/** Заголовок боковой панели (у Hypixel там название режима и дата в игре). */
@Mixin(Objective.class)
public class ObjectiveMixin {

	@Inject(method = "getDisplayName", at = @At("RETURN"), cancellable = true)
	private void skyblockru$sidebarTitle(CallbackInfoReturnable<Component> info) {
		Component original = info.getReturnValue();
		if (original == null) {
			return;
		}

		// Заголовок боковой панели — единственный надёжный признак режима:
		// в SkyBlock там «SKYBLOCK», в лобби «HYPIXEL». Запоминаем ДО перевода
		// и только у той цели, что реально висит на панели.
		//
		// Спрашивать заголовок из Hypixel нельзя: getDisplayName перехвачен
		// вот этим самым методом, тот зовёт переводчик, а переводчик спрашивает
		// режим — вышла бы бесконечная рекурсия. Поэтому значение отдаём отсюда.
		try {
			Objective self = (Objective) (Object) this;
			Scoreboard board = self.getScoreboard();
			if (board != null && board.getDisplayObjective(DisplaySlot.SIDEBAR) == self) {
				Hypixel.noteSidebarTitle(original);
			}
		} catch (RuntimeException ignored) {
			// не смогли понять режим — не повод ломать отрисовку панели
		}

		if (!RuConfig.get().targets.scoreboard) {
			return;
		}
		Component translated = TextTranslator.translate(original, TextTranslator.SRC_SCOREBOARD);
		if (translated != original) {
			info.setReturnValue(translated);
		}
	}
}
