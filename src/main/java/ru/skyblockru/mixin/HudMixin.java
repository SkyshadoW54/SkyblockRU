package ru.skyblockru.mixin;

import net.minecraft.network.chat.Component;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.ModifyVariable;
import ru.skyblockru.hook.OverlayHooks;

/**
 * Надписи поверх экрана — версия для 26.2, где класс зовётся {@code Hud}.
 *
 * <p>⚠️ Цель указана СТРОКОЙ, а не {@code Hud.class}. Так исходник собирается
 * и под 26.1, где такого класса нет вовсе: компилятору нечего искать. Раньше
 * стояла ссылка на класс, и сборка под 26.1 падала на ней одной — это
 * единственное, что мешало моду работать на соседней версии.
 *
 * <p>Какой из двух миксинов применить, решает {@link MixinGate} — по тому,
 * какой класс реально есть в игре.
 */
@Mixin(targets = "net.minecraft.client.gui.Hud")
public class HudMixin {

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
