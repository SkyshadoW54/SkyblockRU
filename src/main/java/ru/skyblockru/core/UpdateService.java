package ru.skyblockru.core;

import com.google.gson.Gson;
import com.google.gson.JsonArray;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import net.minecraft.ChatFormatting;
import net.minecraft.client.Minecraft;
import net.minecraft.network.chat.Component;
import ru.skyblockru.SkyblockRuClient;
import ru.skyblockru.config.RuConfig;

import java.io.IOException;
import java.io.InputStream;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.security.MessageDigest;
import java.time.Duration;
import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Set;
import java.util.regex.Pattern;

/**
 * Обновление словарей по сети.
 *
 * <p><b>Скачиваются только тексты, никогда не код.</b> Это принципиально:
 * мод, который сам тянет и исполняет код с сервера, устроен как бэкдор — угонят
 * хостинг, и чужой код выполнится у всех игроков разом. Поэтому обновляются
 * только JSON-словари, а новый jar игрок ставит руками по ссылке.
 *
 * <p>Словари живут отдельно от кода: файлы из config/skyblockru/packs читаются
 * с диска и перекрывают встроенные в jar. Поэтому обновление текста не требует
 * ни нового jar, ни даже перезапуска игры — достаточно перечитать словари.
 *
 * <p>Проверки, без которых сюда нельзя (манифест приходит из сети, доверия ему нет):
 * <ul>
 *   <li>имя файла — только простое имя .json, без путей: иначе манифест мог бы
 *       записать файл куда угодно, вплоть до папки модов;</li>
 *   <li>адрес — только https;</li>
 *   <li>размер ограничен;</li>
 *   <li>содержимое обязано разбираться как словарь, иначе файл не сохраняется.</li>
 * </ul>
 */
public final class UpdateService {

	private static final Gson GSON = new Gson();

	/** Только простое имя файла. Ни путей, ни «..», ни обратных слэшей. */
	private static final Pattern SAFE_NAME = Pattern.compile("[A-Za-z0-9._-]{1,64}\\.json");

	/**
	 * Предел размера словаря.
	 *
	 * <p>⚠️ Поднят с 5 МБ: корпус абзацев (`96-paragraphs.json`) уже весит
	 * 2.9 МБ и растёт с каждым переводом. Упереться в потолок здесь значило бы
	 * ТИХО перестать обновлять самый крупный словарь — а молчаливый упор в
	 * предел этот проект уже дважды стоил потерянных данных (сбор подсказок
	 * и сбор цветов).
	 *
	 * <p>Предел всё же нужен: файл качается целиком в память, и без него чужой
	 * (или взломанный) сервер мог бы прислать гигабайт.
	 */
	private static final long MAX_PACK_BYTES = 16L * 1024 * 1024;
	private static final Duration TIMEOUT = Duration.ofSeconds(20);

	private static final HttpClient HTTP = HttpClient.newBuilder()
			.connectTimeout(TIMEOUT)
			.followRedirects(HttpClient.Redirect.NORMAL)
			.build();

	private static volatile long lastCheck;
	private static volatile boolean running;

	/**
	 * Сколько неудач подряд стерпеть молча, прежде чем сказать игроку.
	 *
	 * <p>⚠️ Жаловаться на ПЕРВУЮ неудачу нельзя. Проверка идёт при каждом заходе
	 * на сервер, а сеть моргает: у игрока пропал Wi-Fi на секунду, хостинг
	 * перезапустился, провайдер придержал соединение — и мод начнёт писать
	 * в чат при каждом входе. Это ровно тот шум, ради которого 02.08 выключили
	 * `notifyNewStrings` и `notifyProblems`: сообщение, которое видишь каждый
	 * раз, перестают читать вместе со всеми остальными.
	 */
	private static final int QUIET_FAILURES = 3;

	/** Неудач подряд. Сбрасывается, как только сервер ответил. */
	private static volatile int failures;

	/** Уже пожаловались — второй раз за запуск игры не повторяем. */
	private static volatile boolean warned;

	private UpdateService() {
	}

	/** Вызывается при заходе на сервер. Сама решает, пора ли проверять. */
	public static void onJoinServer() {
		RuConfig config = RuConfig.get();
		if (!config.autoUpdate || config.effectiveUpdateUrl().isBlank()) {
			return;
		}
		if (config.onlyOnHypixel && !Hypixel.isOnHypixel()) {
			return;
		}
		long now = System.currentTimeMillis();
		if (now - lastCheck < config.updateCheckMinutes * 60_000L) {
			return;
		}
		lastCheck = now;
		check(false);
	}

