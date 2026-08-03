package ru.skyblockru.core;

import net.minecraft.network.chat.Component;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * Подстановка названий из самого Minecraft.
 *
 * <p>Часть того, что показывает Hypixel, — обычные ванильные вещи: зачарования,
 * предметы, эффекты. У них уже есть официальный перевод, который Mojang
 * поставляет вместе с игрой.
 *
 * <p>Копировать эти строки к себе было бы и неправильно (чужой перевод),
 * и хуже по сути: у игрока может стоять не русский. Поэтому в словаре пишется
 * не сам перевод, а КЛЮЧ: {@code "Impaling {n}": "@enchantment.minecraft.impaling {n}"}.
 * Движок спрашивает перевод у игры — и подставляется то, что видит игрок
 * в своей ванильной локализации, какой бы язык он ни выбрал.
 */
public final class VanillaNames {

	/** @ключ.через.точки — то, что надо спросить у игры. */
	private static final Pattern KEY = Pattern.compile("@([a-z0-9_]+(?:\\.[a-z0-9_]+)+)");

	private static final Map<String, String> CACHE = new ConcurrentHashMap<>();

	private VanillaNames() {
	}

	/** Сбрасывается при перезагрузке словарей: игрок мог сменить язык игры. */
	public static void clearCache() {
		CACHE.clear();
	}

	public static boolean hasKeys(String value) {
		return value != null && value.indexOf('@') >= 0 && KEY.matcher(value).find();
	}

	/**
	 * Заменяет @ключи на перевод из игры.
	 * Возвращает null, если хоть один ключ игре неизвестен — тогда лучше
	 * оставить оригинал, чем показать игроку сырой ключ вида
	 * «enchantment.minecraft.impaling».
	 */
	public static String expand(String value) {
		Matcher matcher = KEY.matcher(value);
		StringBuilder out = new StringBuilder();
		while (matcher.find()) {
			String key = matcher.group(1);
			String translated = CACHE.computeIfAbsent(key, VanillaNames::resolve);
			if (translated.isEmpty()) {
				return null;
			}
			matcher.appendReplacement(out, Matcher.quoteReplacement(translated));
		}
		matcher.appendTail(out);
		return out.toString();
	}

	private static String resolve(String key) {
		try {
			String translated = Component.translatable(key).getString();
			// игра возвращает сам ключ, если перевода нет
			return translated.equals(key) ? "" : translated;
		} catch (RuntimeException exception) {
			Diagnostics.error("vanilla translation (" + key + ")", exception);
			return "";
		}
	}
}
