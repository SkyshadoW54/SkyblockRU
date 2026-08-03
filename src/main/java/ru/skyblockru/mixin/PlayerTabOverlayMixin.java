package ru.skyblockru.mixin;

import net.minecraft.client.gui.GuiGraphicsExtractor;
import net.minecraft.client.gui.components.PlayerTabOverlay;
import net.minecraft.network.chat.Component;
import net.minecraft.world.scores.Objective;
import net.minecraft.world.scores.Scoreboard;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.Shadow;
import org.spongepowered.asm.mixin.Unique;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.ModifyVariable;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;
import ru.skyblockru.config.RuConfig;
import ru.skyblockru.core.Hypixel;
import ru.skyblockru.core.TextTranslator;

/**
 * Шапка и подвал списка игроков (Tab) — там Hypixel держит статистику профиля.
 *
 * <p>⚠️ Перехватывать одну лишь ЗАПИСЬ здесь мало, и это стоило живого бага:
 * после {@code /skyblockru off} подвал оставался русским. Сервер шлёт шапку
 * и подвал ПАКЕТОМ, то есть {@code setHeader} вызывается редко — а переведённый
 * текст ложится прямо в поле и живёт там до следующего пакета. Выключатель
 * до уже записанного не дотягивался, и со стороны это выглядело как «мод
 * не выключается».
 *
 * <p>Поэтому храним ОРИГИНАЛ, а нужную версию ставим в поле при отрисовке
 * ({@code extractRenderState} зовётся каждый кадр). Та же развязка, что
 * у полосы босса: там имя ставит и конструктор, поэтому перехватывать
 * пришлось чтение, а не запись.
 *
 * <p>Перевод при этом считается НЕ каждый кадр: результат держим в поле
 * и пересчитываем, только когда сменился оригинал или состояние выключателя.
 */
@Mixin(PlayerTabOverlay.class)
public abstract class PlayerTabOverlayMixin {

	@Shadow
	private Component header;

	@Shadow
	private Component footer;

	@Unique
	private Component skyblockru$rawHeader;

	@Unique
	private Component skyblockru$rawFooter;

	@Unique
	private Component skyblockru$shownHeader;

	@Unique
	private Component skyblockru$shownFooter;

	/** Состояние, при котором посчитан показанный текст. */
	@Unique
	private boolean skyblockru$shownActive;

	@ModifyVariable(method = "setHeader", at = @At("HEAD"), argsOnly = true)
	private Component skyblockru$header(Component header) {
		this.skyblockru$rawHeader = header;
		this.skyblockru$shownHeader = null; // пришло новое — пересчитаем при отрисовке
		return header;
	}

	@ModifyVariable(method = "setFooter", at = @At("HEAD"), argsOnly = true)
	private Component skyblockru$footer(Component footer) {
		this.skyblockru$rawFooter = footer;
		this.skyblockru$shownFooter = null;
		return footer;
	}

	@Inject(method = "extractRenderState", at = @At("HEAD"))
	private void skyblockru$applyTranslation(GuiGraphicsExtractor extractor, int width,
	                                         Scoreboard scoreboard, Objective objective,
	                                         CallbackInfo info) {
		boolean active = RuConfig.get().enabled
				&& RuConfig.get().targets.tabList
				&& Hypixel.isActive();

		if (this.skyblockru$shownHeader == null || this.skyblockru$shownActive != active) {
			this.skyblockru$shownHeader = this.skyblockru$rawHeader == null ? null
					: (active ? TextTranslator.translate(this.skyblockru$rawHeader,
							TextTranslator.SRC_TAB) : this.skyblockru$rawHeader);
		}
		if (this.skyblockru$shownFooter == null || this.skyblockru$shownActive != active) {
			this.skyblockru$shownFooter = this.skyblockru$rawFooter == null ? null
					: (active ? TextTranslator.translate(this.skyblockru$rawFooter,
							TextTranslator.SRC_TAB) : this.skyblockru$rawFooter);
		}
		this.skyblockru$shownActive = active;

		if (this.skyblockru$shownHeader != null) {
			this.header = this.skyblockru$shownHeader;
		}
		if (this.skyblockru$shownFooter != null) {
			this.footer = this.skyblockru$shownFooter;
		}
	}
}