	/**
	 * Список файлов, которые скачали МЫ. Лежит рядом со словарями, но вне
	 * папки {@code packs} — иначе {@link Translator} попытался бы прочитать
	 * его как пакет.
	 */
	/** Префикс записи журнала для словаря: {@code packs/25-sidebar.json}. */
	private static final String PACKS_PREFIX = "packs/";

	private static Path ledger() {
		return SkyblockRuClient.configDir().resolve("downloaded-packs.txt");
	}

	/**
	 * Что мы скачивали раньше: строки вида {@code packs/40-lore.json}.
	 *
	 * <p>⚠️ БЕЗ ЭТОГО СПИСКА УДАЛЯТЬ НЕЛЬЗЯ. В той же папке лежат словари,
	 * которые игрок положил САМ, — они в манифесте не значатся по построению.
	 * Снести «всё, чего нет в манифесте» значит уничтожить его работу.
	 * Поэтому трогаем ровно то, что принесли сами.
	 */
	private static Set<String> ledgerRead() {
		try {
			Path file = ledger();
			if (!Files.isRegularFile(file)) {
				return new LinkedHashSet<>();
			}
			return new LinkedHashSet<>(Files.readAllLines(file, StandardCharsets.UTF_8)
					.stream().map(String::trim).filter(s -> !s.isEmpty()).toList());
		} catch (IOException | RuntimeException exception) {
			return new LinkedHashSet<>();
		}
	}

	/**
	 * Имена словарей, которые мы скачали из облака: {@code 25-sidebar.json}.
	 *
	 * <p>Нужны {@link Translator}: скачанный словарь ЗАМЕНЯЕТ встроенный
	 * с тем же именем, а не грузится рядом. Иначе облако может лишь дополнять:
	 * записи {@code exact} оно перекроет по ключу, а вот УДАЛИТЬ запись или
	 * заменить ПРАВИЛО — нет. Правила перебираются до первого совпадения,
	 * и встроенное, добавленное раньше, выигрывает у свежего.
	 *
	 * <p>⚠️ Берём ровно то, что принесли САМИ. Словарь, положенный игроком
	 * руками, встроенный не заменяет: он в этом списке не значится, и его
	 * записи по-прежнему лишь перекрывают наши — как было всегда.
	 */
	static Set<String> downloadedPackFiles() {
		Set<String> out = new LinkedHashSet<>();
		for (String record : ledgerRead()) {
			if (record.startsWith(PACKS_PREFIX)) {
				out.add(record.substring(PACKS_PREFIX.length()));
			}
		}
		return out;
	}

	private static void ledgerWrite(Set<String> names) {
		try {
			Files.writeString(ledger(), String.join("\n", names), StandardCharsets.UTF_8);
		} catch (IOException exception) {
			Diagnostics.error("update ledger", exception);
		}
	}

	/**
	 * Убрать то, что мы скачали раньше, а в манифесте этого больше нет.
	 *
	 * <p>Зачем: пока удаления не было, ОШИБОЧНО выложенный словарь нельзя было
	 * отозвать вовсе. Убираешь его из манифеста — у скачавших он остаётся
	 * лежать и применяться, потому что мод читает папку целиком. Единственным
	 * способом отзыва была подмена содержимого на правильное.
	 *
	 * @return имена удалённых файлов
	 */
	private static List<String> dropOrphans(Path packs, Path wikiDir,
	                                        Set<String> keepPacks, Set<String> keepWiki) {
		Set<String> mine = ledgerRead();
		if (mine.isEmpty()) {
			return List.of();
		}
		List<String> removed = new ArrayList<>();
		Set<String> left = new LinkedHashSet<>(mine);
		for (String record : orphansOf(mine, keepPacks, keepWiki)) {
			boolean wiki = record.startsWith("wiki/");
			String name = record.substring(record.indexOf('/') + 1);
			Path dir = wiki ? wikiDir : packs;
			Path target = dir.resolve(name);
			if (!target.toAbsolutePath().normalize()
					.startsWith(dir.toAbsolutePath().normalize())) {
				continue;
			}
			try {
				if (Files.deleteIfExists(target)) {
					removed.add(name);
				}
				left.remove(record);
			} catch (IOException exception) {
				Diagnostics.error("update cleanup", exception);
			}
		}
		if (!removed.isEmpty()) {
			ledgerWrite(left);
		}
		return removed;
	}

