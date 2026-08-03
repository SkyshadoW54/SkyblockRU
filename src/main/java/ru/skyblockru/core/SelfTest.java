package ru.skyblockru.core;

import net.minecraft.ChatFormatting;
import net.minecraft.network.chat.Component;

import java.util.ArrayList;
import java.util.List;

/**
 * Самопроверка перевода на заранее известных строках.
 *
 * <p>Появилась из-за неудобной проверки: я предложил игроку «попроси кого-нибудь
 * прислать запрос обмена», хотя такие строки приходят от других людей и по
 * заказу не появляются. Проверять должен мод, а не игрок — ищущий добровольца.
 *
 * <p>Строки прогоняются через НАСТОЯЩИЙ {@link Translator}, а не через копию
 * его логики: копия проверяет саму себя и врёт ровно там, где ошибка.
 *
 * <p>Добавить случай = дописать строку в {@link #CASES}. Ожидаемого перевода
 * не пишем: он меняется от правки словаря, а проверяем мы другое — что строка
 * ВООБЩЕ находится и подстановки встают на место.
 */
public final class SelfTest {

	/**
	 * Что проверяем: строка как её присылает Hypixel + чего в переводе быть не должно.
	 *
	 * @param viaGlossary гнать через ГЛОССАРИЙ, а не через поиск в словаре.
	 *                    Нужно для случаев «этот кусок трогать нельзя»: глоссарий
	 *                    подставляет термины ВНУТРИ незнакомой строки, и
	 *                    {@link Translator#lookup} его не зовёт вовсе. Первая
	 *                    попытка проверить «Depth Champion» обычным случаем
	 *                    провалилась именно поэтому: перевода у строки нет и быть
	 *                    не должно, а проверка считала это провалом.
	 */
	private record Case(String source, String origin, String mustKeep, boolean viaGlossary, String mustDrop) {
		Case(String source, String origin, String mustKeep) {
			this(source, origin, mustKeep, false, null);
		}

		Case(String source, String origin, String mustKeep, boolean viaGlossary) {
			this(source, origin, mustKeep, viaGlossary, null);
		}

		/**
		 * Случай «этого куска в переводе остаться не должно».
		 *
		 * <p>Нужен там, где перевод НАХОДИТСЯ и без починки, а сломана только
		 * его часть. Так было с набором вариантов ответа: подпись «Выбери
		 * вариант:» переводилась всегда, а сами варианты оставались
		 * английскими — {@link Translator#lookup} отдавал непустой результат,
		 * и проверка «строка нашлась» такую беду не видит вовсе.
		 *
		 * <p>Ждать КОНКРЕТНЫЙ перевод по-прежнему нельзя: он меняется от правки
		 * словаря. А вот английский кусок оригинала — признак устойчивый.
		 */
		static Case drops(String source, String origin, String mustDrop) {
			return new Case(source, origin, null, false, mustDrop);
		}
	}

	/**
	 * Иконка Hypixel — символ приватной зоны Unicode. Собирается числом, а не
	 * пишется в исходник: в файле она невидима, и любой, кто откроет код, увидит
	 * пустое место и «поправит» его.
	 */
	private static final String HEART = String.valueOf((char) 0xE010);
	private static final String CRIT = String.valueOf((char) 0xE02C);

	/** Стрелка, которой Hypixel метит вариант ответа в столбике. */
	private static final String ARROW = String.valueOf((char) 0x279C);

