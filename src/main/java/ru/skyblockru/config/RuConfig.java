package ru.skyblockru.config;

import com.google.gson.Gson;
import com.google.gson.GsonBuilder;
import ru.skyblockru.SkyblockRuClient;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

/**
 * Настройки мода: config/skyblockru/config.json.
 * Каждый источник текста выключается отдельно — если что-то переведено криво,
 * можно погасить именно его, не отключая мод целиком.
 */
public final class RuConfig {

	private static final Gson GSON = new GsonBuilder().setPrettyPrinting().create();

	private static RuConfig instance = new RuConfig();
	private static Path file;

	/** Общий выключатель. */
	public boolean enabled = true;

	/** Работать только на Hypixel — в одиночной игре и на других серверах мод молчит. */
	public boolean onlyOnHypixel = true;

	/**
	 * Работать только в SkyBlock, а не во всём Hypixel.
	 *
	 * <p>Hypixel — это ещё лобби, бедварс, дуэли и десяток режимов. Переводить
	 * их незачем, а собранные оттуда строки засоряют дамп и сбивают частоты,
	 * по которым мы решаем, что переводить в первую очередь.
	 * Режим определяется по заголовку боковой панели: там «SKYBLOCK».
	 */
	public boolean onlySkyBlock = true;

	/**
	 * Показывать команды для РАЗРАБОТКИ: reload, dump, diag, test, stats.
	 *
	 * <p>⚠️ Выключено по умолчанию. Игроку нужны ровно четыре ветки —
	 * посмотреть состояние, включить/выключить перевод, переключить словари
	 * и проверить обновление. Остальное писалось для отладки: `diag` печатает
	 * счётчики промахов, `dump` пишет собранное на диск, `test` гоняет
	 * самопроверку. В подсказке команд они выглядят так, будто мод сложный.
	 *
	 * <p>Команды не удалены, а спрятаны: мне они нужны каждый день.
	 */
	public boolean devCommands = false;

	/**
	 * Язык словарей. Пусто — выбрать самому.
	 *
	 * <p>⚠️ Мод НЕ привязан к языку игры. Он переводит на русский, за этим его
	 * и ставят, — поэтому при английском клиенте он всё равно берёт русские
	 * словари, а не молчит. Раньше молчал: игрок завёл инстанс с английским
	 * клиентом и получил полностью английский экран при живом моде.
	 *
	 * <p>Поле нужно тем, у кого языков словарей несколько: тогда выбор
	 * перестаёт зависеть от языка клиента и делается явно. Значение — код
	 * вроде {@code "ru_ru"}; неизвестный код игнорируется с жалобой в лог,
	 * потому что молча переводить не на то хуже, чем не переводить.
	 */
	public String language = "";

	/**
	 * Необязательные словари: id -> включён ли.
	 *
	 * <p>Словарь может объявить себя выключенным по умолчанию (поле
	 * {@code "default": false}), а игрок — включить его тут или командой
	 * {@code /skyblockru pack <id> on}. Так вкусовые решения перестают быть
	 * зашитыми в мод: раньше «переводить ли ванильные названия предметов»
	 * менялось только пересборкой.
	 *
	 * <p>Чего тут нет — берётся из самого словаря. То есть файл конфига
	 * не надо заполнять заранее, в нём лежат только осознанные отличия.
	 */
	public java.util.Map<String, Boolean> packs = new java.util.LinkedHashMap<>();

	/**
	 * Склеивать абзац, когда свой цвет только у ПЕРВОЙ строки (заголовок),
	 * а описание под ним одноцветное.
	 *
	 * <p>Без этого подсказки вида «Tiered Bonus: … (0/4)» + описание остаются
	 * английскими: защита цвета принимает заголовок за подпись из пары
	 * «подпись / значение». Ценой того, что заголовок красится цветом описания.
	 *
	 * <p>Выключается, если где-то поедут цвета: это вкусовое решение, а не
	 * механика, и игрок должен уметь его отменить сам.
	 */
	public boolean mergeHeaderRuns = true;

	/** Записывать непереведённые строки в config/skyblockru/dump/. */
	public boolean dumpUntranslated = true;

