package ru.skyblockru.core;

import net.minecraft.core.Holder;
import net.minecraft.core.component.DataComponents;
import net.minecraft.nbt.CompoundTag;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.item.component.CustomData;
import net.minecraft.world.item.enchantment.Enchantment;
import net.minecraft.world.item.enchantment.ItemEnchantments;

import java.util.HashSet;
import java.util.LinkedHashSet;
import java.util.Set;

/**
 * Данные предмета из NBT — то, что сервер говорит о вещи ПРЯМО, а не текстом.
 *
 * <p><b>Зачем.</b> Весь перевод в этом проекте привязан к отображаемой строке:
 * обобщённой по числам, очищенной от цветов и склеенной из кусков, которые
 * Hypixel разрезал по ширине окна ИГРОКА. Каждое звено — место, где стороны
 * расходятся, и почти все грабли проекта оттуда. А в NBT лежат готовые факты:
 * идентификатор предмета, список зачарований с уровнями, самоцветы, перековка.
 *
 * <p>⚠️ <b>Формат РАЗНЫЙ в клиенте и в API, и это не мелочь.</b> Клиент 1.20.5+
 * держит данные в компонентах: {@code custom_data} и сразу {@code id} в корне.
 * А API аукциона отдаёт старый формат, где всё завёрнуто в {@code ExtraAttributes}.
 * Код, написанный под один, на другом молча вернёт пустоту — так и вышло
 * с первой попыткой, собравшей НОЛЬ идентификаторов. Читаем оба пути.
 *
 * <p>⚠️ Отдельным классом, чтобы чтение было ОДНО. Сперва оно жило приватным
 * методом в {@code TextHooks}, а когда понадобилось справке — копия разошлась бы
 * с оригиналом при первой же правке. В этом проекте копии признаков расходились
 * трижды, и каждый раз молча.
 */
public final class Items {

	private Items() {
	}

	/** Сырой NBT предмета или null. */
	public static CompoundTag nbt(ItemStack stack) {
		if (stack == null) {
			return null;
		}
		try {
			CustomData data = stack.get(DataComponents.CUSTOM_DATA);
			return data == null ? null : data.copyTag();
		} catch (RuntimeException ignored) {
			return null;
		}
	}

	/**
	 * Идентификатор SkyBlock: «HYPERION», «STARRED_MIDAS_SWORD».
	 *
	 * <p>⚠️ Лежит в КОРНЕ {@code custom_data}, а не в «ExtraAttributes», как
	 * было в старых версиях. Проверено на живых данных: ключ {@code id}
	 * встретился 4130 раз в корне и ни разу во вложенной обёртке.
	 *
	 * @return идентификатор либо пустая строка
	 */
	public static String idOf(ItemStack stack) {
		CompoundTag tag = nbt(stack);
		if (tag == null) {
			return "";
		}
		String id = string(tag, "id");
		if (!id.isBlank()) {
			return id;
		}
		return string(nested(tag, "ExtraAttributes"), "id");
	}

