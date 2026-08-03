package ru.skyblockru.core;

import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;

/**
 * Сбор всего, что помогает понять, почему перевод ведёт себя не так.
 *
 * <p>Собирается четыре разных вида сведений, и каждый отвечает на свой вопрос:
 * <ul>
 *   <li><b>проблемы словарей</b> — почему строка не переводится, хотя я её вписал;</li>
 *   <li><b>попадания</b> — что вообще работает и каким видом правил;</li>
 *   <li><b>потеря цвета</b> — почему разноцветная строка стала одноцветной;</li>
 *   <li><b>ошибки</b> — что упало внутри перевода (наружу мы их не пускаем,
 *       иначе кривое правило роняло бы отрисовку игры).</li>
 * </ul>
 *
 * Отчёт целиком пишется в файл: в чат столько строк не влезет.
 */
public final class Diagnostics {

	/** Сколько строк перевели, по месту появления. */
	private static final Map<String, AtomicInteger> HITS = new ConcurrentHashMap<>();

	/** Сколько строк перевели, по виду правила (точное / шаблон / регулярка / глоссарий). */
	private static final Map<String, AtomicInteger> BY_KIND = new ConcurrentHashMap<>();

	/** Строки, где перевод потерял цвета оригинала. Ключ — сама строка. */
	private static final Map<String, AtomicInteger> COLOR_LOSS = new ConcurrentHashMap<>();
	private static final Map<String, AtomicInteger> COLOR_GUARD = new ConcurrentHashMap<>();

	/** Регулярки, которые хоть раз сработали, — чтобы найти мёртвые правила. */
	private static final Map<String, AtomicInteger> RULE_HITS = new ConcurrentHashMap<>();

	/** Пойманные исключения. Держим немного: важен факт и место, а не тысяча повторов. */
	private static final List<String> ERRORS = Collections.synchronizedList(new ArrayList<>());

	private static final int MAX_ERRORS = 30;
	private static final int MAX_COLOR_LOSS = 200;

	/** Замечания, найденные при загрузке словарей. Перезаписываются при каждой перезагрузке. */
	private static volatile List<String> loadProblems = List.of();

	private static final long STARTED = System.currentTimeMillis();

	public static final String KIND_EXACT = "exact match";
	public static final String KIND_TEMPLATE = "number template";
	public static final String KIND_REGEX = "regex";
	public static final String KIND_GLOSSARY = "glossary";
	public static final String KIND_SEGMENT = "by segments";
	public static final String KIND_BY_ITEM = "per-item override";
	public static final String KIND_COLUMNS = "by columns";
	public static final String KIND_PARAGRAPH = "whole paragraph";

	private Diagnostics() {
	}

	public static void hit(String source, String kind) {
		HITS.computeIfAbsent(source, key -> new AtomicInteger()).incrementAndGet();
		BY_KIND.computeIfAbsent(kind, key -> new AtomicInteger()).incrementAndGet();
	}

	public static void ruleHit(String pattern) {
		RULE_HITS.computeIfAbsent(pattern, key -> new AtomicInteger()).incrementAndGet();
	}

	/**
	 * Оригинал был раскрашен в несколько цветов, а перевод получился одноцветным.
	 * Лечится тем, что переводчик прописывает цвета прямо в перевод кодами §.
	 */
	public static void colorLoss(String plain) {
		if (COLOR_LOSS.size() >= MAX_COLOR_LOSS && !COLOR_LOSS.containsKey(plain)) {
			return;
		}
		boolean fresh = !COLOR_LOSS.containsKey(plain);
		COLOR_LOSS.computeIfAbsent(plain, key -> new AtomicInteger()).incrementAndGet();
		// О НОВОЙ потере говорим сразу: счётчик читают редко, а игрок смотрит
		// на экран прямо сейчас. Повторы молчат — иначе чат зальёт одним и тем же.
		if (fresh) {
			UnknownStrings.noteProblem("color", plain);
		}
	}

	/**
	 * Абзац НЕ склеен, потому что строки разного цвета — сработала защита.
	 *
	 * <p>⚠️ Это не поломка, а наоборот. Раньше считалось тем же счётчиком, что и
	 * настоящая потеря цвета, и «строк потеряли цвет: 537» выглядело как беда,
	 * хотя означало ровно обратное: 537 раз мы вовремя не тронули пару
	 * «подпись / значение». Один счётчик на два противоположных события — верный
	 * способ не заметить настоящее.
	 */
	public static void colorGuard(String plain) {
		if (COLOR_GUARD.size() >= MAX_COLOR_LOSS && !COLOR_GUARD.containsKey(plain)) {
			return;
		}
		boolean fresh = !COLOR_GUARD.containsKey(plain);
		COLOR_GUARD.computeIfAbsent(plain, key -> new AtomicInteger()).incrementAndGet();
		// ⚠️ Здесь перевод УЖЕ НАЙДЕН и всё же не показан — то есть оплаченный
		// текст не дошёл до экрана. Молчать об этом дороже всего: именно так
		// зелье Ophelia оставалось английским на пять строк из шести.
		if (fresh) {
			UnknownStrings.noteProblem("guard", plain);
		}
	}