	/**
	 * Сообщать в чат, когда попались новые строки для перевода.
	 *
	 * <p>⚠️ ВЫКЛЮЧЕНО по умолчанию (решение игрока 02.08, перед раздачей мода
	 * чужим людям). Строка «+75 новых строк для перевода» — это сообщение
	 * РАЗРАБОТЧИКУ: она говорит, что сбор работает и куда ещё не заходили.
	 * Игроку, который поставил мод ради перевода, она не значит ничего и
	 * читается как ошибка или спам.
	 *
	 * <p>Сам сбор при этом продолжается — молча, в дамп. Включить обратно:
	 * {@code notifyNewStrings: true} в config/skyblockru/config.json.
	 */
	public boolean notifyNewStrings = false;

	/**
	 * Сообщать в чат о ПРОМАХАХ перевода, которые мод замечает сам:
	 * смесь языков, погашенный защитой перевод, потерянный цвет.
	 *
	 * <p>⚠️ Заводилось это ДЛЯ РАЗРАБОТКИ: мод про свои неудачи знает, и пусть
	 * говорит сразу, а не копит в счётчиках, которые открывают раз в неделю.
	 * Для игрока же «нашли баг в покраске» — сообщение ни о чём: починить он
	 * его не может, а выглядит оно как поломка мода.
	 *
	 * <p>⚠️ ВЫКЛЮЧЕНО по умолчанию (решение игрока 02.08, перед раздачей мода
	 * чужим людям). Промахи по-прежнему копятся в дамп и видны через
	 * {@code /skyblockru diag} и {@code tools/report.py} — потерять их нельзя,
	 * они и есть рабочий список. Включить обратно: {@code notifyProblems: true}.
	 */
	public boolean notifyProblems = false;

	/**
	 * Читать описания ВСЕХ предметов открытого меню, не дожидаясь наведения.
	 *
	 * <p>⚠️ Раньше мод узнавал текст только под курсором, и собранное зависело
	 * от того, куда игрок навёл мышку. В меню аукциона 54 предмета — водить
	 * по ним ради сбора бессмысленно, отсюда и вечное «этой строки нет в дампе»
	 * на очевидные вещи. Обход слотов забирает всё разом.
	 */
	public boolean sweepContainers = true;

	/**
	 * Показывать справку по терминам SkyBlock: что это и зачем (по Shift).
	 *
	 * <p>Часть названий мы намеренно оставляем английскими — по ним ищут вещи
	 * на аукционе и читают гайды. Но игроку от слова «Overbloom» толку мало,
	 * если неизвестно, что это характеристика Земледелия. Справка даёт смысл,
	 * не отнимая поиска.
	 */
	public boolean wikiHints = true;

	/**
	 * Частичный перевод: подменять знакомые термины внутри ещё не переведённых строк.
	 * По умолчанию выключено — получается смесь языков, и падежи не сходятся.
	 * Включай, если хочешь понимать хотя бы термины, пока словарь неполный.
	 */
	public boolean glossaryPass = false;

	/**
	 * Адрес обновлений, зашитый в мод. ЕДИНСТВЕННОЕ место, которое надо заполнить
	 * перед сборкой релиза — тогда обновления работают у всех игроков из коробки,
	 * и тем, кто уже поставил мод, ничего настраивать не нужно.
	 *
	 * <p>Object Storage Yandex Cloud (Казахстан), бакет с публичным чтением.
	 * Выкладывает `tools/publish.py`; манифест перечисляет словари с их sha256,
	 * и мод качает только изменившиеся.
	 *
	 * <p>⚠️ Адрес ОДИН, зеркал нет (решение игрока 03.08). Значит недоступность
	 * этого адреса означает, что обновление не придёт вовсе. Молчаливым это
	 * не будет: после трёх неудач подряд мод говорит об этом в чат
	 * (`UpdateService.noteFailure`).
	 *
	 * <p>⚠️ Домен в зоне .kz — проверено, что из России открывается. Если
	 * когда-нибудь начнутся жалобы «перевод не обновляется», проверять надо
	 * это в первую очередь.
	 */
	public static final String DEFAULT_UPDATE_URL =
			"https://storage.yandexcloud.kz/skyblockru-dict/manifest.json";

