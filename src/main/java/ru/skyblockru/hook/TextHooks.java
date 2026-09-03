package ru.skyblockru.hook;

import net.fabricmc.fabric.api.client.item.v1.ItemTooltipCallback;
import net.fabricmc.fabric.api.client.message.v1.ClientReceiveMessageEvents;
import net.minecraft.core.component.DataComponents;
import net.minecraft.nbt.CompoundTag;
import net.minecraft.network.chat.Component;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.item.component.CustomData;
import ru.skyblockru.config.RuConfig;
import ru.skyblockru.core.TextTranslator;

import java.util.List;

/**
 * Точки, для которых у Fabric API есть готовые события — здесь миксины не нужны.
 * Чем меньше миксинов, тем меньше ломается при обновлении Minecraft.
 */
public final class TextHooks {

	private TextHooks() {
	}

	public static void register() {
		// Чат. На Hypixel почти всё приходит системными сообщениями, а не как реплики игроков.
		ClientReceiveMessageEvents.MODIFY_GAME.register((message, overlay) -> {
			if (!RuConfig.get().targets.chat) {
				return message;
			}
			// строка над хотбаром приходит сюда же — у неё свой выключатель
			String origin = overlay ? TextTranslator.SRC_ACTION_BAR : TextTranslator.SRC_CHAT;
			if (overlay && !RuConfig.get().targets.actionBar) {
				return message;
			}
			// ⚠️ При сбое отдаём ИСХОДНОЕ сообщение: непереведённая строка
			// в чате — мелочь, а проглоченное сообщение игрок не восстановит.
			return ru.skyblockru.core.Guard.get("chat", () ->
					TextTranslator.translate(message, origin), message);
		});

		// Описание предмета (лор) — строки под названием.
		ItemTooltipCallback.EVENT.register((stack, context, type, lines) ->
				ru.skyblockru.core.Guard.run("item_lore", () ->
						translateTooltip(stack, lines)));
	}

	/**
	 * Перевод подсказки предмета. Вынесен из обработчика, чтобы его целиком
	 * накрывала {@link ru.skyblockru.core.Guard} — см. её описание: список
	 * строк Fabric отдаёт нам БЕЗ копирования (проверено javap по
	 * {@code fabric-item-api-v1}: он берёт {@code cir.getReturnValue()}),
	 * то есть исключение отсюда уронит построение подсказки целиком —
	 * и у соседних модов тоже.
	 */
	private static void translateTooltip(ItemStack stack, List<Component> lines) {
		if (!RuConfig.get().targets.itemLore) {
			return;
		}
		// ⚠️ ТОЛЬКО ГЛАВНЫЙ ПОТОК. Каталоги вроде REI и JEI строят подсказки
		// пачками в фоне, чтобы наполнить поиск. Нам там делать нечего:
		// игрок этих предметов не видел (дамп забьётся тем, мимо чего он
		// не проходил), работа впустую даёт лаги, а `Wiki.append` пишет
		// приготовленную панель в статическое поле — из чужого потока это
		// гонка, и на экран уехала бы справка не от того предмета.
		net.minecraft.client.Minecraft client = net.minecraft.client.Minecraft.getInstance();
		if (client != null && !client.isSameThread()) {
			return;
		}
		// Имя предмета уходит в дамп вместе со строкой: без него «Storage unlocked
		// at tier VIII» непонятно к чему относится, а с ним видно, что это миньон.
		String itemName = null;
		try {
			itemName = stack.getHoverName().getString();
		} catch (RuntimeException ignored) {
			// имя не достали — переживём, контекст необязателен
		}
		// Подсказку запоминаем ЦЕЛИКОМ, до перевода: обрывок фразы в отрыве
		// от соседей перевести нельзя, а весь список у нас уже на руках.
		java.util.List<String> raw = new java.util.ArrayList<>(lines.size());
		for (Component line : lines) {
			raw.add(line.getString());
		}
		// ⚠️⚠️ ХВОСТ ЧУЖИХ МОДОВ ОТРЕЗАЕМ ДО ВСЕГО ОСТАЛЬНОГО.
		//
		// REI, EMI и JEI дописывают в конец подсказки строку «Minecraft»
		// (имя мода-владельца предмета), клиент при F3+H — идентификатор
		// и число компонентов, NEU — цены. Их обработчики стоят раньше нашего,
		// и строки уже лежат в списке. Пустой строкой от лора они не отделены,
		// поэтому `Paragraphs.runs` приклеивал их к последнему куску: ключ
		// «Left-click to summon! … Right-click to convert to an item! Minecraft»
		// в словаре не находился, и действия питомца оставались английскими
		// у всех, у кого стоит REI или EMI. Прислано игроком скриншотом 03.09;
		// в блоках от игроков таких подсказок 312.
		//
		// Граница берётся из ДАННЫХ предмета (компонент лора), а не по виду
		// строки: список имён соседей отстал бы от первого нового. Хвост
		// возвращаем на место в `finally` — чужие строки нам не принадлежат,
		// и пропасть они не должны даже при нашем исключении.
		int tail = ru.skyblockru.core.TooltipTail.start(raw, ru.skyblockru.core.Items.loreTexts(stack));
		java.util.List<Component> foreignTail = java.util.List.of();
		if (tail < lines.size()) {
			foreignTail = new java.util.ArrayList<>(lines.subList(tail, lines.size()));
			lines.subList(tail, lines.size()).clear();
			raw = new java.util.ArrayList<>(raw.subList(0, tail));
		}
		try {
			translateBody(stack, lines, itemName, raw);
		} finally {
			lines.addAll(foreignTail);
		}
	}

