package ru.skyblockru.core;

import com.google.gson.JsonArray;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.regex.Pattern;
import java.util.regex.PatternSyntaxException;

/**
 * Один файл словаря. Формат JSON:
 *
 * <pre>
 * {
 *   "id": "chat",
 *   "priority": 20,
 *   "exact":    { "Your Island": "Твой остров" },
 *   "regex":    [ { "p": "^You found (.+)!$", "r": "Ты нашёл $1!" } ],
 *   "glossary": { "Enchanted": "Зачарованный" }
 * }
 * </pre>
 *
 * Пустая строка перевода = «ещё не переведено», такие записи движок пропускает.
 * Это нужно, чтобы заготовки (skeleton) можно было класть в игру как есть.
 */
public final class TranslationPack {

	/**
	 * @param translateGroups прогонять ли захваченные куски ($1, $2) через словарь.
	 *                        Задаётся полем "tg": true.
	 *                        <p>По умолчанию НЕТ, и это важно: в правиле
	 *                        «Piece Bonus: $1» захвачено имя перековки, а его
	 *                        переводить нельзя. Но у строк вида «Cobblestone.
	 *                        Minions also work when» название материала —
	 *                        обычное слово, и без перевода строка выходит
	 *                        наполовину английской.
	 */
	public record RegexRule(Pattern pattern, String replacement, boolean translateGroups) {
	}

	public final String id;
	public final int priority;
	public final Map<String, String> exact = new HashMap<>();
	public final List<RegexRule> regex = new ArrayList<>();
	public final Map<String, String> glossary = new HashMap<>();

	/**
	 * Абзацы: склеенная фраза целиком -> перевод целиком.
	 *
	 * <p>Нужны, потому что сервер режет описание на строки не по смыслу,
	 * а по ширине окна. Переводя абзац целиком, мы вольны переносить
	 * по-русски, а не втискиваться в чужие границы.
	 */
	public final Map<String, String> paragraphs = new HashMap<>();

	/**
	 * Где пакет разрешено применять: item_lore, chat, scoreboard и т.д.
	 * null — везде. Задаётся полем "only" и нужен, например, чтобы ванильные
	 * названия переводились в описаниях, но не в заголовках предметов —
	 * иначе по русскому названию не найти вещь на аукционе.
	 */
	public java.util.Set<String> only;

	/**
	 * Включён ли словарь по умолчанию. Поле {@code "default": false} делает его
	 * НЕОБЯЗАТЕЛЬНЫМ: файл есть, но не грузится, пока игрок сам не включит.
	 *
	 * <p>Нужно для вкусовых решений, где нет одного правильного ответа.
	 * Живой пример — ванильные названия предметов: кому-то удобнее «Булыжник»,
	 * а кто-то ищет вещи на аукционе по английскому названию и хочет видеть
	 * «Cobblestone». Раньше такой словарь просто не вписывали в index.json,
	 * то есть выбор был зашит намертво и правился пересборкой мода.
	 */
	public boolean defaultEnabled = true;

	/** Человеческое описание для {@code /skyblockru packs}: что этот словарь даёт. */
	public String about = "";

	/**
	 * Тождественная запись («Immolate» -> «Immolate») здесь ОСОЗНАННА.
	 *
	 * <p>Обычно такая запись бесполезна: движок и так оставит строку как есть,
	 * и {@code checkEntry} справедливо зовёт её мусором. Но у словаря заголовков
	 * ({@code 41-headers}) роль другая — он нужен НЕ ради перевода, а чтобы мод
	 * ОТРЕЗАЛ заголовок своей строкой: {@code Paragraphs.header} режет найденный
	 * перевод абзаца только тогда, когда вырезанное совпадает с переводом первой
	 * строки. Имена зачарований мы не переводим (они английские по решению
	 * игрока), значит их «перевод» и есть оригинал — и без такой записи
	 * {@code lookup} вернёт null, резка отменится, а заголовок слипнется
	 * с описанием.
	 *
	 * <p>⚠️ Поле нужно, чтобы отличить ЗАМЫСЕЛ от ошибки. Без него мод честно
	 * ругался на 1229 записей сразу — и настоящую беду в таком списке уже
	 * не разглядеть: жалоба, которая горит всегда, приучает не смотреть.
	 */
	public boolean allowIdentity;

	/**
	 * Переводы, привязанные к конкретному предмету: имя предмета -> (строка -> перевод).
	 *
	 * <p>Обычный словарь переводит строку одинаково везде, и это иногда врёт:
	 * обрывок «each.» у разных предметов продолжает разные фразы. Здесь можно
	 * задать перевод отдельно для предмета — он побеждает общий.
	 */
	public final Map<String, Map<String, String>> byItem = new HashMap<>();

