package ru.skyblockru.core;

import com.google.gson.JsonArray;
import com.google.gson.JsonObject;
import net.minecraft.ChatFormatting;
import net.minecraft.client.Minecraft;
import net.minecraft.network.chat.ClickEvent;
import net.minecraft.network.chat.Component;
import net.minecraft.network.chat.Style;
import ru.skyblockru.SkyblockRuClient;
import ru.skyblockru.config.RuConfig;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.zip.GZIPOutputStream;

/**
 * Отправка непереведённых строк — чтобы перевод пополнялся у всех сразу.
 *
 * <p><b>Зачем.</b> Мод видит на экране то, чего нет в словаре, и знает об этом
 * точно. Пока эти строки лежали только у одного игрока, перевод рос со
 * скоростью его прогулок по меню. Собранное у сотни игроков покрывает игру
 * быстрее и ровнее — и каждому из них вернётся готовым переводом.
 *
 * <p><b>Что отправляется.</b> Только СТРОКИ ИГРОВОГО ИНТЕРФЕЙСА, которые мод
 * не смог перевести. Мусор (ники, номера серверов, даты панели) отсекается
 * ещё при сборе — {@link UnknownStrings#isNoise}. Сверх того здесь снимаются
 * реплики игроков.
 *
 * <p><b>Чего НЕ отправляется никогда:</b> ник, UUID, имя профиля, координаты,
 * адрес сервера, время игры — ничего, что указывает на человека. В пакете
 * лежат версия мода, версия игры и сами строки, больше ничего.
 *
 * <p>⚠️ Отправка ВКЛЮЧЕНА по умолчанию (решение игрока 03.08) и выключается
 * командой {@code /skyblockru telemetry off}. При первом запуске мод один раз
 * говорит в чат, что именно он отправляет, — молча собирать данные нельзя,
 * даже безобидные.
 *
 * <p>⚠️ Каждая строка уходит ОДИН раз. Отправленное помнится в
 * {@code dump/telemetry-sent.txt}, иначе при каждом выходе с сервера
 * улетал бы весь накопленный дамп заново — 25 тысяч строк вместо десятка новых.
 */
public final class Telemetry {

	private static final org.slf4j.Logger LOG =
			org.slf4j.LoggerFactory.getLogger("SkyblockRU");

	private static final Duration TIMEOUT = Duration.ofSeconds(20);

	private static final HttpClient HTTP = HttpClient.newBuilder()
			.connectTimeout(TIMEOUT)
			.followRedirects(HttpClient.Redirect.NORMAL)
			.build();

	private static volatile boolean running;
	private static volatile long lastSend;
	private static Set<String> sent;

	/**
	 * Приветствие уже ждёт своей очереди — второй раз не планируем.
	 *
	 * <p>Отметка в конфиге ставится ТОЛЬКО когда сообщение действительно уходит
	 * в чат (см. {@link #tellOnce}), поэтому одного её наличия мало: событие
	 * JOIN приходит и при переходе между серверами сети Hypixel, и без замка
	 * рядом ждали бы несколько потоков, каждый со своим сообщением.
	 */
	private static final AtomicBoolean noticeScheduled = new AtomicBoolean();

	/**
	 * Шаг ожидания SkyBlock и число попыток переехали в {@link Hypixel}.
	 *
	 * <p>Первая пауза нужна сама по себе: сразу после входа чат забит
	 * приветствиями сервера, и одинокая строка утонет в них незамеченной —
	 * формально сказали, фактически нет. Дальше тем же шагом ждём, пока
	 * человек доберётся до острова: пять минут покрывают лобби, выбор режима
	 * и прогрузку, а если он в этот вечер вообще не пойдёт в SkyBlock —
	 * приветствие достанется следующему заходу.
	 *
	 * <p>⚠️ Держать их здесь значило иметь ВТОРУЮ копию ожидания: точно такое
	 * же нужно сообщению о новой версии мода. Копии в этом проекте расходятся
	 * молча — см. CLAUDE.md.
	 */

	private Telemetry() {
	}

	/** Где помним отправленное. Рядом с дампом — это тоже накопленное знание. */
	private static Path sentFile() {
		return SkyblockRuClient.configDir().resolve("dump").resolve("telemetry-sent.txt");
	}

	private static synchronized Set<String> sentSet() {
		if (sent != null) {
			return sent;
		}
		sent = new HashSet<>();
		Path path = sentFile();
		if (Files.exists(path)) {
			try {
				sent.addAll(Files.readAllLines(path, StandardCharsets.UTF_8));
			} catch (IOException exception) {
				// не прочиталось — не беда, отправим по второму разу
				Diagnostics.error("telemetry: reading sent list", exception);
			}
		}
		return sent;
	}

	/** Что нового накопилось с прошлой отправки. */
	private static Map<String, List<String>> fresh() {
		Set<String> already = sentSet();
		Map<String, List<String>> out = new java.util.TreeMap<>();
		UnknownStrings.forTelemetry().forEach((source, lines) -> {
			List<String> keep = new ArrayList<>();
			for (String line : lines) {
				if (TelemetryFilter.worthSending(source, line)
						&& !already.contains(key(source, line))) {
					keep.add(line);
				}
			}
			if (!keep.isEmpty()) {
				out.put(source, keep);
			}
		});
		return out;
	}

