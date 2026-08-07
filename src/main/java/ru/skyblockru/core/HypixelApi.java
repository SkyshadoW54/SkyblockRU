package ru.skyblockru.core;

import io.netty.buffer.Unpooled;
import net.fabricmc.fabric.api.client.networking.v1.ClientPlayConnectionEvents;
import net.fabricmc.fabric.api.client.networking.v1.ClientPlayNetworking;
import net.fabricmc.fabric.api.client.networking.v1.ServerboundPlayChannelEvents;
import net.fabricmc.fabric.api.networking.v1.PayloadTypeRegistry;
import net.hypixel.data.type.GameType;
import net.hypixel.data.type.ServerType;
import net.hypixel.modapi.HypixelModAPI;
import net.hypixel.modapi.HypixelModAPIImplementation;
import net.hypixel.modapi.packet.HypixelPacket;
import net.hypixel.modapi.packet.impl.clientbound.event.ClientboundLocationPacket;
import net.hypixel.modapi.serializer.PacketSerializer;
import net.minecraft.network.FriendlyByteBuf;
import net.minecraft.network.RegistryFriendlyByteBuf;
import net.minecraft.network.codec.StreamCodec;
import net.minecraft.network.protocol.common.custom.CustomPacketPayload;
import net.minecraft.resources.Identifier;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * Официальный Hypixel Mod API: сервер сам сообщает, в каком мы режиме.
 *
 * <p><b>Зачем.</b> Раньше «мы в SkyBlock» мод определял по ЗАГОЛОВКУ боковой
 * панели: там лежит {@code SKYBLOCK}, а в лобби {@code HYPIXEL}. Признак взят
 * из живого дампа и работает, но держится на строке, которую Hypixel волен
 * переписать в любой день — а мы это уже наблюдали с репликами NPC к событиям.
 * Здесь же режим приходит ДАННЫМИ, полем {@link ClientboundLocationPacket}.
 *
 * <p><b>Панель остаётся запасным путём.</b> Пакет приходит не сразу и не всем:
 * нужен обмен подпиской, сервер может её не подтвердить, у старого клиента
 * версия пакета не совпадёт. Поэтому API только ПОДТВЕРЖДАЕТ режим, а молчание
 * API ничего не выключает — иначе повторилась бы беда, на которой проект уже
 * обжёгся: проверка тихо вернула false, и перевод пропал целиком, без единой
 * строчки в логе.
 *
 * <p><b>Почему берём чужую библиотеку, а не пишем протокол сами.</b> Так велит
 * FAQ самого Hypixel: свои реализации ломаются на рейт-лимитах и на согласовании
 * версий пакетов. Библиотека {@code net.hypixel:mod-api} — чистая Java, она
 * только собирает и разбирает пакеты; сеть не трогает вовсе, поэтому транспорт
 * (регистрация каналов, отправка, приём) написан здесь.
 */
public final class HypixelApi implements HypixelModAPIImplementation {

	private static final Logger LOG = LoggerFactory.getLogger("skyblockru");

	private static final HypixelApi INSTANCE = new HypixelApi();

	/**
	 * Каналы, по которым мы шлём серверу. Заполняются при инициализации из
	 * самой библиотеки, а не переписываются руками: список каналов — её
	 * хозяйство («hypixel:register», «hypixel:ping»…), и разойтись с ним
	 * значило бы молча перестать отправлять.
	 */
	private static final Map<String, CustomPacketPayload.Type<Raw>> SERVERBOUND = new HashMap<>();

	/** Пространство имён каналов Hypixel: по нему узнаём, что сервер их принимает. */
	private static final String HYPIXEL_NAMESPACE = "hypixel";

	/** ⚠️ События живут в ДРУГОМ пространстве: «hyevent:location», не «hypixel:». */
	private static final String EVENT_NAMESPACE = "hyevent";

	private static volatile boolean ready;

	/** Подписка оформляется РАЗ на подключение: сервер и так шлёт события сам. */
	private static volatile boolean subscribed;

	private HypixelApi() {
	}

	/**
	 * Пакет Hypixel как есть, сырыми байтами.
	 *
	 * <p>Разбирать содержимое здесь незачем: этим занимается библиотека. Нам
	 * нужно лишь довезти байты от Minecraft до неё и обратно.
	 */
	public record Raw(CustomPacketPayload.Type<Raw> type, byte[] data) implements CustomPacketPayload {
		@Override
		public CustomPacketPayload.Type<Raw> type() {
			return type;
		}
	}

