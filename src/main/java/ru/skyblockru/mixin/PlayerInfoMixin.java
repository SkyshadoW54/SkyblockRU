package ru.skyblockru.mixin;

import net.minecraft.ChatFormatting;
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
		Component result = TextTranslator.translate(original, TextTranslator.SRC_TAB);
		result = skyblockru$withPing(result);
		if (result != original) {
			info.setReturnValue(result);
		}
	}

	/**
	 * Пинг числом рядом с ником — по флагу {@code showPing}, ВЫКЛЮЧЕННОМУ
	 * по умолчанию.
	 *
	 * <p>Заведено для разбора жалобы «по ощущениям пинг 500»: в ванильном табе
	 * задержка показана полосками, и отличить 40 мс от 400 по ним нельзя.
	 * Число сразу говорит, сеть виновата или кадры.
	 *
	 * <p>⚠️ По умолчанию выключено НАМЕРЕННО. Мод раздают людям как русификатор,
	 * и лишние надписи в чужом интерфейсе — не его дело: кто-то уже показывает
	 * пинг своим модом, и два числа рядом читались бы как поломка.
	 *
	 * <p>⚠️ Мод пинг не меняет и менять не может: он читает уже пришедший текст,
	 * а в игровой обмен не вмешивается. Число здесь — измеритель, а не лечение.
	 */
	private Component skyblockru$withPing(Component name) {
		if (!RuConfig.get().showPing) {
			return name;
		}
		int ms = ((PlayerInfo) (Object) this).getLatency();
		// Цвет тот же, каким игра красит полоски: зелёный до 150, жёлтый
		// до 300, дальше красный. Границы не выдуманы — они видны в шкале
		// ванильного таба (5 делений на 0…1000 мс).
		ChatFormatting colour = ms < 150 ? ChatFormatting.GREEN
				: ms < 300 ? ChatFormatting.YELLOW : ChatFormatting.RED;
		return Component.empty()
				.append(name)
				.append(Component.literal(" " + ms + " мс").withStyle(colour));
	}
}