	/**
	 * Откуда брать обновления переводов. Пусто — берётся зашитый адрес.
	 * Скачиваются ТОЛЬКО словари (json), код никогда.
	 * Чтобы выключить обновления совсем, есть autoUpdate.
	 */
	public String updateUrl = "";

	/** Адрес, который реально используется: свой, если задан, иначе зашитый в мод. */
	public String effectiveUpdateUrl() {
		return updateUrl == null || updateUrl.isBlank() ? DEFAULT_UPDATE_URL : updateUrl;
	}

	/**
	 * Отправлять непереведённые строки, чтобы перевод пополнялся у всех сразу.
	 *
	 * <p>ВКЛЮЧЕНО по умолчанию (решение игрока 03.08), выключается
	 * {@code /skyblockru telemetry off}. Уходят только строки игрового
	 * интерфейса, которые мод не смог перевести; ник, UUID и имя профиля
	 * не отправляются никогда — см. {@link ru.skyblockru.core.Telemetry}.
	 */
	public boolean telemetry = true;

	/** Показывали ли игроку, что мод отправляет. Один раз за всё время. */
	public boolean telemetryNotified = false;

	/** Куда слать. Пусто — берётся зашитый адрес. */
	public String telemetryUrl = "";

	/**
	 * Зашитый адрес приёмника.
	 *
	 * <p>Сервер AEZA, домен через DuckDNS, https держит Caddy (сертификат
	 * Let's Encrypt, выпускается сам). Приёмник — {@code server/receiver.py},
	 * слушает только localhost, наружу смотрит Caddy.
	 *
	 * <p>⚠️ Домен ВРЕМЕННЫЙ: `duckdns.org` бесплатный и чужой. Когда будет
	 * куплен свой, поменять надо здесь — и собрать мод заново. Игрокам со
	 * старым jar отправка просто перестанет доходить, поломки не будет.
	 */
	public static final String DEFAULT_TELEMETRY_URL =
			"https://skyblockru.duckdns.org/submit";

	public String effectiveTelemetryUrl() {
		return telemetryUrl == null || telemetryUrl.isBlank()
				? DEFAULT_TELEMETRY_URL : telemetryUrl;
	}

	/** Не чаще раза в столько минут — чтобы не дёргать сеть на каждом выходе. */
	public int telemetryMinutes = 30;

	/**
	 * Ссылка на политику: что собирается и как это выключить.
	 *
	 * <p>Показывается один раз при первом входе, кликабельной строкой.
	 * Страница лежит на том же сервере, что и приёмник.
	 */
	public String policyUrl = "https://skyblockru.duckdns.org/privacy";

	/** Проверять обновления переводов при заходе на сервер. */
	public boolean autoUpdate = true;

	/** Не чаще одного раза в столько минут, чтобы не дёргать сеть на каждом заходе. */
	public int updateCheckMinutes = 60;

	/** Что именно переводим. */
	public Targets targets = new Targets();

	public static final class Targets {
		public boolean chat = true;
		public boolean itemName = true;
		public boolean itemLore = true;
		public boolean scoreboard = true;
		public boolean tabList = true;
		public boolean actionBar = true;
		public boolean title = true;
		public boolean screenTitle = true;
		public boolean bossBar = true;
		public boolean nameTag = true;
	}

	public static RuConfig get() {
		return instance;
	}

	public static void load(Path configDir) {
		file = configDir.resolve("config.json");
		if (Files.exists(file)) {
			try {
				RuConfig loaded = GSON.fromJson(Files.readString(file, StandardCharsets.UTF_8), RuConfig.class);
				if (loaded != null) {
					if (loaded.targets == null) {
						loaded.targets = new Targets();
					}
					instance = loaded;
				}
			} catch (IOException | RuntimeException exception) {
				SkyblockRuClient.LOG.warn("[SkyblockRU] config.json unreadable, using defaults: {}",
						exception.toString());
			}
		}
		save();
	}

	public static void save() {
		if (file == null) {
			return;
		}
		try {
			Files.createDirectories(file.getParent());
			Files.writeString(file, GSON.toJson(instance), StandardCharsets.UTF_8);
		} catch (IOException exception) {
			SkyblockRuClient.LOG.warn("[SkyblockRU] could not save config.json: {}", exception.toString());
		}
	}
}
