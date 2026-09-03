package ru.skyblockru.core;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;

/**
 * Где в подсказке предмета кончается текст Hypixel и начинаются строки
 * ЧУЖИХ модов.
 *
 * <p>⚠️ ЗАЧЕМ. REI, EMI и JEI дописывают в конец подсказки имя мода-владельца
 * предмета — синюю курсивную строку «Minecraft» (у Hypixel все предметы
 * ванильные). При включённых F3+H сам клиент дописывает идентификатор
 * («minecraft:player_head») и число компонентов; NEU и Skyblocker кладут
 * туда же цены. Все они регистрируют обработчик ПОДСКАЗКИ раньше нашего
 * (пруф на скриншоте игрока: наше приглашение «Shift — подробности» стояло
 * ПОСЛЕ «Minecraft»), и их строки уже лежат в списке, когда мы его получаем.
 *
 * <p>Пустой строкой они от лора не отделены, поэтому {@link Paragraphs#runs}
 * приклеивал их к последнему куску: ключ «Left-click to summon! … Right-click
 * to convert to an item! Minecraft» в словаре не находился, абзац уходил
 * на построчный путь, а там перевода не было — три строки действий питомца
 * оставались английскими у ВСЕХ, у кого стоит REI или EMI. Замер по блокам
 * от игроков: 312 подсказок кончаются строкой «Minecraft».
 *
 * <p>⚠️ ПРИЗНАК — НЕ ФОРМА СТРОКИ, А ДАННЫЕ ПРЕДМЕТА. Список «Minecraft»,
 * «minecraft:…», «NBT: N tag(s)» отстал бы от первого же нового соседа
 * (записанная семья бед проекта). Зато лор предмета лежит в его компоненте
 * {@code minecraft:lore}, и всё, что идёт в подсказке ПОСЛЕ последней строки
 * лора, прислал не Hypixel. Это железно: чужие строки могут стоять только
 * после лора — раньше их вставить некуда.
 *
 * <p>⚠️ ОШИБАЕМСЯ В БЕЗОПАСНУЮ СТОРОНУ. Если последняя строка лора в подсказке
 * не нашлась (сосед вроде SkyHanni успел её переписать), хвост не режем
 * вовсе — поведение ровно то, что было до этой правки. Отрезать лишнее
 * значило бы оставить строку Hypixel без перевода, а не отрезать — лишь
 * не починить чужой хвост.
 *
 * <p>Чистая логика без Minecraft: проверяется настоящей Java без игры
 * ({@code tools/check_tooltip_tail.py}).
 */
public final class TooltipTail {

	private TooltipTail() {
	}

	/**
	 * Индекс первой чужой строки; {@code tooltip.size()}, если хвоста нет.
	 *
	 * @param tooltip строки подсказки текстом, как они лежат в списке
	 * @param lore    строки лора предмета текстом, как их прислал сервер
	 */
	public static int start(List<String> tooltip, List<String> lore) {
		if (tooltip == null || lore == null || tooltip.size() < 2 || lore.isEmpty()) {
			return tooltip == null ? 0 : tooltip.size();
		}
		// Последняя НЕПУСТАЯ строка лора: пустой хвост у лора бывает, а искать
		// пустую строку в подсказке бессмысленно — их там много.
		String last = null;
		for (int i = lore.size() - 1; i >= 0; i--) {
			String candidate = lore.get(i);
			if (candidate != null && !candidate.trim().isEmpty()) {
				last = candidate.trim();
				break;
			}
		}
		if (last == null) {
			return tooltip.size();
		}
		// Ищем С КОНЦА: имя предмета стоит первой строкой и в лоре не
		// повторяется, а чужие строки стоят только в хвосте. Первое совпадение
		// с конца — это и есть граница лора.
		for (int i = tooltip.size() - 1; i >= 1; i--) {
			String line = tooltip.get(i);
			if (line != null && line.trim().equals(last)) {
				return i + 1;
			}
		}
		// Последней строки лора в подсказке нет: её переписал сосед. Не гадаем.
		return tooltip.size();
	}

	/**
	 * Проверка без игры: на входе первая строка — число строк лора N, затем
	 * N строк лора, затем строки подсказки; на выходе индекс начала хвоста.
	 */
	public static void main(String[] args) throws Exception {
		BufferedReader in = new BufferedReader(
				new InputStreamReader(System.in, StandardCharsets.UTF_8));
		int count = Integer.parseInt(in.readLine().trim());
		List<String> lore = new ArrayList<>();
		for (int i = 0; i < count; i++) {
			lore.add(in.readLine());
		}
		List<String> tooltip = new ArrayList<>();
		String line;
		while ((line = in.readLine()) != null) {
			tooltip.add(line);
		}
		System.out.println(start(tooltip, lore));
	}
}