	/**
	 * Зачарования предмета — нормализованные имена, как их сравнивает
	 * {@link Paragraphs#bareName}.
	 *
	 * <p>⚠️ Разница между «набор пуст» и «набора нет» существенная, и потребители
	 * обязаны её соблюдать: <b>null</b> и пустой набор значат «данных нет,
	 * работай по форме», непустой — «вот полный список, всё прочее не зачарование».
	 * У 76 предметов из 87 собранных {@code enchantments} отсутствует вовсе
	 * (морковка, черепа, петы), и трактуй мы это как запрет — предметы
	 * с зачарованиями перестали бы резаться на секции.
	 *
	 * <p>Замер, ради которого всё затевалось: в живом дампе 1340 строк вида
	 * «Имя IV» зачарованиями НЕ являются — коллекции («Melon Slice VII»),
	 * уровни навыков, истребители, эссенции. Признак по форме их не отличает.
	 */
	public static Set<String> enchantsOf(ItemStack stack) {
		CompoundTag tag = nbt(stack);
		if (tag == null) {
			return null;
		}
		CompoundTag list = nested(tag, "enchantments");
		if (list.isEmpty()) {
			list = nested(nested(tag, "ExtraAttributes"), "enchantments");
		}
		// ⚠️ НЕТ СПИСКА SKYBLOCK — НЕ ФИЛЬТРУЕМ ВОВСЕ, даже если ваниль есть.
		//
		// Наступил на это 05.08, чиня соседнюю беду: начал собирать ванильные
		// и возвращать их сами по себе. У дрели SkyBlock-часть не прочиталась,
		// список вышел ИЗ ОДНОЙ ВАНИЛИ — и «Flowstate III», «Lapidary V»,
		// «Prismatic V» перестали признаваться заголовками, хотя раньше
		// признавались по форме. Стало хуже, чем было.
		//
		// Правило записано в этом файле выше и нарушено мной же: null и пустой
		// набор значат «данных нет, работай по форме». Неполный список хуже
		// пустого — он ЗАПРЕЩАЕТ то, о чём просто не знает.
		if (list.isEmpty()) {
			return null;
		}
		Set<String> out = new HashSet<>();
		for (String key : keys(list)) {
			out.add(Paragraphs.bareName(key));
		}
		// ⚠️ ВАНИЛЬНЫЕ ЗАЧАРОВАНИЯ ЛЕЖАТ ОТДЕЛЬНО, и без них список НЕПОЛОН.
		//
		// Hypixel держит свои в custom_data, а Efficiency, Sharpness, Protection —
		// это ваниль Minecraft, и она в своём компоненте. Список выходил неполным,
		// а работает он ЗАПРЕТОМ: раз он не пуст, всё, чего в нём нет, заголовком
		// не считается. На топоре игрока «Efficiency V» из-за этого не признавался
		// заголовком, секция не вырезалась — и купленный перевод (он лежит
		// в 96-paragraphs.json) не спрашивался ни разу.
		//
		// ⚠️ Это ТРЕТИЙ раз, когда фильтр по данным сервера отсекает СВОЁ: сперва
		// ультимативные с префиксом «ultimate_», потом справка по Alt, теперь
		// ванильные. Признак один — «сервер про это знает», и знать надо оба
		// источника, а не тот, что вспомнили первым.
		// ⚠️ Имя берём getRegisteredName(), а не через ResourceKey: у ключа метод
		// зовётся по-разному в разных версиях («identifier()» в 26.2 против
		// «location()» ниже), и пришлось бы заводить замену Stonecutter ради
		// одной строки. getRegisteredName отдаёт «minecraft:efficiency» и есть
		// во всех версиях, которые мы собираем.
		ItemEnchantments vanilla = stack.get(DataComponents.ENCHANTMENTS);
		if (vanilla != null) {
			for (Holder<Enchantment> holder : vanilla.keySet()) {
				String name = holder.getRegisteredName();
				int colon = name.indexOf(':');
				out.add(Paragraphs.bareName(colon >= 0 ? name.substring(colon + 1) : name));
			}
		}
		return out;
	}

	/** Ключи верхнего уровня — для разведки: что сервер вообще присылает. */
	public static Set<String> keysOf(ItemStack stack) {
		CompoundTag tag = nbt(stack);
		if (tag == null) {
			return Set.of();
		}
		Set<String> keys = new LinkedHashSet<>(keys(tag));
		for (String key : compound(tag, "ExtraAttributes")) {
			keys.add("ExtraAttributes." + key);
		}
		return keys;
	}

	// ─── Чтение NBT: имена методов менялись между поколениями игры ───
	//
	// ⚠️ ОБЁРТКИ, А НЕ ЗАМЕНЫ ПО ВСЕМУ КОДУ. Замена «keySet()» через Stonecutter
	// сломала бы `Translator`, `Wiki` и `UnknownStrings`: там это обычные Map,
	// и к версии игры они отношения не имеют. Расходятся ровно три вызова,
	// и все три живут в этом классе — значит и условие должно быть здесь.
	//
	// ⚠️ Порог 1.21.5 ЗАМЕРЕН: на 1.21.4 сборка падает на `getCompoundOrEmpty`,
	// `getStringOr` и `keySet`, на 1.21.5 — уже нет.

	/** Строка из тега: в старых версиях {@code getString} возвращал пустую сам. */
	private static String string(CompoundTag tag, String key) {
		//? if >=1.21.5 {
		return tag.getStringOr(key, "");
		//?} else
		/*return tag.getString(key);*/
	}

	/** Вложенный тег. */
	private static CompoundTag nested(CompoundTag tag, String key) {
		//? if >=1.21.5 {
		return tag.getCompoundOrEmpty(key);
		//?} else
		/*return tag.getCompound(key);*/
	}

	/** Имена ключей тега. */
	private static Set<String> keys(CompoundTag tag) {
		//? if >=1.21.5 {
		return tag.keySet();
		//?} else
		/*return tag.getAllKeys();*/
	}

	/** Ключи вложенного тега — то, что нужно почти всем вызовам разом. */
	private static Set<String> compound(CompoundTag tag, String key) {
		return keys(nested(tag, key));
	}
}
