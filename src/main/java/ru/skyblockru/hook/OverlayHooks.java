package ru.skyblockru.hook;

import net.minecraft.network.chat.Component;
import ru.skyblockru.config.RuConfig;
import ru.skyblockru.core.TextTranslator;

/**
 * Надписи поверх экрана: строка над хотбаром и крупные заголовки.
 *
 * <p><b>Зачем отдельным классом.</b> Тело перехвата одинаково для всех версий
 * игры, а вот КЛАСС, который его несёт, называется по-разному: в 26.2 это
 * {@code Hud}, в 26.1 — {@code Gui}. Держать две копии кода значило бы чинить
 * каждую беду дважды и однажды забыть — поэтому миксины оставлены пустыми
 * обёртками, а вся работа здесь.
 */
public final class OverlayHooks {

	private OverlayHooks() {
	}

	/** Строка над хотбаром. */
	public static Component actionBar(Component message) {
		if (!RuConfig.get().targets.actionBar) {
			return message;
		}
		return TextTranslator.translate(message, TextTranslator.SRC_ACTION_BAR);
	}

	/** Крупный заголовок и подзаголовок — переводятся одинаково. */
	public static Component title(Component message) {
		if (!RuConfig.get().targets.title) {
			return message;
		}
		return TextTranslator.translate(message, TextTranslator.SRC_TITLE);
	}
}