	private static StreamCodec<RegistryFriendlyByteBuf, Raw> codecFor(CustomPacketPayload.Type<Raw> type) {
		return StreamCodec.of(
				(buffer, payload) -> buffer.writeBytes(payload.data()),
				buffer -> {
					byte[] data = new byte[buffer.readableBytes()];
					buffer.readBytes(data);
					return new Raw(type, data);
				});
	}

	/** Зовётся один раз при старте клиента. */
	public static void init() {
		try {
			HypixelModAPI api = HypixelModAPI.getInstance();

			// ⚠️⚠️ ЕСТЬ СОСЕД — ТРАНСПОРТ ЕГО, МЫ ТОЛЬКО СЛУШАЕМ.
			//
			// Мод-обёртка `hypixel-mod-api` делает ровно то же самое: ставит
			// свою реализацию и регистрирует каналы `hypixel:*`. Сделай это
			// оба — и проигравший упадёт: `PayloadTypeRegistry.register`
			// и `registerGlobalReceiver` на дубликат бросают исключение.
			// Наше упало бы в этот `try`, а ЕГО — в entrypoint, то есть
			// уронило бы игру на старте. Ровно так мы уже ломали чужие
			// сборки вложенной библиотекой (см. грабли), и повторять эту
			// беду вторым способом незачем.
			//
			// Кто первым инициализируется, зависит от порядка загрузки модов,
			// то есть от случая — значит полагаться на «мы успеем раньше»
			// нельзя вовсе. Уступаем всегда: обёртка для того и создана.
			boolean wrapper = net.fabricmc.loader.api.FabricLoader.getInstance()
					.isModLoaded("hypixel-mod-api");
			if (wrapper) {
				LOG.info("[skyblockru] hypixel-mod-api is present: "
						+ "using its transport, registering nothing of our own");
			} else {
				api.setModImplementation(INSTANCE);

				for (String identifier : api.getRegistry().getClientboundIdentifiers()) {
					register(identifier, true);
				}
				for (String identifier : api.getRegistry().getServerboundIdentifiers()) {
					register(identifier, false);
				}
			}

			// Режим и локация. Обработчик ставим ДО подписки: сервер отвечает
			// сразу, и потерять первый же пакет было бы обидно.
			api.createHandler(ClientboundLocationPacket.class, HypixelApi::onLocation);

			// ⚠️ Подписку шлём ПРИ ВХОДЕ и НЕ спрашивая `canSend`.
			//
			// История двух неудач. Сперва подписка уходила на JOIN, но код
			// сверялся с `ClientPlayNetworking.canSend` — тот отвечает «нет»,
			// пока сервер не объявит канал, и пакет молча не отправлялся.
			// Тогда подписку перевесили на событие «сервер объявил каналы»
			// (`ServerboundPlayChannelEvents.REGISTER`) — и оно не сработало
			// ни разу: в логе не было ни «subscribed», ни жалобы. То есть
			// Hypixel каналы НЕ ОБЪЯВЛЯЕТ, он их просто принимает.
			//
			// Значит спрашивать разрешения не у кого: шлём и смотрим на ответ.
			// Хуже не будет — на чужом сервере пакет просто уйдёт в никуда.
			ClientPlayConnectionEvents.JOIN.register((handler, sender, client) -> {
				subscribed = false;
				if (Hypixel.isOnHypixel()) {
					subscribe();
				}
			});

			// Если сервер всё же объявит каналы — подпишемся ещё раз: лишняя
			// подписка безвредна, а пропущенная стоит всей затеи.
			ServerboundPlayChannelEvents.REGISTER.register((handler, sender, client, channels) -> {
				List<String> hypixel = new ArrayList<>();
				for (Identifier channel : channels) {
					if (HYPIXEL_NAMESPACE.equals(channel.getNamespace())
							|| EVENT_NAMESPACE.equals(channel.getNamespace())) {
						hypixel.add(channel.toString());
					}
				}
				if (!hypixel.isEmpty()) {
					LOG.info("[skyblockru] server announced Hypixel channels: {}", hypixel);
					if (!subscribed) {
						subscribe();
					}
				}
			});

			ClientPlayConnectionEvents.DISCONNECT.register((handler, client) -> subscribed = false);

			ready = true;
			LOG.info("[skyblockru] Hypixel Mod API ready: {} clientbound, {} serverbound",
					api.getRegistry().getClientboundIdentifiers().size(), SERVERBOUND.size());
		} catch (RuntimeException | LinkageError problem) {
			// ⚠️ Громко, но не смертельно. Мод обязан работать и без API —
			// у нас есть заголовок панели. А вот молчаливый отказ был бы
			// худшим исходом: режим определялся бы хуже, и никто б не узнал.
			LOG.warn("[skyblockru] Hypixel Mod API unavailable, falling back to sidebar title", problem);
		}
	}

