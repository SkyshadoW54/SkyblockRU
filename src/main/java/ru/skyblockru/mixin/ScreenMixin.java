package ru.skyblockru.mixin;

import net.minecraft.client.gui.screens.Screen;
import net.minecraft.client.gui.screens.inventory.AbstractContainerScreen;
import net.minecraft.network.chat.Component;
import org.spongepowered.asm.mixin.Final;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.Mutable;
import org.spongepowered.asm.mixin.Shadow;
import org.spongepowered.asm.mixin.Unique;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;
import ru.skyblockru.config.RuConfig;
import ru.skyblockru.core.Hypixel;
import ru.skyblockru.core.TextTranslator;
import ru.skyblockru.core.TitleSwap;

/**
 * Заголовок открытого окна — название сундука-меню на Hypixel
 * («Auction House», «Your Bags» и т.п.).
 *
 * <p>Подменяем само поле, а не getTitle(): отрисовка окна-контейнера
 * читает поле напрямую, через геттер перевод бы не дошёл.
 *
 * <p>⚠️⚠️ У КОНТЕЙНЕРОВ ПОДМЕНА ВРЕМЕННАЯ, и это починка живой поломки.
 * Поле, подменённое навсегда, достаётся и соседям: Modern Warp Menu опознаёт
 * меню быстрого перемещения через {@code ContainerScreen.getTitle()} и,
 * получив «Быстрое перемещение» вместо «Fast Travel», рисовал ванильный
 * сундук с головами вместо карты островов. Поэтому для контейнеров перевод
 * ставится ровно на время отрисовки заголовка — см. {@link ContainerTitleMixin},
 * а сами методы подмены живут здесь: поле {@code title} объявлено в
 * {@code Screen}, и {@code @Shadow} видит его только отсюда.
 */
@Mixin(Screen.class)
public class ScreenMixin implements TitleSwap {

	@Shadow
	@Final
	@Mutable
	protected Component title;

	/** Оригинал Hypixel — то, что видят соседи и что вернётся после отрисовки. */
	@Unique
	private Component skyblockru$rawTitle;

	/** Готовый перевод; считается один раз на заголовок, а не каждый кадр. */
	@Unique
	private Component skyblockru$shownTitle;

	/** Состояние выключателя, при котором посчитан перевод. */
	@Unique
	private boolean skyblockru$titleActive;

	// Конструкторов у Screen два, с разными аргументами. Хендлер без аргументов
	// подходит к обоим — иначе пришлось бы дублировать метод под каждую сигнатуру.
	@Inject(method = "<init>", at = @At("TAIL"))
	private void skyblockru$translateTitle(CallbackInfo info) {
		if (!RuConfig.get().targets.screenTitle) {
			return;
		}
		// ⚠️ Прочие экраны (настройки, пауза) переводятся сразу: их заголовок
		// соседи не разбирают, а единой точки отрисовки, как `extractLabels`
		// у контейнеров, у них нет — у каждого своя.
		if ((Object) this instanceof AbstractContainerScreen) {
			return;
		}
		this.title = TextTranslator.translate(this.title, TextTranslator.SRC_SCREEN);
	}

	@Override
	public void skyblockru$showTranslatedTitle() {
		if (!RuConfig.get().targets.screenTitle) {
			return;
		}
		// ⚠️ Заголовок мог смениться (новое окно на том же экране) — тогда
		// прежний перевод не годится, и его надо посчитать заново.
		if (this.skyblockru$rawTitle != this.title) {
			this.skyblockru$rawTitle = this.title;
			this.skyblockru$shownTitle = null;
		}
		boolean active = RuConfig.get().enabled && Hypixel.isActive();
		if (this.skyblockru$shownTitle == null || this.skyblockru$titleActive != active) {
			this.skyblockru$shownTitle = active
					? TextTranslator.translate(this.skyblockru$rawTitle, TextTranslator.SRC_SCREEN)
					: this.skyblockru$rawTitle;
			this.skyblockru$titleActive = active;
		}
		this.title = this.skyblockru$shownTitle;
	}

	@Override
	public void skyblockru$restoreOriginalTitle() {
		// ⚠️ Возврат идёт от СОХРАНЁННОГО оригинала, а не «перевести обратно»:
		// обратного перевода не бывает, и без этого поля сосед получил бы
		// русский текст при первом же своём вопросе.
		if (this.skyblockru$rawTitle != null) {
			this.title = this.skyblockru$rawTitle;
		}
	}
}
