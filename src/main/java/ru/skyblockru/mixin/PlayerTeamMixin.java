package ru.skyblockru.mixin;

import net.minecraft.network.chat.Component;
import net.minecraft.network.chat.MutableComponent;
import net.minecraft.world.scores.PlayerTeam;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfoReturnable;
import ru.skyblockru.config.RuConfig;
import ru.skyblockru.core.TextTranslator;

/**
 * Строки боковой панели.
 *
 * <p>Hypixel собирает каждую строку сайдбара из префикса и суффикса команды.
 * Перехватывать сами геттеры бесполезно — проверено по байт-коду 26.2:
 * {@code getFormattedName} читает поля {@code playerPrefix}/{@code playerSuffix}
 * НАПРЯМУЮ (getfield), минуя геттеры, поэтому при отрисовке они не вызываются
 * вовсе. Из-за этого «Кошелёк», дата и задание не переводились и даже не
 * попадали в сбор незнакомых строк.
 *
 * <p>Правильная точка — сам {@code getFormattedName}: путь отрисовки
 * {@code PlayerScoreEntry.ownerName()} → {@code formatNameForTeam} →
 * {@code getFormattedName}. Там строка уже собрана целиком, и это лучше:
 * словарь ищет по всей строке, а не по обрывкам префикса.
 *
 * <p>Геттеры оставлены: их зовут другие места (список игроков, таблички),
 * а с отрисовкой сайдбара они не пересекаются — двойного перевода не будет.
 */
@Mixin(PlayerTeam.class)
public class PlayerTeamMixin {

	@Inject(method = "getFormattedName", at = @At("RETURN"), cancellable = true)
	private void skyblockru$sidebarLine(Component name, CallbackInfoReturnable<MutableComponent> info) {
		if (!RuConfig.get().targets.scoreboard) {
			return;
		}
		MutableComponent original = info.getReturnValue();
		if (original == null) {
			return;
		}
		Component translated = TextTranslator.translate(original, TextTranslator.SRC_SCOREBOARD);
		if (translated != original) {
			info.setReturnValue(translated.copy());
		}
	}

	@Inject(method = "getPlayerPrefix", at = @At("RETURN"), cancellable = true)
	private void skyblockru$prefix(CallbackInfoReturnable<Component> info) {
		skyblockru$translate(info);
	}

	@Inject(method = "getPlayerSuffix", at = @At("RETURN"), cancellable = true)
	private void skyblockru$suffix(CallbackInfoReturnable<Component> info) {
		skyblockru$translate(info);
	}

	private void skyblockru$translate(CallbackInfoReturnable<Component> info) {
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
