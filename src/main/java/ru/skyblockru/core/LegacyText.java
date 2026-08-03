package ru.skyblockru.core;

import net.minecraft.ChatFormatting;
import net.minecraft.network.chat.Component;
import net.minecraft.network.chat.MutableComponent;
import net.minecraft.network.chat.Style;

/**
 * Работа со старыми кодами форматирования (§a, §l и т.д.).
 * <p>
 * Hypixel почти весь текст шлёт именно так, и переводчику удобно писать цвета
 * прямо в строке перевода: "§6Золотой §7меч". Здесь такая строка превращается
 * в нормальный Component, и наоборот — коды вырезаются для поиска по словарю.
 */
public final class LegacyText {

	private LegacyText() {
	}

	/** Убирает все коды §X — по такой «чистой» строке ищем перевод в словаре. */
	public static String strip(String text) {
		if (text.indexOf(ChatFormatting.PREFIX_CODE) < 0) {
			return text;
		}
		StringBuilder out = new StringBuilder(text.length());
		for (int i = 0; i < text.length(); i++) {
			char c = text.charAt(i);
			if (c == ChatFormatting.PREFIX_CODE && i + 1 < text.length()) {
				i++; // пропускаем и сам §, и символ кода
				continue;
			}
			out.append(c);
		}
		return out.toString();
	}

	/** Есть ли в строке коды форматирования. */
	/**
	 * Коды в начале строки — они и задают её цвет.
	 *
	 * <p>Нужны, когда строку разбирают и собирают заново: цвет у Hypixel живёт
	 * §-кодом ВНУТРИ текста, а не стилем компонента, и без переноса кода
	 * пересобранная строка теряет раскраску.
	 */
	public static String leadingCodes(String text) {
		if (text == null) {
			return "";
		}
		int at = 0;
		while (at + 1 < text.length() && text.charAt(at) == '§') {
			at += 2;
		}
		return text.substring(0, at);
	}

	public static boolean hasCodes(String text) {
		return text.indexOf(ChatFormatting.PREFIX_CODE) >= 0;
	}


	/**
	 * Собирает Component из строки с кодами §.
	 *
	 * @param text строка перевода, возможно с кодами
	 * @param base стиль по умолчанию — им красится текст до первого кода
	 */
	public static MutableComponent parse(String text, Style base) {
		MutableComponent root = Component.empty();
		if (!hasCodes(text)) {
			return root.append(Component.literal(text).setStyle(base));
		}

		Style current = base;
		StringBuilder buffer = new StringBuilder();

		for (int i = 0; i < text.length(); i++) {
			char c = text.charAt(i);
			if (c == ChatFormatting.PREFIX_CODE && i + 1 < text.length()) {
				ChatFormatting format = ChatFormatting.getByCode(text.charAt(i + 1));
				if (format != null) {
					if (!buffer.isEmpty()) {
						root.append(Component.literal(buffer.toString()).setStyle(current));
						buffer.setLength(0);
					}
					current = apply(current, format, base);
					i++;
					continue;
				}
			}
			buffer.append(c);
		}

		if (!buffer.isEmpty()) {
			root.append(Component.literal(buffer.toString()).setStyle(current));
		}
		return root;
	}

	/**
	 * Применяет один код форматирования к стилю.
	 * Цвет сбрасывает всё оформление — так работает ванильный Minecraft.
	 */
	private static Style apply(Style style, ChatFormatting format, Style base) {
		if (format == ChatFormatting.RESET) {
			return base;
		}
		return switch (format) {
			case BOLD -> style.withBold(true);
			case ITALIC -> style.withItalic(true);
			case UNDERLINE -> style.withUnderlined(true);
			case STRIKETHROUGH -> style.withStrikethrough(true);
			case OBFUSCATED -> style.withObfuscated(true);
			// остальное — цвета: они сбрасывают жирность/курсив и т.п.
			default -> Style.EMPTY.withColor(format);
		};
	}
}