	private static String key(String source, String line) {
		return Integer.toHexString((source + "\0" + line).hashCode());
	}

	/** Отправить накопленное. Зовётся при выходе с сервера и при закрытии игры. */
	public static void send() {
		RuConfig config = RuConfig.get();
		if (!config.telemetry || config.effectiveTelemetryUrl().isBlank()) {
			return;
		}
		// ⚠️ ТОЛЬКО ИЗ SKYBLOCK (требование игрока 03.08). Мод живёт на всём
		// Hypixel, и заглянув в лобби или бедварс, игрок отправил бы строки
		// чужого режима — их мы не переводим, и в очереди они только мусор.
		// Проверяем ДО `forgetMode`: порядок вызовов в SkyblockRuClient
		// это гарантирует, но если он поменяется — режим будет уже забыт,
		// и отправка молча прекратится.
		if (!Hypixel.isSkyBlock()) {
			return;
		}
		long now = System.currentTimeMillis();
		if (running || now - lastSend < config.telemetryMinutes * 60_000L) {
			return;
		}
		lastSend = now;
		running = true;
		Thread.ofVirtual().name("skyblockru-telemetry").start(() -> {
			try {
				run(config.effectiveTelemetryUrl());
			} catch (Exception exception) {
				// ⚠️ Молча: игроку до этого дела нет, а мешать игре из-за
				// недоступного сервера сбора — тем более незачем.
				Diagnostics.error("telemetry", exception);
			} finally {
				running = false;
			}
		});
	}

	private static void run(String url) throws IOException, InterruptedException {
		Map<String, List<String>> lines = fresh();
		if (lines.isEmpty()) {
			return;
		}

		JsonObject payload = new JsonObject();
		payload.addProperty("mod", SkyblockRuClient.modVersion());
		payload.addProperty("game", gameVersion());
		JsonObject sources = new JsonObject();
		int count = 0;
		for (var entry : lines.entrySet()) {
			JsonArray array = new JsonArray();
			for (String line : entry.getValue()) {
				array.add(line);
				count++;
			}
			sources.add(entry.getKey(), array);
		}
		payload.add("lines", sources);

		byte[] body = gzip(payload.toString().getBytes(StandardCharsets.UTF_8));
		HttpRequest request = HttpRequest.newBuilder(URI.create(url))
				.timeout(TIMEOUT)
				.header("Content-Type", "application/json")
				.header("Content-Encoding", "gzip")
				.header("User-Agent", "SkyblockRU/" + SkyblockRuClient.modVersion())
				.POST(HttpRequest.BodyPublishers.ofByteArray(body))
				.build();
		HttpResponse<String> answer = HTTP.send(request, HttpResponse.BodyHandlers.ofString());
		if (answer.statusCode() != 200) {
			throw new IOException("server answered " + answer.statusCode());
		}

		// ⚠️ Помечаем отправленным ТОЛЬКО после успеха. Иначе потерянный
		// по дороге пакет исчез бы навсегда: строки уже «отправлены».
		remember(lines);
		LOG.info("[skyblockru] telemetry: sent {} lines ({} bytes)", count, body.length);
	}

	private static synchronized void remember(Map<String, List<String>> lines) {
		Set<String> already = sentSet();
		List<String> added = new ArrayList<>();
		lines.forEach((source, rows) -> rows.forEach(line -> {
			String key = key(source, line);
			if (already.add(key)) {
				added.add(key);
			}
		}));
		if (added.isEmpty()) {
			return;
		}
		try {
			Path path = sentFile();
			Files.createDirectories(path.getParent());
			Files.write(path, added, StandardCharsets.UTF_8,
					java.nio.file.StandardOpenOption.CREATE,
					java.nio.file.StandardOpenOption.APPEND);
		} catch (IOException exception) {
			Diagnostics.error("telemetry: writing sent list", exception);
		}
	}

	private static String gameVersion() {
		try {
			return net.fabricmc.loader.api.FabricLoader.getInstance()
					.getModContainer("minecraft")
					.map(mod -> mod.getMetadata().getVersion().getFriendlyString())
					.orElse("");
		} catch (Exception ignored) {
			return "";
		}
	}

	private static byte[] gzip(byte[] data) throws IOException {
		ByteArrayOutputStream out = new ByteArrayOutputStream();
		try (GZIPOutputStream zip = new GZIPOutputStream(out)) {
			zip.write(data);
		}
		return out.toByteArray();
	}