	private static final List<Case> CASES = List.of(
			// Обмен: ник игрока подставляется через {s}. Эти строки приходят от
			// других людей, поэтому вручную их не вызвать — тем нужнее проверка.
			new Case("Usairim has sent you a trade request. Click here to accept!",
					TextTranslator.SRC_CHAT, "Usairim"),
			new Case("The /trade request from Usairim expired!",
					TextTranslator.SRC_CHAT, "Usairim"),
			new Case("Inventory full? Don't forget to check out your Storage inside the SkyBlock Menu!",
					TextTranslator.SRC_CHAT, null),

			// Задания NPC: имя предмета обязано уцелеть — по нему ищут на аукционе
			new Case("[NPC] Ryan: To receive it, we require Dark Oak Log x512!",
					TextTranslator.SRC_CHAT, "Dark Oak Log"),
			new Case("[NPC] Ryan: I need you to hold your Campfire Initiate Badge III so I can upgrade it!",
					TextTranslator.SRC_CHAT, "Campfire Initiate Badge III"),

			// Полоса над хотбаром: переводится по колонкам, середина бывает разной
			new Case("83 Defense", TextTranslator.SRC_ACTION_BAR, null),
			new Case("105/105 Mana", TextTranslator.SRC_ACTION_BAR, null),
			new Case("+36 Foraging (3,308/5k)", TextTranslator.SRC_ACTION_BAR, null),

			// Миньоны: название материала остаётся английским
			new Case("generating and mining Cobblestone!", TextTranslator.SRC_ITEM_LORE, "Cobblestone"),
			new Case("generating and harvesting carrots.", TextTranslator.SRC_ITEM_LORE, null),
			new Case("Requires dirt or soil nearby so", TextTranslator.SRC_ITEM_LORE, null),

			// Характеристики. Пришло по жалобе на экран профиля: там строка
			// написана БЕЗ двоеточия — иконка, название, число, — и ни одно
			// правило её не ловило. Форм оказалось четыре, все из живого дампа.
			new Case(HEART + " Health 1,234", TextTranslator.SRC_ITEM_LORE, null),
			new Case(CRIT + " Crit Chance 87.64%", TextTranslator.SRC_ITEM_LORE, null),
			new Case("+10 " + HEART + " Health", TextTranslator.SRC_CHAT, null),
			new Case("Health: +293 (+40) (+432) (+120)", TextTranslator.SRC_ITEM_LORE, null),
			new Case("Crit Chance: " + CRIT + "50", TextTranslator.SRC_TAB, null),
			// Составное имя целиком: «Depth Champion» — название бонуса, и
			// глоссарий не должен переводить в нём одно слово. Смесь языков
			// («Depth Чемпион») хуже, чем целая английская фраза.
			new Case("Tiered Bonus: Depth Champion (0/8)",
					TextTranslator.SRC_ITEM_LORE, "Depth Champion", true),

			// Смесь языков: глоссарий знает «Mining Spread», но вокруг него
			// английская проза. Подставить одно словосочетание — сделать хуже,
			// чем не трогать вовсе.
			new Case("Grants +5 Mining Spread on Ores and Blocks.",
					TextTranslator.SRC_ITEM_LORE, "Mining Spread", true),

			// ⚠️ Список зачарований с УРОВНЯМИ. Пришло по скриншоту: строка
			// оставалась целиком английской, хотя два названия из трёх словарь
			// знает. Причина была в счёте слов — римские «III» считались
			// английскими и перевешивали русский перевод. Уровней в списке
			// столько же, сколько названий, поэтому ломалось тем вернее, чем
			// больше зачарований переведено.
			new Case("Strong Vitality V, Sugar Rush III, Thorns III",
					TextTranslator.SRC_ITEM_LORE, null, true),
			new Case("Growth VI, Protection VI, Rejuvenate V",
					TextTranslator.SRC_ITEM_LORE, null, true),

			// Кусок разноцветной строки: «Talk to» лежит точной записью, а всё
			// остальное нет. Перевести один кусок — сделать смесь языков.
			new Case("Talk to Roddy in the Backwater Bayou to apply parts to this rod.",
					TextTranslator.SRC_ITEM_LORE, "Backwater Bayou", true),

			// Валюта Bits переводу не подлежит вовсе. Скрипт правил однажды
			// сам, молча, включил её перевод — пусть проверка следит.
			new Case("Bits: 1,250", TextTranslator.SRC_SCOREBOARD, "Bits"),

			// Боковая панель
			new Case("Purse: 40,213", TextTranslator.SRC_SCOREBOARD, null),
			new Case("Late Spring 19th", TextTranslator.SRC_SCOREBOARD, null),
			new Case("9:30am ☀", TextTranslator.SRC_SCOREBOARD, null),
			new Case("Talk to Susan", TextTranslator.SRC_SCOREBOARD, "Susan"),

			// ⚠️ НАБОР ВАРИАНТОВ ОТВЕТА СТОЛБИКОМ. Короткий набор Hypixel пишет
			// в строку («[YES] [NO]»), а длинный — столбиком, помечая каждый
			// вариант стрелкой. Второй вид не резался вовсе, и на экране
			// выходило худшее: подпись по-русски, варианты по-английски.
			// Проверяем ОТСУТСТВИЕ английского: перевод тут находится в любом
			// случае — подпись переводит правило, — поэтому обычная проверка
			// «строка нашлась» эту беду не увидит.
			Case.drops("Select an option: \n  " + ARROW + " [How are perks chosen?] \n  "
							+ ARROW + " [What are Special Mayors?]",
					TextTranslator.SRC_CHAT, "Special Mayors")
	);

	private SelfTest() {
	}

	/** Прогоняет все случаи и возвращает строки для вывода в чат. */
	public static List<Component> run() {
		List<Component> out = new ArrayList<>();
		int passed = 0;
		int failed = 0;

		for (Case test : CASES) {
			String result;
			if (test.viaGlossary()) {
				// Глоссарий вернул null — значит ничего не подменил, строка как была.
				// Для случаев «не трогать» это и есть успех.
				String changed = Translator.applyGlossary(test.source(), test.origin());
				result = changed == null ? test.source() : changed;
			} else {
				Translator.Match match = Translator.lookup(test.source(), test.origin(), null);
				result = match == null ? null : match.text();
			}

			if (result == null) {
				failed++;
				out.add(say(ChatFormatting.RED,
						Component.translatable("skyblockru.selftest.missing", test.source())));
				continue;
			}
			if (test.mustKeep() != null && !result.contains(test.mustKeep())) {
				failed++;
				out.add(say(ChatFormatting.RED,
						Component.translatable("skyblockru.selftest.lost", test.mustKeep(), result)));
				continue;
			}
			if (test.mustDrop() != null && result.contains(test.mustDrop())) {
				failed++;
				out.add(say(ChatFormatting.RED,
						Component.translatable("skyblockru.selftest.leftover", test.mustDrop(), result)));
				continue;
			}
			passed++;
			out.add(line(ChatFormatting.GRAY, test.source()));
			out.add(line(ChatFormatting.GREEN, "   " + result));
		}

		out.add(0, say(failed == 0 ? ChatFormatting.GREEN : ChatFormatting.YELLOW,
				Component.translatable("skyblockru.selftest.header", passed, CASES.size())));
		return out;
	}

	/** Проверяемые строки показываем как есть — это данные, а не речь мода. */
	private static Component line(ChatFormatting color, String text) {
		return Component.literal(text).withStyle(color);
	}

	private static Component say(ChatFormatting color, Component text) {
		return text.copy().withStyle(color);
	}
}