	/** Всё, что мод делает с подсказкой ПОСЛЕ отрезания чужого хвоста. */
	private static void translateBody(ItemStack stack, List<Component> lines, String itemName,
			java.util.List<String> raw) {
		ru.skyblockru.core.UnknownStrings.recordTooltip(itemName, raw);

		// ⚠️ РАЗВЕДКА: есть ли у предмета идентификатор надёжнее текста.
		// Весь наш перевод привязан к отображаемой строке, а у предмета
		// может лежать настоящий id в NBT. Пока только записываем найденное
		// в дамп — решать по фактам, а не по памяти о том, «как обычно
		// делают моды». Подробности в UnknownStrings.recordItemId.
		// ⚠️ NBT читаем ОДИН раз на подсказку и передаём дальше.
		// `Items.nbt` делает copyTag() — полную копию тега, — и раньше
		// каждый спрашивающий читал его сам: четыре-пять копий одного
		// и того же на КАЖДУЮ подсказку.
		net.minecraft.nbt.CompoundTag nbt = ru.skyblockru.core.Items.nbt(stack);
		recordItemId(nbt, itemName);

		// Снимок ДО перевода — вместе с цветами. Нужен, чтобы подсказку
		// можно было посмотреть вне игры: tools/preview.py рисует её
		// в терминале, и проверка перестаёт зависеть от скриншотов.
		String before = ru.skyblockru.core.UnknownStrings.snapshot(lines);

		// ⚠️ ПОКАЗАТЬ ОРИГИНАЛ — выход ЗДЕСЬ, а не в начале метода.
		//
		// Всё, что выше, — это СБОР: строки, идентификатор, снимок подсказки.
		// Он обязан идти и при зажатой клавише, иначе игрок, сверяющийся
		// с гайдом, молча переставал бы пополнять корпус — причём ровно теми
		// подсказками, которые ему интересны. А ниже начинается ПЕРЕВОД,
		// и вот его-то и надо пропустить.
		if (ru.skyblockru.core.Keys.showingOriginal()) {
			return;
		}

		// Сперва абзацами: сервер режет описание по ширине окна, а не по
		// смыслу, и построчный перевод вынужден повторять чужие границы.
		// Абзац, для которого есть перевод, перекладываем заново; для
		// остальных всё остаётся как было — сломать нечего.
		java.util.Set<Component> fromParagraphs = ru.skyblockru.core.Paragraphs.apply(
				lines, TextTranslator.SRC_ITEM_LORE, itemName, enchantsOf(stack, nbt));
		if (!fromParagraphs.isEmpty()) {
			ru.skyblockru.core.Diagnostics.hit(TextTranslator.SRC_ITEM_LORE,
					ru.skyblockru.core.Diagnostics.KIND_PARAGRAPH);
		}
		// ⚠️⚠️ ИМЯ ПРЕДМЕТА ПЕРЕВОДИТСЯ ЗДЕСЬ, А НЕ ПЕРЕХВАТОМ getHoverName.
		//
		// Раньше стоял миксин на `ItemStack.getHoverName`, и подменённое имя
		// доставалось ВСЕМ, кто спрашивает игру. Замер 03.09 по jar соседей:
		// этот метод зовут 115 классов SkyHanni и 72 Skyblocker. У SkyHanni
		// из-за этого гасла подсветка нажатых карточек в Superpairs: его
		// `SuperPairsItemVisibility` ищет в ИМЕНИ английское «?» и «Click any
		// button!», а получал русский текст. Подробности в core/ItemName.
		//
		// ⚠️ ПОСЛЕ `Paragraphs.apply`, а не до: `nameAside` отрезает первую
		// строку, сравнивая её с именем предмета, и оба должны быть на ОДНОМ
		// языке. Переведи мы имя раньше — сравнение перестало бы совпадать.
		java.util.Set<Component> done = fromParagraphs;
		if (!lines.isEmpty() && itemName != null) {
			Component first = lines.get(0);
			// ⚠️ Первая строка не ВСЕГДА имя (замер: 96% блоков из 52 931).
			// Спрашиваем не порядок, а совпадение с именем предмета.
			String bare = ru.skyblockru.core.LegacyText.strip(first.getString()).trim();
			if (bare.equals(ru.skyblockru.core.LegacyText.strip(itemName).trim())) {
				Component named = ru.skyblockru.core.ItemName.translate(stack, first);
				if (named != null && named != first) {
					lines.set(0, named);
					done = new java.util.HashSet<>(fromParagraphs);
					done.add(named);
				}
			}
		}
		translateLines(lines, itemName, done);
		ru.skyblockru.core.UnknownStrings.recordPreview(itemName, before,
				ru.skyblockru.core.UnknownStrings.snapshot(lines));
		// Справка по терминам — ПОСЛЕ снимка: это наша добавка, а не то,
		// что прислал Hypixel, и в сравнении подсказок ей делать нечего.
		ru.skyblockru.core.Wiki.append(stack, lines);
	}

