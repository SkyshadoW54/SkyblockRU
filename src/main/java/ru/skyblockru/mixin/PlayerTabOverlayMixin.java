package ru.skyblockru.mixin;

import com.llamalad7.mixinextras.injector.ModifyExpressionValue;
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

	/**
	 * Строки внутри списка игроков — у Hypixel это не только ники, но и целые
	 * панели статистики: «Area: Hub», «Profile: Papaya», «Mining 30: 12.0%».
	 *
	 * <p>⚠️ ПЕРЕХВАТЫВАЕМ ВЫЗОВ ВНУТРИ ОТРИСОВКИ, а не сам метод чтения, —
	 * и это не придирка, а починка живой поломки. Раньше перевод стоял
	 * на {@code PlayerInfo.getTabListDisplayName}, и его получали ВСЕ, кто
	 * спрашивает таб, — в том числе соседние моды. SkyHanni читает таб
	 * именно так ({@code TabListData} зовёт {@code getNameForDisplay},
	 * а та — {@code getTabListDisplayName}) и ищет там английские заголовки
	 * виджетов: «Info», «Island», «Area:», «Commissions:». Получая наш
	 * перевод, он не находил ничего и ругался игроку: «Extra Information
	 * from Tab list not found». Замер по его же {@code TabWidget}: из 23
	 * маркеров наш перевод ломал 13.
	 *
	 * <p>Здесь же подмена живёт ровно до экрана: значение уходит в состояние
	 * отрисовки, а всякий, кто спросит игру сам, получит оригинал Hypixel.
	 * Та же мысль, что у шапки с подвалом выше, только на строку списка.
	 *
	 * <p>⚠️ {@code getNameForDisplay} перехватывать НЕЛЬЗЯ: SkyHanni зовёт
	 * именно её (проверено по байткоду — {@code method_1918} в TabListData),
	 * и мы снова подменили бы ему данные.
	 *
	 * <p>⚠️ ПИНГ ЧИСЛОМ ЗДЕСЬ ПОКАЗЫВАТЬ НЕЛЬЗЯ — пробовали 05.08, убрано.
	 * Hypixel рисует свои панели через записи игроков-пустышек: у них
	 * задержка 1 мс, и число повисло на КАЖДОЙ строке экрана, включая
	 * заголовки колонок. Отличить настоящего игрока в этой точке нечем.
	 */
	@ModifyExpressionValue(method = "extractRenderState",
			at = @At(value = "INVOKE",
					target = "Lnet/minecraft/client/gui/components/PlayerTabOverlay;"
							+ "getNameForDisplay(Lnet/minecraft/client/multiplayer/PlayerInfo;)"
							+ "Lnet/minecraft/network/chat/Component;"))
	private Component skyblockru$tabLine(Component original) {
		if (original == null || !RuConfig.get().enabled || !RuConfig.get().targets.tabList) {
			return original;
		}
		return TextTranslator.translate(original, TextTranslator.SRC_TAB);
	}

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

		// ⚠️ ПОДМЕНА ЖИВЁТ РОВНО НА ВРЕМЯ ОТРИСОВКИ. Раньше мы клали перевод
		// в поле и оставляли его там — а поля `header`/`footer` СОСЕДИ ЧИТАЮТ
		// НАПРЯМУЮ: у SkyHanni это `TabListData`, и в его байткоде стоят
		// `field_2153`/`field_2154`, то есть ровно эти два поля. Значит наш
		// перевод доставался ему вместо текста Hypixel — та же беда, что мы
		// уже чинили на строках таба, только оставшаяся в шапке.
		//
		// Теперь на выходе из отрисовки поля возвращаются к оригиналу
		// (см. skyblockru$restore), и всякий, кто спросит игру сам, получит
		// текст Hypixel.
		if (this.skyblockru$shownHeader != null) {
			this.header = this.skyblockru$shownHeader;
		}
		if (this.skyblockru$shownFooter != null) {
			this.footer = this.skyblockru$shownFooter;
		}
	}

	/** Возвращает полям оригинал: подмена нужна была только экрану. */
	@Inject(method = "extractRenderState", at = @At("RETURN"))
	private void skyblockru$restore(GuiGraphicsExtractor extractor, int width,
	                                Scoreboard scoreboard, Objective objective,
	                                CallbackInfo info) {
		if (this.skyblockru$rawHeader != null) {
			this.header = this.skyblockru$rawHeader;
		}
		if (this.skyblockru$rawFooter != null) {
			this.footer = this.skyblockru$rawFooter;
		}
	}
}
