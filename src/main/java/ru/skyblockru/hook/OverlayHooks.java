package ru.skyblockru.hook;

import net.minecraft.network.chat.Component;
import net.minecraft.network.chat.MutableComponent;
import ru.skyblockru.config.RuConfig;
import ru.skyblockru.core.Hypixel;
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

	/**
	 * Строка боковой панели — уже собранная из префикса, имени и суффикса,
	 * ровно в том виде, в каком уйдёт на экран.
	 *
	 * <p>⚠️ ПЕРЕХВАТЫВАЕМ ВЫЗОВ ВНУТРИ ОТРИСОВКИ ({@code displayScoreboardSidebar}
	 * -> {@code PlayerTeam.formatNameForTeam}), а не методы чтения
	 * ({@code PlayerScoreEntry.ownerName}, {@code PlayerTeam.getPlayerPrefix},
	 * {@code getFormattedName}). До 16.09 стояли именно они — и перевод
	 * доставался ВСЕМ, кто спрашивает панель у игры. Замер по сборке
	 * SkyBlock Enhanced 5.2.11: панель читают 22 jar, и все этими методами.
	 * {@code skyblock-api} (внутри Custom Scoreboard, SkyOcean, SkyBlockPv,
	 * Catharsis, Stella) собирает строку так же, как игра, и ищет в ней
	 * {@code ^(?<type>Purse|Piggy): } — а получал «Кошелёк: 1,234», и счётчик
	 * монет у Custom Scoreboard замирал. Skyblocker, SkyHanni, MarketGuard,
	 * btrbz, Feesh, SBO читают тем же путём.
	 *
	 * <p>Здесь подмена живёт ровно до экрана: значение уходит в запись
	 * отрисовки, а всякий, кто спросит игру сам, получит оригинал Hypixel.
	 * Та же развязка, что у таба ({@code PlayerTabOverlayMixin}).
	 *
	 * <p>Строка приходит СОБРАННОЙ — и это лучше построчных кусков: словарь
	 * ищет по всей строке, а не по обрывкам префикса.
	 */
	public static MutableComponent sidebarLine(MutableComponent line) {
		if (line == null || !RuConfig.get().targets.scoreboard) {
			return line;
		}
		Component translated = TextTranslator.translate(line, TextTranslator.SRC_SCOREBOARD);
		return translated == line ? line : translated.copy();
	}

	/**
	 * Заголовок боковой панели (у Hypixel там название режима и дата).
	 *
	 * <p>Заголовок — единственный надёжный признак режима: в SkyBlock там
	 * «SKYBLOCK», в лобби «HYPIXEL». Запоминаем ДО перевода, и запоминаем
	 * здесь, потому что сюда попадает ровно та цель, что рисуется на панели:
	 * {@code displayScoreboardSidebar} зовётся с ней. Раньше это делал
	 * перехват {@code Objective.getDisplayName} — а его читают SkyHanni
	 * ({@code HypixelData}, {@code ScoreboardData}) и Skyblocker, чтобы узнать
	 * тот же режим. Отдавать им наш перевод нельзя.
	 */
	public static Component sidebarTitle(Component title) {
		if (title == null) {
			return title;
		}
		Hypixel.noteSidebarTitle(title);
		if (!RuConfig.get().targets.scoreboard) {
			return title;
		}
		return TextTranslator.translate(title, TextTranslator.SRC_SCOREBOARD);
	}
}