	/**
	 * Какие из НАШИХ файлов манифест больше не объявляет.
	 *
	 * <p>Вынесено отдельно и без работы с диском НАРОЧНО: это код, который
	 * УДАЛЯЕТ файлы у игрока, и ошибка тут стирает чужую работу. Чистую
	 * функцию можно прогнать настоящей Java без игры — что и сделано.
	 *
	 * <p>⚠️ Записи без префикса (`packs/`, `wiki/`) пропускаем: их писала
	 * какая-то другая версия мода, и куда они указывают — неизвестно.
	 * ⚠️ Имя проверяем тем же правилом, что и при скачивании: список лежит
	 * на диске игрока, а мы по нему удаляем.
	 */
	static List<String> orphansOf(Set<String> mine, Set<String> keepPacks, Set<String> keepWiki) {
		List<String> out = new ArrayList<>();
		for (String record : mine) {
			boolean wiki = record.startsWith("wiki/");
			boolean pack = record.startsWith("packs/");
			if (!wiki && !pack) {
				continue;
			}
			String name = record.substring(record.indexOf('/') + 1);
			if (!SAFE_NAME.matcher(name).matches()) {
				continue;
			}
			if ((wiki ? keepWiki : keepPacks).contains(name)) {
				continue;
			}
			out.add(record);
		}
		return out;
	}

	/**
	 * Ключ сообщения под число словарей: «1 словарь», «2 словаря», «5 словарей».
	 *
	 * <p>⚠️ Было одно сообщение на все числа — и в чате выходило
	 * «Переводы обновлены (1 файлов)». Русское числительное требует трёх форм,
	 * и подставить их одной строкой нельзя: правило зависит от ДВУХ последних
	 * цифр, а не от последней. 11–14 всегда «словарей», хотя кончаются на 1–4.
	 *
	 * <p>Английскому хватило бы двух форм, поэтому выбор делаем ключом,
	 * а не склейкой строк: каждый язык объявляет свои формы в своём файле.
	 */
	static String doneKey(int count) {
		return plural("skyblockru.update.done", count);
	}

	/** То же для сообщения об отозванных словарях. */
	static String goneKey(int count) {
		return plural("skyblockru.update.gone", count);
	}

	/** Форма числительного: одна на все сообщения, чтобы правило жило в одном месте. */
	private static String plural(String base, int count) {
		int tail = count % 100;
		if (tail >= 11 && tail <= 14) {
			return base + ".many";
		}
		return switch (count % 10) {
			case 1 -> base + ".one";
			case 2, 3, 4 -> base + ".few";
			default -> base + ".many";
		};
	}

	/**
	 * Проверить и скачать обновления словарей.
	 *
	 * @param loud true — писать в чат и когда обновлений нет (для ручной команды)
	 */
	public static void check(boolean loud) {
		if (running) {
			return;
		}
		running = true;
		Thread.ofVirtual().name("skyblockru-update").start(() -> {
			try {
				run(loud);
			} catch (Exception exception) {
				Diagnostics.error("dictionary update", exception);
				if (loud) {
					// Спросили руками — отвечаем сразу и с причиной.
					chat(ChatFormatting.RED, Component.translatable("skyblockru.update.failed", exception.toString()));
				} else {
					noteFailure();
				}
			} finally {
				running = false;
			}
		});
	}