	public static int colorGuardCount() {
		return COLOR_GUARD.size();
	}

	public static void error(String where, Throwable throwable) {
		if (ERRORS.size() >= MAX_ERRORS) {
			return;
		}
		ERRORS.add(where + ": " + throwable);
	}

	public static void setLoadProblems(List<String> problems) {
		loadProblems = List.copyOf(problems);
	}

	public static int loadProblemCount() {
		return loadProblems.size();
	}

	public static int colorLossCount() {
		return COLOR_LOSS.size();
	}

	public static int errorCount() {
		return ERRORS.size();
	}

	public static int hitTotal() {
		return HITS.values().stream().mapToInt(AtomicInteger::get).sum();
	}

	public static void reset() {
		HITS.clear();
		BY_KIND.clear();
		COLOR_LOSS.clear();
		COLOR_GUARD.clear();
		RULE_HITS.clear();
		ERRORS.clear();
	}

	/** Полный отчёт. Пишется в файл целиком, в чат идёт только сводка. */
	public static String report(List<String> allRulePatterns) {
		StringBuilder out = new StringBuilder();
		long minutes = (System.currentTimeMillis() - STARTED) / 60000L;

		out.append("=== SkyblockRU: diagnostics ===\n");
		out.append("uptime: ").append(minutes).append(" min\n");
		out.append("on Hypixel: ").append(Hypixel.isOnHypixel() ? "yes" : "no").append('\n');
		out.append('\n');

		out.append("--- DICTIONARIES ---\n");
		out.append("files: ").append(Translator.packCount())
				.append(", lines: ").append(Translator.exactCount())
				.append(", rules: ").append(Translator.regexCount())
				.append(", terms: ").append(Translator.glossaryCount()).append('\n');
		if (loadProblems.isEmpty()) {
			out.append("no load problems\n");
		} else {
			out.append("LOAD PROBLEMS (").append(loadProblems.size()).append("):\n");
			for (String problem : loadProblems) {
				out.append("  ! ").append(problem).append('\n');
			}
		}
		out.append('\n');

		out.append("--- TRANSLATED THIS SESSION ---\n");
		if (HITS.isEmpty()) {
			out.append("nothing at all - check that you are on Hypixel and translation is on\n");
		} else {
			out.append("total: ").append(hitTotal()).append('\n');
			sorted(HITS).forEach((source, count) ->
					out.append("  ").append(source).append(": ").append(count).append('\n'));
			out.append("by rule kind:\n");
			sorted(BY_KIND).forEach((kind, count) ->
					out.append("  ").append(kind).append(": ").append(count).append('\n'));
		}
		out.append('\n');

		out.append("--- UNTRANSLATED ---\n");
		out.append("unique lines: ").append(UnknownStrings.total()).append('\n');
		UnknownStrings.countsBySource().forEach((source, count) ->
				out.append("  ").append(source).append(": ").append(count).append('\n'));
		out.append("details in dump/untranslated.txt\n");
		out.append('\n');

		out.append("--- COLOR LOSS ---\n");
		if (COLOR_LOSS.isEmpty()) {
			out.append("none\n");
		} else {
			out.append("The original was multi-colored, the translation came out single-colored.\n");
			out.append("Fix: write the colors into the translation itself (\u00a7c red, \u00a7a green, \u00a7b blue).\n");
			sorted(COLOR_LOSS).forEach((text, count) ->
					out.append("  ").append(count).append("x  ").append(text).append('\n'));
		}
		out.append('\n');

		out.append("--- RULES THAT NEVER MATCHED ---\n");
		List<String> dead = new ArrayList<>();
		for (String pattern : allRulePatterns) {
			if (!RULE_HITS.containsKey(pattern)) {
				dead.add(pattern);
			}
		}
		if (dead.isEmpty()) {
			out.append("none, every rule fired\n");
		} else {
			out.append("Either such lines have not shown up yet, or the rule is wrong.\n");
			for (String pattern : dead) {
				out.append("  ").append(pattern).append('\n');
			}
		}
		out.append('\n');

		out.append("--- ERRORS ---\n");
		if (ERRORS.isEmpty()) {
			out.append("none\n");
		} else {
			synchronized (ERRORS) {
				for (String error : ERRORS) {
					out.append("  ! ").append(error).append('\n');
				}
			}
		}

		return out.toString();
	}

	private static Map<String, Integer> sorted(Map<String, AtomicInteger> source) {
		Map<String, Integer> out = new LinkedHashMap<>();
		source.entrySet().stream()
				.sorted((a, b) -> Integer.compare(b.getValue().get(), a.getValue().get()))
				.forEach(entry -> out.put(entry.getKey(), entry.getValue().get()));
		return out;
	}
}
