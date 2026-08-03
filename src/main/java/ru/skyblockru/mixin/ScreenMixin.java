package ru.skyblockru.mixin;

import net.minecraft.client.gui.screens.Screen;
import net.minecraft.network.chat.Component;
import org.spongepowered.asm.mixin.Final;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.Mutable;
import org.spongepowered.asm.mixin.Shadow;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;
import ru.skyblockru.config.RuConfig;
import ru.skyblockru.core.TextTranslator;

/**
 * Заголовок открытого окна — название сундука-меню на Hypixel
 * («Auction House», «Your Bags» и т.п.).
 *
 * <p>Подменяем само поле, а не getTitle(): отрисовка окна-контейнера
 * читает поле напрямую, через геттер перевод бы не дошёл.
 */
@Mixin(Screen.class)
public class ScreenMixin {

	@Shadow
	@Final
	@Mutable
	protected Component title;

	// Конструкторов у Screen два, с разными аргументами. Хендлер без аргументов
	// подходит к обоим — иначе пришлось бы дублировать метод под каждую сигнатуру.
	@Inject(method = "<init>", at = @At("TAIL"))
	private void skyblockru$translateTitle(CallbackInfo info) {
		if (!RuConfig.get().targets.screenTitle) {
			return;
		}
		this.title = TextTranslator.translate(this.title, TextTranslator.SRC_SCREEN);
	}
}