	private static void run(boolean loud) throws Exception {
		String url = RuConfig.get().effectiveUpdateUrl();
		if (url.isBlank()) {
			if (loud) {
				chat(ChatFormatting.YELLOW, Component.translatable("skyblockru.update.nourl"));
			}
			return;
		}

		String body = fetch(url);
		// Сервер ответил — значит связь есть, и прошлые неудачи больше не в счёт.
		// ⚠️ Сбрасываем ЗДЕСЬ, а не в конце: дальше файл может не пройти проверку
		// содержимого, и это уже не «обновление не пришло», а другая беда.
		failures = 0;
		warned = false;
		JsonObject manifest = GSON.fromJson(body, JsonObject.class);

		Path packs = SkyblockRuClient.packsDir();
		Files.createDirectories(packs);

		List<String> updated = new ArrayList<>();
		// что манифест объявляет сейчас — по этому решаем, чему больше не место
		Set<String> keepPacks = new LinkedHashSet<>();
		Set<String> keepWiki = new LinkedHashSet<>();
		Set<String> mine = ledgerRead();

		JsonArray list = manifest.getAsJsonArray("packs");
		if (list != null) {
			for (JsonElement element : list) {
				JsonObject entry = element.getAsJsonObject();
				String name = string(entry, "file");
				String packUrl = string(entry, "url");
				String hash = string(entry, "sha256");

				if (name == null || packUrl == null || !SAFE_NAME.matcher(name).matches()) {
					Diagnostics.error("update", new IllegalArgumentException(
							"manifest sent an invalid file name: " + name));
					continue;
				}
				if (!packUrl.toLowerCase(Locale.ROOT).startsWith("https://")) {
					Diagnostics.error("update", new IllegalArgumentException(
							"address is not https: " + packUrl));
					continue;
				}

				Path target = packs.resolve(name);
				// проверка от выхода из папки: имя уже отфильтровано, но пусть будет и здесь
				if (!target.toAbsolutePath().normalize().startsWith(packs.toAbsolutePath().normalize())) {
					continue;
				}
				keepPacks.add(name);
				if (alreadyHave(target, hash, name, false)) {
					continue; // уже свежий — на диске или внутри jar
				}

				String content = fetch(packUrl);
				if (content.length() > MAX_PACK_BYTES) {
					Diagnostics.error("update", new IllegalStateException(
							"file too large: " + name));
					continue;
				}
				if (!looksLikePack(content)) {
					Diagnostics.error("update", new IllegalStateException(
							"not a dictionary: " + name));
					continue;
				}

				Path temp = packs.resolve(name + ".tmp");
				Files.writeString(temp, content, StandardCharsets.UTF_8);
				Files.move(temp, target, StandardCopyOption.REPLACE_EXISTING);
				updated.add(name);
				// помечаем как СВОЙ: только такие мы вправе удалить потом
				mine.add("packs/" + name);
			}
		}

		// ⚠️ Справка обновляется ТЕМ ЖЕ путём, но лежит в своей папке: она не
		// словарь, и класть её в packs нельзя — Translator попытался бы её
		// прочитать как пакет. Формат манифеста тот же: file, url, sha256.
		JsonArray wiki = manifest.getAsJsonArray("wiki");
		if (wiki != null) {
			Path wikiDir = SkyblockRuClient.configDir().resolve("wiki");
			Files.createDirectories(wikiDir);
			for (JsonElement element : wiki) {
				JsonObject entry = element.getAsJsonObject();
				String name = string(entry, "file");
				String fileUrl = string(entry, "url");
				String hash = string(entry, "sha256");

				if (name == null || fileUrl == null || !SAFE_NAME.matcher(name).matches()) {
					Diagnostics.error("update", new IllegalArgumentException(
							"manifest sent an invalid wiki file name: " + name));
					continue;
				}
				if (!fileUrl.toLowerCase(Locale.ROOT).startsWith("https://")) {
					Diagnostics.error("update", new IllegalArgumentException(
							"address is not https: " + fileUrl));
					continue;
				}
				Path target = wikiDir.resolve(name);
				if (!target.toAbsolutePath().normalize()
						.startsWith(wikiDir.toAbsolutePath().normalize())) {
					continue;
				}
				keepWiki.add(name);
				if (alreadyHave(target, hash, name, true)) {
					continue;
				}
				String content = fetch(fileUrl);
				if (content.length() > MAX_PACK_BYTES) {
					Diagnostics.error("update", new IllegalStateException(
							"file too large: " + name));
					continue;
				}
				if (!looksLikeWiki(content)) {
					Diagnostics.error("update", new IllegalStateException(
							"not a wiki file: " + name));
					continue;
				}
				Path temp = wikiDir.resolve(name + ".tmp");
				Files.writeString(temp, content, StandardCharsets.UTF_8);
				Files.move(temp, target, StandardCopyOption.REPLACE_EXISTING);
				updated.add(name);
				mine.add("wiki/" + name);
			}
		}

		if (!mine.isEmpty()) {
			ledgerWrite(mine);
		}

		// ⚠️ Отзыв словаря. Раньше его не было вовсе: убранный из манифеста файл
		// оставался у игрока и продолжал применяться, потому что мод читает папку
		// целиком. Ошибку можно было только ПЕРЕКРЫТЬ новым содержимым.
		// Удаляем строго своё — см. dropOrphans.
		List<String> removed = dropOrphans(packs,
				SkyblockRuClient.configDir().resolve("wiki"), keepPacks, keepWiki);
		if (!removed.isEmpty()) {
			chat(ChatFormatting.GRAY,
					Component.translatable(goneKey(removed.size()), removed.size()));
		}

		if (!updated.isEmpty() || !removed.isEmpty()) {
			// Перечитывать словари ОБЯЗАТЕЛЬНО в игровом потоке: качаем мы в фоновом,
			// а перевод читает те же таблицы на каждом кадре отрисовки. Перезапись
			// на ходу из другого потока — это мусор в чтении или зависание.
			Minecraft client = Minecraft.getInstance();
			if (client != null) {
				client.execute(() -> Translator.reload(packs));
			} else {
				Translator.reload(packs);
			}
			if (!updated.isEmpty()) {
				chat(ChatFormatting.GREEN,
						Component.translatable(doneKey(updated.size()), updated.size()));
			}
			String note = string(manifest, "note");
			if (note != null && !note.isBlank()) {
				chat(ChatFormatting.GRAY, Component.translatable("skyblockru.update.note", note));
			}
		} else if (loud) {
			chat(ChatFormatting.GRAY, Component.translatable("skyblockru.update.fresh"));
		}

		// Про новую версию самого мода только сообщаем — скачивать и подменять jar не будем.
		JsonObject mod = manifest.getAsJsonObject("mod");
		if (mod != null) {
			String version = string(mod, "version");
			String link = string(mod, "url");
			// ⚠️ Сравниваем ЛЕВУЮ часть версии: в jar она с хвостом версии игры
			// («0.2.0+26.2»), а в манифесте голая («0.2.0»). Наивное equals
			// показывало игроку «вышла версия 0.2.0» при установленной 0.2.0.
			if (version != null && !Versions.same(version, SkyblockRuClient.modVersion())) {
				chat(ChatFormatting.AQUA, Component.translatable("skyblockru.update.newversion", version,
						link != null ? " — " + link : ""));
				chat(ChatFormatting.GRAY, Component.translatable("skyblockru.update.manual"));
			}
		}
	}

