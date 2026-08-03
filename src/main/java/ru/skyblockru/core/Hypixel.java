package ru.skyblockru.core;

import net.minecraft.client.Minecraft;
import net.minecraft.client.multiplayer.ServerData;
import net.minecraft.network.chat.Component;
import ru.skyblockru.config.RuConfig;

import java.util.Locale;

/**
 * Определяет, где мы сейчас: на Hypixel вообще и в SkyBlock в частности.
 *
 * <p>Проверка по адресу подключения — явный признак, а не догадка по содержимому
 * чата. Так мод гарантированно молчит в одиночной игре и на чужих серверах:
 * подменять текст там не надо, да и дамп замусорится.
 *
 * <p><b>Одного адреса мало.</b> Hypixel — это не только SkyBlock: там лобби,
 * бедварс, дуэли и ещё десяток режимов. Мод переводил и собирал строки во всех,
 * а нужен нам ровно один. Лишние строки не просто бесполезны — они попадают
 * в дамп и сбивают частоты, по которым мы решаем, что переводить за деньги
 * в первую очередь.
 */
public final class Hypixel {

	private static final String DOMAIN = "hypixel.net";

	/**
	 * Заголовок боковой панели, каким его прислал сервер (до нашего перевода).
	 *
	 * <p>Признак взят из живого дампа, а не выдуман: там лежат ровно
	 * {@code SKYBLOCK} и {@code SKYBLOCK GUEST}, а в лобби — {@code HYPIXEL}.
	 *
	 * <p>Заполняется из {@code ObjectiveMixin}, и это не случайность.
	 * Спросить заголовок самим нельзя: {@code getDisplayName} перехвачен нашим же
	 * миксином, который зовёт переводчик, а тот спрашивает режим — получилась бы
	 * бесконечная рекурсия. Миксин отдаёт нам сырое значение сам, ещё до перевода.
	 */
	private static volatile String sidebarTitle = "";

	/**
	 * Что сказал ОФИЦИАЛЬНЫЙ Hypixel Mod API: {@code null} — не сказал ничего.
	 *
	 * <p>Три состояния, а не два, и это важно. Заголовок панели — догадка по
	 * тексту, который сервер волен переписать; пакет {@code hyevent:location} —
	 * данные. Но пакет приходит не всегда (нужна подписка, сервер может её
	 * не подтвердить, версия пакета может не совпасть), и «API промолчал»
	 * обязано отличаться от «API сказал: не SkyBlock». Иначе молчание выключало
	 * бы перевод — ровно та беда, на которой проект уже обжигался.
	 */
	private static volatile Boolean apiSkyBlock;

	/** Имя типа сервера от API — только чтобы показать его в {@code /skyblockru}. */
	private static volatile String apiServerType = "";

	private Hypixel() {
	}

	/**
	 * Пришёл официальный ответ сервера о том, где мы.
	 *
	 * <p>Строку сюда передаёт {@link HypixelApi} уже разобранной: сам
	 * {@code Hypixel} про библиотеку Hypixel ничего не знает и знать не должен —
	 * иначе мод перестал бы собираться, стоит библиотеке пропасть.
	 */
	public static void noteServerType(String typeName, boolean skyBlock) {
		apiServerType = typeName == null ? "" : typeName;
		apiSkyBlock = skyBlock;
	}

	/** Вызывается миксином боковой панели. Значение — ДО перевода. */
	public static void noteSidebarTitle(Component title) {
		if (title == null) {
			return;
		}
		String plain = LegacyText.strip(title.getString()).trim();
		if (!plain.equals(sidebarTitle)) {
			sidebarTitle = plain;
		}
	}

	/** Сброс при выходе с сервера: иначе в лобби мы бы помнили старый режим. */
	public static void forgetMode() {
		sidebarTitle = "";
		apiSkyBlock = null;
		apiServerType = "";
	}

	/** Название режима и ЧЕМ он определён — для /skyblockru. */
	public static String currentMode() {
		Boolean fromApi = apiSkyBlock;
		if (fromApi != null) {
			return apiServerType.isEmpty() ? "?" : apiServerType + " (API)";
		}
		return sidebarTitle.isEmpty() ? "?" : sidebarTitle;
	}

	/**
	 * Мы в SkyBlock? Просто чтение поля — метод зовётся на каждую строку,
	 * поэтому ничего тяжелее сравнения тут быть не должно.
	 *
	 * <p>Официальный ответ сервера важнее догадки по тексту панели: заголовок
	 * Hypixel может переписать, а поле пакета — это данные.
	 */
	public static boolean isSkyBlock() {
		Boolean fromApi = apiSkyBlock;
		if (fromApi != null) {
			return fromApi;
		}
		return sidebarTitle.toLowerCase(Locale.ROOT).contains("skyblock");
	}

	public static boolean isActive() {
		RuConfig config = RuConfig.get();
		if (config.onlyOnHypixel && !isOnHypixel()) {
			return false;
		}
		if (!config.onlySkyBlock) {
			return true;
		}
		// ⚠️ Режим ещё НЕ ИЗВЕСТЕН (панель не отрисовалась, признак не пришёл) —
		// работаем как раньше, а не молчим. Сегодня перевод уже умирал целиком
		// из-за проверки, которая тихо вернула false: в игре ни ошибки, ни
		// предупреждения, просто английский текст. Незнание не должно
		// выключать мод — выключать его вправе только явное «мы в лобби».
		if (apiSkyBlock == null && sidebarTitle.isEmpty()) {
			return true;
		}
		return isSkyBlock();
	}

	public static boolean isOnHypixel() {
		Minecraft client = Minecraft.getInstance();
		if (client == null || client.isLocalServer()) {
			return false;
		}
		ServerData server = client.getCurrentServer();
		if (server == null || server.ip == null) {
			return false;
		}
		String ip = server.ip.toLowerCase(Locale.ROOT);
		return ip.equals(DOMAIN) || ip.endsWith("." + DOMAIN);
	}
}