	private TranslationPack(String id, int priority) {
		this.id = id;
		this.priority = priority;
	}

	public int size() {
		return exact.size() + regex.size() + glossary.size();
	}

	/**
	 * Разбирает пакет. Кривые записи пропускаются с записью в лог —
	 * один битый regex не должен ронять весь словарь.
	 */
	public static TranslationPack fromJson(String fallbackId, JsonObject json, List<String> problems) {
		String id = json.has("id") ? json.get("id").getAsString() : fallbackId;
		int priority = json.has("priority") ? json.get("priority").getAsInt() : 100;
		TranslationPack pack = new TranslationPack(id, priority);
		if (json.has("default") && json.get("default").isJsonPrimitive()) {
			pack.defaultEnabled = json.get("default").getAsBoolean();
		}
		if (json.has("about")) {
			String about = asString(json.get("about"));
			pack.about = about == null ? "" : about;
		}
		if (json.has("allowIdentity") && json.get("allowIdentity").isJsonPrimitive()) {
			pack.allowIdentity = json.get("allowIdentity").getAsBoolean();
		}

		if (json.has("only") && json.get("only").isJsonArray()) {
			java.util.Set<String> only = new java.util.HashSet<>();
			json.getAsJsonArray("only").forEach(element -> {
				String value = asString(element);
				if (value != null && !value.isBlank()) {
					only.add(value);
				}
			});
			if (!only.isEmpty()) {
				pack.only = only;
			}
		}

		if (json.has("exact") && json.get("exact").isJsonObject()) {
			for (Map.Entry<String, JsonElement> entry : json.getAsJsonObject("exact").entrySet()) {
				String value = asString(entry.getValue());
				if (value != null && !value.isEmpty()) {
					pack.exact.put(entry.getKey(), value);
				}
			}
		}

		if (json.has("byItem") && json.get("byItem").isJsonObject()) {
			for (Map.Entry<String, JsonElement> itemEntry : json.getAsJsonObject("byItem").entrySet()) {
				if (!itemEntry.getValue().isJsonObject()) {
					continue;
				}
				Map<String, String> lines = new HashMap<>();
				for (Map.Entry<String, JsonElement> line : itemEntry.getValue().getAsJsonObject().entrySet()) {
					String value = asString(line.getValue());
					if (value != null && !value.isEmpty()) {
						lines.put(line.getKey(), value);
					}
				}
				if (!lines.isEmpty()) {
					pack.byItem.put(itemEntry.getKey(), lines);
				}
			}
		}

		if (json.has("glossary") && json.get("glossary").isJsonObject()) {
			for (Map.Entry<String, JsonElement> entry : json.getAsJsonObject("glossary").entrySet()) {
				String value = asString(entry.getValue());
				if (value != null && !value.isEmpty()) {
					pack.glossary.put(entry.getKey(), value);
				}
			}
		}

		if (json.has("paragraphs") && json.get("paragraphs").isJsonObject()) {
			for (Map.Entry<String, JsonElement> entry : json.getAsJsonObject("paragraphs").entrySet()) {
				String value = asString(entry.getValue());
				if (value != null && !value.isEmpty()) {
					pack.paragraphs.put(entry.getKey(), value);
				}
			}
		}

		if (json.has("regex") && json.get("regex").isJsonArray()) {
			JsonArray rules = json.getAsJsonArray("regex");
			for (int i = 0; i < rules.size(); i++) {
				if (!rules.get(i).isJsonObject()) {
					continue;
				}
				JsonObject rule = rules.get(i).getAsJsonObject();
				String p = rule.has("p") ? asString(rule.get("p")) : null;
				String r = rule.has("r") ? asString(rule.get("r")) : null;
				if (p == null || p.isEmpty() || r == null || r.isEmpty()) {
					continue;
				}
				boolean translateGroups = rule.has("tg")
						&& rule.get("tg").isJsonPrimitive()
						&& rule.get("tg").getAsBoolean();
				try {
					pack.regex.add(new RegexRule(Pattern.compile(p), r, translateGroups));
				} catch (PatternSyntaxException exception) {
					problems.add(id + ": broken regular expression \"" + p + "» — " + exception.getDescription());
				}
			}
		}

		return pack;
	}

	private static String asString(JsonElement element) {
		return element != null && element.isJsonPrimitive() ? element.getAsString() : null;
	}
}