	/**
	 * Этот файл уже есть — на диске ИЛИ внутри jar?
	 *
	 * <p>⚠️ Проверять ТОЛЬКО диск было мало, и это стоило бы трафика на пустом
	 * месте. У свежепоставленного мода папка `config/skyblockru/packs` пуста,
	 * поэтому первое же обновление качало ВСЕ словари — 6 МБ, — хотя они
	 * побайтово те же, что лежат внутри jar. Перевод от этого не менялся
	 * ни на строку. Тысяча игроков дала бы 6 ГБ впустую.
	 *
	 * <p>Сверено, что сравнение осмысленно: Loom кладёт ресурсы в jar как есть,
	 * все 33 файла совпадают с исходниками байт в байт.
	 *
	 * <p>⚠️ Хеш берём из манифеста — то есть от ВЫЛОЖЕННОГО файла. Совпал
	 * со встроенным — значит облако несёт ровно то, что у игрока уже есть,
	 * и качать нечего. Разошёлся — качаем, даже если файл лежит внутри jar.
	 */
	private static boolean alreadyHave(Path target, String hash, String name,
			boolean wiki) throws IOException {
		if (hash == null) {
			// Манифест не назвал хеш — сверять не с чем, качаем.
			return false;
		}
		if (Files.exists(target)) {
			return hash.equalsIgnoreCase(sha256(Files.readAllBytes(target)));
		}
		byte[] inside = builtin(name, wiki);
		return inside != null && hash.equalsIgnoreCase(sha256(inside));
	}

