package ru.skyblockru.core;

import net.minecraft.network.chat.Component;
import net.minecraft.network.chat.Style;
import net.minecraft.network.chat.TextColor;

import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.regex.Pattern;

/**
 * Имена собственные, которые Hypixel сам подсветил цветом.
 *
 * <p><b>Зачем.</b> В репликах NPC названия мест, имена персонажей и виды существ
 * выделены отдельным цветом: «go and find §6Captain Baha §fin the §bFishing
 * Outpost§f!». Переводить их нельзя — по ним ищут на аукционе и ходят по карте, —
 * а список таких имён до сих пор вёлся руками в tools/protected.py. Руками он
 * всегда неполон: на каждом новом острове появляются новые.
 *
 * <p>Цвет тут — <b>данные от сервера</b>, а не догадка по виду текста. Это тот же
 * принцип, что и у защиты абзацев от склейки разноцветных строк: сервер сам
 * говорит, где у него разметка, надо только не выбросить её по дороге.
 *
 * <p>⚠️ Дамп выбрасывал §-коды при записи, поэтому offline-инструменты этот
 * признак не видели вовсе — 0 строк чата из 468 сохранили хоть один код.
 * Собираем здесь, пока строка ещё цела.
 *
 * <p>Цвет приходит двумя путями (§-код внутри текста и стиль компонента), и
 * {@link Component#visit} отдаёт уже разобранные куски со стилем — то есть оба
 * случая покрыты одним обходом.
 */
public final class Highlights {

	/**
	 * Похоже на имя собственное: слова с заглавной, латиница, от одного до
	 * четырёх слов. Апостроф — ради «Necron's», дефис — ради «Nether-Warts».
	 */
	private static final String WORD = "[A-Z][A-Za-z'-]+";

	/** Связки внутри имени пишутся со строчной: «Trial of Fire», «Heart of the Mountain». */
	private static final String LINK = "(?:of|the|and|in|on)";

	private static final Pattern NAME = Pattern.compile(
			WORD + "(?:\\s+" + LINK + "){0,2}"
					+ "(?:\\s+" + WORD + "(?:\\s+" + LINK + "){0,2}){0,3}");

	/** Служебные слова: подсвечены, но именами не являются. */
	private static final java.util.Set<String> NOT_A_NAME = java.util.Set.of(
			"CLICK", "Click", "You", "Your", "The", "A", "An", "I", "It", "New",
			"Right", "Left", "Warning", "Error", "Yes", "No", "OK");

	private static final Map<String, AtomicInteger> SEEN = new ConcurrentHashMap<>();

	/** Потолок, чтобы редкая мусорная строка не раздула файл. */
	private static final int MAX = 3_000;

	private Highlights() {
	}

	/**
	 * Запоминает подсвеченные имена из строки.
	 *
	 * <p>Берём кусок, только если у него ЕСТЬ свой цвет и этот цвет отличается
	 * от цвета первого куска строки: подсветка — это выделение на фоне обычного
	 * текста, а строка целиком одного цвета ничего не выделяет.
	 */
	public static void note(Component line) {
		if (line == null || SEEN.size() >= MAX) {
			return;
		}
		java.util.List<String> parts = new java.util.ArrayList<>();
		java.util.List<String> colors = new java.util.ArrayList<>();
		line.visit((style, text) -> {
			if (!text.isBlank()) {
				TextColor color = style.getColor();
				parts.add(text);
				colors.add(color == null ? "" : color.serialize());
			}
			return Optional.empty();
		}, Style.EMPTY);

		if (parts.size() < 2) {
			return;
		}
		String base = baseColor(parts, colors);
		for (int i = 0; i < parts.size(); i++) {
			if (colors.get(i).isEmpty() || colors.get(i).equals(base)) {
				continue;
			}
			java.util.regex.Matcher found = NAME.matcher(parts.get(i).trim());
			while (found.find()) {
				String name = found.group();
				// одно короткое слово слишком часто оказывается просто
				// выделенным обычным словом, а не именем
				if (name.length() < 4 || NOT_A_NAME.contains(name)) {
					continue;
				}
				// ЗАГЛАВНЫМИ Hypixel набирает выделение, а не имена:
				// «CLICK HERE», «NEW RABBIT». Настоящие имена так не пишут.
				if (name.equals(name.toUpperCase(java.util.Locale.ROOT))) {
					continue;
				}
				SEEN.computeIfAbsent(name, key -> new AtomicInteger()).incrementAndGet();
			}
		}
	}

	/**
	 * Цвет, которым набрана БОЛЬШАЯ ЧАСТЬ строки, — он и есть фон.
	 *
	 * <p>⚠️ Не цвет первого куска. У реплики NPC первым идёт жёлтое «[NPC] »,
	 * и если считать фоном жёлтый, то фоном перестанет быть белое тело реплики —
	 * тогда «Welcome to the...» тоже сойдёт за подсветку. По объёму текста
	 * признак устойчив: фон всегда длиннее выделения.
	 */
	private static String baseColor(java.util.List<String> parts, java.util.List<String> colors) {
		Map<String, Integer> weight = new java.util.HashMap<>();
		for (int i = 0; i < parts.size(); i++) {
			weight.merge(colors.get(i), parts.get(i).length(), Integer::sum);
		}
		return weight.entrySet().stream()
				.max(Map.Entry.comparingByValue())
				.map(Map.Entry::getKey)
				.orElse("");
	}

	public static int count() {
		return SEEN.size();
	}

	/** Имя -> сколько раз встретилось, самые частые сверху. */
	public static Map<String, Integer> collected() {
		Map<String, Integer> out = new LinkedHashMap<>();
		SEEN.entrySet().stream()
				.sorted(Comparator.<Map.Entry<String, AtomicInteger>>comparingInt(
						entry -> -entry.getValue().get()).thenComparing(Map.Entry::getKey))
				.forEach(entry -> out.put(entry.getKey(), entry.getValue().get()));
		return out;
	}

	/** Восстановление накопленного при старте: дамп живёт между сессиями. */
	public static void restore(Map<String, Integer> saved) {
		saved.forEach((name, count) ->
				SEEN.computeIfAbsent(name, key -> new AtomicInteger()).addAndGet(count));
	}
}
