package ru.skyblockru;

import net.fabricmc.api.ClientModInitializer;
import net.fabricmc.fabric.api.client.event.lifecycle.v1.ClientLifecycleEvents;
import net.fabricmc.fabric.api.client.event.lifecycle.v1.ClientTickEvents;
import net.fabricmc.fabric.api.client.networking.v1.ClientPlayConnectionEvents;
import net.fabricmc.loader.api.FabricLoader;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import ru.skyblockru.command.RuCommand;
import ru.skyblockru.config.RuConfig;
import ru.skyblockru.core.Keys;
import ru.skyblockru.core.Translator;
import ru.skyblockru.core.UnknownStrings;
import ru.skyblockru.core.UpdateService;
import ru.skyblockru.hook.TextHooks;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

public class SkyblockRuClient implements ClientModInitializer {

	public static final String MOD_ID = "skyblockru";
	public static final Logger LOG = LoggerFactory.getLogger("SkyblockRU");

	private static Path configDir;

	/**
	 * Как часто сверять язык клиента, в тиках. Раз в секунду: игрок закрывает
	 * меню настроек и сразу смотрит на экран, а перезагрузка словарей заметна
	 * (читаются 28 файлов), и делать её чаще незачем.
	 */
	private static final int LANGUAGE_CHECK_TICKS = 20;

	private static int languageTick;

	public static Path configDir() {
		return configDir;
	}

	public static Path packsDir() {
		return configDir.resolve("packs");
	}

	/**
	 * Когда собран jar, который сейчас запущен.
	 * Нужно, чтобы отличить свежую сборку от старой: игра держит jar с момента
	 * запуска, и правка, сделанная позже, в неё не попадает.
	 */
	public static String buildTime() {
		return FabricLoader.getInstance().getModContainer(MOD_ID)
				.filter(container -> container.getMetadata().containsCustomValue("skyblockru:built"))
				.map(container -> container.getMetadata().getCustomValue("skyblockru:built").getAsString())
				.orElse("unknown");
	}

	/** Версия из fabric.mod.json — её сравнивает проверка обновлений. */
	public static String modVersion() {
		return FabricLoader.getInstance().getModContainer(MOD_ID)
				.map(container -> container.getMetadata().getVersion().getFriendlyString())
				.orElse("?");
	}

	@Override
	public void onInitializeClient() {
		configDir = FabricLoader.getInstance().getConfigDir().resolve(MOD_ID);
		try {
			Files.createDirectories(packsDir());
		} catch (IOException exception) {
			LOG.warn("[SkyblockRU] could not create the config folder: {}", exception.toString());
		}

		RuConfig.load(configDir);
		UnknownStrings.init(configDir);
		Translator.reload(packsDir());
		TextHooks.register();
		RuCommand.register();
		// ⚠️ Клавиши заявляем ЗДЕСЬ: позже игра уже построила список привязок,
		// и в меню управления наши бы не появились. Раньше Shift был зашит
		// константой — переназначить его было нельзя никак.
		Keys.register();

		// ⚠️ Каналы Hypixel Mod API заявляем ЗДЕСЬ, до подключения к серверу:
		// PayloadTypeRegistry принимает регистрацию только на этом этапе.
		// Сам режим придёт позже, пакетом; панель остаётся запасным путём.
		//
		// ⚠️ ЛОВИМ ЗДЕСЬ, А НЕ ТОЛЬКО ВНУТРИ init(). Библиотеку мы больше
		// не вкладываем (она ломала чужие сборки — см. грабли), поэтому её
		// может не быть вовсе либо оказаться версия 1.0.1, где нет
		// `HypixelModAPIImplementation`. Класс `HypixelApi` этот интерфейс
		// РЕАЛИЗУЕТ, а значит JVM разрешает его в момент ЗАГРУЗКИ класса —
		// то есть падение случится на этой строке, снаружи чужого try.
		try {
			ru.skyblockru.core.HypixelApi.init();
		} catch (Throwable problem) {
			// Не смертельно: режим определяется заголовком боковой панели,
			// как и до появления Mod API. Но сказать об этом надо громко —
			// молчаливый откат к худшему способу никто бы не заметил.
			LOG.warn("[skyblockru] Hypixel Mod API not available ({}), "
					+ "using sidebar title instead", problem.toString());
		}

		// Обновление переводов при заходе на сервер — игроку ничего нажимать не надо.
		ClientPlayConnectionEvents.JOIN.register((handler, sender, client) -> {
			UpdateService.onJoinServer();
			// ⚠️ Про отправку непереведённого говорим ОДИН раз за всё время —
			// молча собирать нельзя, но и повторять каждый вход незачем.
			ru.skyblockru.core.Telemetry.tellOnce();
		});

		// Сброс собранного на диск при выходе с сервера и при закрытии игры.
		//
		// Автосохранение раз в 20 секунд срабатывает ТОЛЬКО в момент, когда
		// пришла новая строка. Побродил по новым меню, поток строк иссяк, вышел —
		// и хвост сессии оставался лишь в памяти. Просить игрока каждый раз
		// вводить /skyblockru dump — значит рано или поздно потерять вечер работы.
		ClientPlayConnectionEvents.DISCONNECT.register((handler, client) -> {
			UnknownStrings.flush();
			// Заодно отправляем накопленное: момент удобный — игра уже не рисует
			// кадры, а строки за сессию собраны целиком.
			ru.skyblockru.core.Telemetry.send();
			// Забываем режим: иначе, выйдя из SkyBlock в лобби, мод продолжал бы
			// считать, что он всё ещё в SkyBlock, и переводил бы чужие режимы.
			ru.skyblockru.core.Hypixel.forgetMode();
		});
		ClientLifecycleEvents.CLIENT_STOPPING.register(client -> {
			UnknownStrings.flush();
			ru.skyblockru.core.Telemetry.send();
		});

		// Словари перечитываем ещё раз, когда клиент ПОЛНОСТЬЮ поднялся.
		//
		// ⚠️ Здесь, в onInitializeClient, языка ещё нет: LanguageManager не создан,
		// и выбор словарей делался вслепую. Один раз это уже стоило всего перевода —
		// язык определился как en_us, папки под него нет, загрузился один общий
		// словарь, и в игре не переводилось НИЧЕГО. Второй проход стоит копейки
		// и снимает всю эту зависимость от момента запуска.
		ClientLifecycleEvents.CLIENT_STARTED.register(client -> Translator.reload(packsDir()));

		// ⚠️ СМЕНУ ЯЗЫКА ЛОВИМ САМИ, а не просим игрока вводить /skyblockru reload.
		//
		// Словари читаются вручную, а не через менеджер ресурсов, поэтому смена
		// языка в настройках их не перечитывает. Игрок завёл инстанс с английским
		// клиентом, переключился на русский уже в игре — и получил полностью
		// английский экран при живом моде: команды отвечали по-русски, потому
		// что их текст разрешает сам клиент, а не наши словари. Причина была
		// в логе прямым текстом, но читать лог — не работа игрока.
		//
		// Проверка — сравнение двух строк, поэтому её не жалко делать часто;
		// перезагрузка идёт ТОЛЬКО когда язык действительно другой.
		ClientTickEvents.END_CLIENT_TICK.register(client -> {
			if (++languageTick < LANGUAGE_CHECK_TICKS) {
				return;
			}
			languageTick = 0;
			if (Translator.languageChanged()) {
				LOG.info("[SkyblockRU] game language changed - reloading dictionaries");
				Translator.reload(packsDir());
			}
		});

		LOG.info("[SkyblockRU] ready. Put your own dictionaries in {}", packsDir());
	}
}