	/**
	 * Один раз поздороваться: сказать про БЕТУ и про то, что мод отправляет.
	 *
	 * <p>⚠️ Про бету говорим ВСЕГДА и отдельным флагом, а не вместе
	 * с телеметрией: телеметрию игрок вправе выключить, а знать о неполноте
	 * перевода он должен в любом случае. Иначе человек, поставивший
	 * русификатор, встретит английское описание и решит, что мод сломан.
	 *
	 * <p>⚠️ Показываем ОДИН раз за всё время, а не при каждом запуске: отметка
	 * лежит в конфиге. Сообщение, которое видишь каждый вечер, перестают читать
	 * вместе со всеми остальными — этим проект уже обжигался.
	 */
	public static void tellOnce() {
		RuConfig config = RuConfig.get();
		boolean needBeta = !config.betaNotified;
		boolean needTelemetry = config.telemetry && !config.telemetryNotified;
		if (!needBeta && !needTelemetry) {
			return;
		}
		// ⚠️ Один поток на запуск игры. Событие JOIN приходит и при переходе
		// между серверами сети Hypixel, а отметка теперь ставится ПОЗЖЕ —
		// без этого замка несколько ожидающих потоков показали бы сообщение
		// по разу каждый.
		if (!noticeScheduled.compareAndSet(false, true)) {
			return;
		}
		String policy = config.policyUrl;

		// ⚠️ С задержкой. Сразу после входа чат забит приветствиями сервера,
		// и одинокая строка про телеметрию утонет в них незамеченной —
		// то есть формально мы сказали, а фактически нет.
		Thread.ofVirtual().name("skyblockru-telemetry-notice").start(() -> {
			// ⚠️ ЖДЁМ SkyBlock, а не спрашиваем однажды.
			//
			// Событие JOIN приходит при подключении к СЕТИ Hypixel, а человек
			// попадает оттуда в лобби и только потом на остров. Одной проверки
			// через восемь секунд не хватало: к этому моменту он обычно ещё
			// выбирает режим, а второго JOIN может и не быть.
			//
			// ⚠️ Ожидание живёт в ОДНОМ месте (Hypixel.awaitSkyBlock) и общее
			// со всеми, кому надо «сказать игроку в SkyBlock»: сообщение
			// о новой версии мода ждёт им же. Своя копия разошлась бы шагом
			// или числом попыток — и сообщения повели бы себя по-разному
			// без всякой причины.
			Minecraft client = Hypixel.awaitSkyBlock();
			if (client == null) {
				noticeScheduled.set(false);   // не дождались — попробуем в следующий заход
				return;
			}
			// ⚠️ ОТМЕТКУ СТАВИМ ЗДЕСЬ, а не при подключении к серверу.
			//
			// Раньше она записывалась в самом начале tellOnce, до задержки —
			// «лучше не показать, чем показать дважды». Но отсчёт идёт от входа
			// НА СЕРВЕР, а не в SkyBlock, и за восемь секунд человек обычно ещё
			// в лобби: выбор режима и прогрузка острова дольше. Флаг при этом
			// уже лежал на диске, а показывается сообщение ОДИН раз за всё
			// время — то есть про неполноту перевода игрок не узнавал никогда.
			// Поймано на живом конфиге: betaNotified=true при том, что SkyBlock
			// стоял на техработах и игрок туда не заходил вовсе.
			config.betaNotified = true;
			if (needTelemetry) {
				config.telemetryNotified = true;
			}
			config.save();
			client.execute(() -> {
				// ⚠️ ЦВЕТ НЕ ТЕМНЕЕ СЕРОГО. DARK_GRAY на светлом фоне чата
				// Hypixel почти не читается — проверено скриншотом игрока:
				// две строки из четырёх сливались с фоном. Подсказка,
				// которую не прочли, всё равно что не показана.
				// ⚠️ Про бету — ПЕРВЫМ и всегда: это то, из-за чего мод сочтут
				// сломанным, если промолчать.
				if (needBeta) {
					say(ChatFormatting.GOLD, Component.translatable("skyblockru.beta.notice"));
					say(ChatFormatting.GRAY, Component.translatable("skyblockru.beta.why"));
				}
				if (!needTelemetry) {
					return;
				}
				say(ChatFormatting.YELLOW, Component.translatable("skyblockru.telemetry.notice"));
				say(ChatFormatting.GRAY, Component.translatable("skyblockru.telemetry.what"));
				say(ChatFormatting.GRAY, Component.translatable("skyblockru.telemetry.off"));
				if (policy != null && !policy.isBlank()) {
					// ⚠️ Ссылка задаётся ПО-РАЗНОМУ: в новых версиях это
					// `ClickEvent.OpenUrl(URI)`, в 1.21.4 и ниже — конструктор
					// с действием и СТРОКОЙ. Замена имени тут не поможет:
					// расходится и тип аргумента, и форма вызова.
					//? if >=1.21.5 {
					ClickEvent open = new ClickEvent.OpenUrl(URI.create(policy));
					//?} else
					/*ClickEvent open = new ClickEvent(ClickEvent.Action.OPEN_URL, policy);*/
					say(ChatFormatting.AQUA,
							Component.translatable("skyblockru.telemetry.policy")
									.copy().withStyle(Style.EMPTY
											.withUnderlined(true)
											.withClickEvent(open)));
				}
			});
		});
	}

	private static void say(ChatFormatting color, Component text) {
		Minecraft client = Minecraft.getInstance();
		if (client == null || client.player == null) {
			return;
		}
		Chat.tell(client.player, Component.literal("[SkyblockRU] ").withStyle(ChatFormatting.AQUA)
				.append(text.copy().withStyle(color)));
	}
}