	/**
	 * Зачарования предмета ПО ДАННЫМ СЕРВЕРА, а не по виду строки.
	 *
	 * <p>Hypixel кладёт в NBT готовый список: {@code enchantments:
	 * {bane_of_arthropods:6, champion:10}}. Это избавляет от признака
	 * «имя + римский уровень», который ловил коллекции («Ice IV») — грабля
	 * записана, и правку по ней уже откатывали.
	 *
	 * <p>⚠️ Пустой набор и null для {@code Paragraphs} значат одно: «данных
	 * нет, работай по форме». Список работает ФИЛЬТРОМ и только когда он
	 * не пуст — иначе предмет, чьи зачарования сервер в NBT не положил,
	 * перестал бы резаться на секции. Подробности в Paragraphs.enchantHead.
	 */
	private static java.util.Set<String> enchantsOf(ItemStack stack, net.minecraft.nbt.CompoundTag nbt) {
		// Чтение живёт в core/Items — одно на весь мод. Копия здесь разошлась бы
		// с той, что спрашивает справка, при первой же правке формата.
		return ru.skyblockru.core.Items.enchantsOf(stack, nbt);
	}

	/**
	 * Достаёт идентификатор предмета из NBT и отдаёт его в дамп.
	 *
	 * <p>Сигнатуры проверены {@code javap} по jar 26.2, а не взяты из примеров
	 * под 1.21 — в этом проекте они уже дважды не компилировались:
	 * {@code ItemStack.get(DataComponents.CUSTOM_DATA)} отдаёт {@link CustomData},
	 * у него {@code copyTag()}, а {@code CompoundTag.getString} в 26.2
	 * возвращает {@code Optional}, поэтому берём {@code getStringOr}.
	 *
	 * <p>⚠️ Ошибки глушим молча и намеренно: это разведка, и уронить из-за неё
	 * подсказку предмета было бы обменом важного на любопытное.
	 */
	private static void recordItemId(CompoundTag tag, String itemName) {
		try {
			if (tag == null) {
				return;
			}
			// Разбор — в core/Items: и id, и ключи читаются там же, где их
			// читает справка. Про то, что id лежит В КОРНЕ custom_data,
			// а не в «ExtraAttributes», написано в самом Items.idOf.
			String id = ru.skyblockru.core.Items.idOf(tag);
			ru.skyblockru.core.UnknownStrings.recordItemId(
					id, itemName, ru.skyblockru.core.Items.keysOf(tag));
			// Образец сырого NBT — чтобы увидеть СТРУКТУРУ, а не только имена
			// ключей: зачарования, самоцветы и перековка приходят данными,
			// и по ним строку можно СОБИРАТЬ, а не разбирать обратно.
			// ⚠️⚠️ СТРОКУ СТРОИМ, ТОЛЬКО ЕСЛИ ОНА НУЖНА. Раньше `tag.toString()`
			// считался ДО вызова, а метод первым делом выходил: образцов уже 400,
			// потолок упёрся дважды. То есть весь NBT предмета сериализовался
			// в строку и выбрасывался — на КАЖДОЙ подсказке. Разведка по id
			// закончена 30.07, и работа эта мёртвая вдвойне.
			if (ru.skyblockru.core.UnknownStrings.wantsNbtSample()) {
				ru.skyblockru.core.UnknownStrings.recordNbtSample(id, tag.toString());
			}
		} catch (RuntimeException ignored) {
			// NBT не достали — подсказку это ломать не должно
		}
	}

	/**
	 * @param fromParagraphs строки, которые уже перевёл {@link ru.skyblockru.core.Paragraphs}.
	 *                       Их трогать нельзя: они на русском и готовы. Пройтись по ним
	 *                       значило бы записать собственный перевод в дамп как
	 *                       «непереведённое» и раздуть счётчик, а с включённым
	 *                       glossaryPass — ещё и подменить имя внутри готовой фразы.
	 */
	private static void translateLines(List<Component> lines, String itemName,
			java.util.Set<Component> fromParagraphs) {
		for (int i = 0; i < lines.size(); i++) {
			Component line = lines.get(i);
			if (fromParagraphs.contains(line)) {
				continue;
			}
			Component translated = TextTranslator.translate(line, TextTranslator.SRC_ITEM_LORE, itemName);
			if (translated != line) {
				lines.set(i, translated);
			}
		}
	}
}