	private static void register(String identifier, boolean clientbound) {
		Identifier id = Identifier.tryParse(identifier);
		if (id == null) {
			LOG.warn("[skyblockru] bad Hypixel channel: {}", identifier);
			return;
		}
		CustomPacketPayload.Type<Raw> type = new CustomPacketPayload.Type<>(id);
		if (clientbound) {
			PayloadTypeRegistry.clientboundPlay().register(type, codecFor(type));
			ClientPlayNetworking.registerGlobalReceiver(type, (payload, context) ->
					context.client().execute(() -> receive(identifier, payload)));
		} else {
			PayloadTypeRegistry.serverboundPlay().register(type, codecFor(type));
			SERVERBOUND.put(identifier, type);
		}
	}

	private static void receive(String identifier, Raw payload) {
		// ⚠️ Приём логируем: без этого «API не работает» неотличимо от «сервер
		// молчит». Первые два захода отладки ушли именно на этот вопрос.
		LOG.info("[skyblockru] got {} ({} bytes)", identifier, payload.data().length);
		try {
			HypixelModAPI.getInstance().handle(identifier,
					new PacketSerializer(Unpooled.wrappedBuffer(payload.data())));
		} catch (RuntimeException problem) {
			LOG.warn("[skyblockru] broken Hypixel packet on {}", identifier, problem);
		}
	}

	private static void subscribe() {
		try {
			HypixelModAPI.getInstance().subscribeToEventPacket(ClientboundLocationPacket.class);
			subscribed = true;
			LOG.info("[skyblockru] subscribed to Hypixel location events");
		} catch (RuntimeException problem) {
			LOG.warn("[skyblockru] cannot subscribe to Hypixel location events", problem);
		}
	}

	/**
	 * Пришла локация. Тип сервера сравниваем с {@link GameType#SKYBLOCK} —
	 * это перечисление самой библиотеки, а не строка, которую надо угадывать.
	 */
	private static void onLocation(ClientboundLocationPacket packet) {
		ServerType type = packet.getServerType().orElse(null);
		boolean skyBlock = type == GameType.SKYBLOCK;
		String name = type == null ? "?" : type.name();
		Hypixel.noteServerType(name, skyBlock);
	}

	/** Успел ли API вообще встать — для {@code /skyblockru}. */
	public static boolean isReady() {
		return ready;
	}

	@Override
	public void onInit() {
		// Библиотека зовёт это сама; регистрацию каналов мы уже сделали в init().
	}

	@Override
	public boolean sendPacket(HypixelPacket packet) {
		CustomPacketPayload.Type<Raw> type = SERVERBOUND.get(packet.getIdentifier());
		if (type == null) {
			LOG.warn("[skyblockru] unknown Hypixel channel {}", packet.getIdentifier());
			return false;
		}
		// ⚠️ `canSend` НЕ спрашиваем: Hypixel свои каналы не объявляет, и проверка
		// отвечала бы «нет» всегда. Пакет уходит как есть — на чужом сервере он
		// просто останется без ответа, а тут дороже промолчать.
		FriendlyByteBuf buffer = new FriendlyByteBuf(Unpooled.buffer());
		packet.write(new PacketSerializer(buffer));
		byte[] data = new byte[buffer.readableBytes()];
		buffer.readBytes(data);
		try {
			ClientPlayNetworking.send(new Raw(type, data));
		} catch (RuntimeException problem) {
			LOG.warn("[skyblockru] cannot send {}: {}", packet.getIdentifier(), problem.toString());
			return false;
		}
		LOG.info("[skyblockru] sent {} ({} bytes)", packet.getIdentifier(), data.length);
		return true;
	}

	@Override
	public boolean isConnectedToHypixel() {
		return Hypixel.isOnHypixel();
	}
}