	/**
	 * Байты файла, встроенного в jar, или null.
	 *
	 * <p>Словари лежат либо в папке языка, либо в `common` (там те, что работают
	 * на любом языке). Спрашиваем обе — какая подойдёт, та и ответит.
	 */
	private static byte[] builtin(String name, boolean wiki) {
		String[] candidates = wiki
				? new String[] {"/assets/skyblockru/wiki/" + name}
				: new String[] {
					"/assets/skyblockru/packs/" + Translator.dictionaryLanguage() + "/" + name,
					"/assets/skyblockru/packs/common/" + name,
				};
		for (String path : candidates) {
			try (InputStream stream = UpdateService.class.getResourceAsStream(path)) {
				if (stream != null) {
					return stream.readAllBytes();
				}
			} catch (IOException ignored) {
				// не прочиталось — не беда, просто скачаем файл
			}
		}
		return null;
	}

	/**
	 * Автоматическая проверка не удалась — сказать игроку, но не в первый раз.
	 *
	 * <p>⚠️ Сообщение написано так, чтобы НЕ ПУГАТЬ: перевод продолжает работать
	 * на словарях внутри jar, не пришло только пополнение. Иначе игрок решит,
	 * что мод сломался, и пойдёт его переустанавливать — а чинить нечего.
	 */
	private static void noteFailure() {
		failures++;
		if (failures < QUIET_FAILURES || warned) {
			return;
		}
		warned = true;
		chat(ChatFormatting.YELLOW,
				Component.translatable("skyblockru.update.offline", failures));
	}

	/**
	 * Похоже ли содержимое на словарь. Файл, который не разбирается, не сохраняем.
	 *
	 * <p>⚠️ ПЕРЕЧИСЛЯТЬ НАДО ВСЕ СЕКЦИИ, КОТОРЫЕ ЧИТАЕТ ДВИЖОК. Сперва здесь
	 * стояли только {@code exact}, {@code regex} и {@code glossary} — и три
	 * живых словаря не прошли бы проверку: {@code 93-abilities},
	 * {@code 94-menus} и {@code 97-enchant-sections} держат ОДНУ секцию
	 * {@code paragraphs}, и ничего больше. Обновление таких файлов
	 * не сохранилось бы, причём МОЛЧА — ошибка ушла бы в лог, а игрок увидел
	 * бы «переводы обновлены» без этих словарей.
	 */
	private static boolean looksLikePack(String content) {
		try {
			JsonObject json = GSON.fromJson(content, JsonObject.class);
			return json != null
					&& (json.has("exact") || json.has("regex") || json.has("glossary")
							|| json.has("paragraphs") || json.has("byItem"));
		} catch (RuntimeException exception) {
			return false;
		}
	}

	/**
	 * Похоже ли содержимое на файл справки.
	 *
	 * <p>Признак свой, а не как у словаря: у справки нет ни {@code exact},
	 * ни {@code regex} — там {@code terms} со статьями. Без отдельной проверки
	 * файл справки не прошёл бы и не сохранился.
	 */
	private static boolean looksLikeWiki(String content) {
		try {
			JsonObject json = GSON.fromJson(content, JsonObject.class);
			return json != null && json.has("terms")
					&& json.get("terms").isJsonObject();
		} catch (RuntimeException exception) {
			return false;
		}
	}

	private static String fetch(String url) throws IOException, InterruptedException {
		HttpRequest request = HttpRequest.newBuilder(URI.create(url))
				.timeout(TIMEOUT)
				.header("User-Agent", "SkyblockRU/" + SkyblockRuClient.modVersion())
				.GET()
				.build();
		HttpResponse<String> response = HTTP.send(request, HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
		if (response.statusCode() != 200) {
			throw new IOException("server answered " + response.statusCode() + " for " + url);
		}
		return response.body();
	}

	private static String sha256(byte[] data) {
		try {
			MessageDigest digest = MessageDigest.getInstance("SHA-256");
			StringBuilder out = new StringBuilder();
			for (byte b : digest.digest(data)) {
				out.append(String.format("%02x", b));
			}
			return out.toString();
		} catch (Exception exception) {
			return "";
		}
	}

	private static String string(JsonObject json, String key) {
		JsonElement element = json.get(key);
		return element != null && element.isJsonPrimitive() ? element.getAsString() : null;
	}

	private static void chat(ChatFormatting color, Component text) {
		Minecraft client = Minecraft.getInstance();
		if (client == null) {
			return;
		}
		client.execute(() -> {
			if (client.player != null) {
				Chat.tell(client.player, 
						Component.literal("[SkyblockRU] ").append(text).withStyle(color));
			} else {
				SkyblockRuClient.LOG.info("[SkyblockRU] {}", text);
			}
		});
	}
}
