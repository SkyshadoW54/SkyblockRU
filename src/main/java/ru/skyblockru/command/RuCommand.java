package ru.skyblockru.command;

import net.fabricmc.fabric.api.client.command.v2.ClientCommandRegistrationCallback;
import net.fabricmc.fabric.api.client.command.v2.FabricClientCommandSource;
import net.minecraft.ChatFormatting;
import net.minecraft.network.chat.Component;
import ru.skyblockru.SkyblockRuClient;
import ru.skyblockru.config.RuConfig;
import ru.skyblockru.core.Diagnostics;
import ru.skyblockru.core.Hypixel;
import ru.skyblockru.core.TextTranslator;
import ru.skyblockru.core.Translator;
import ru.skyblockru.core.UnknownStrings;

import static net.fabricmc.fabric.api.client.command.v2.ClientCommands.literal;

/**
 * Команда /skyblockru — перечитать словари, сбросить дамп, посмотреть статистику.
 *
 * <p>Весь текст идёт через {@link Component#translatable}: сам мод обязан говорить
 * на языке игрока, а не только по-русски. Строки лежат в assets/skyblockru/lang/,
 * базовый язык — en_us (на него Minecraft откатывается сам, если ключа нет).
 */
public final class RuCommand {

	private RuCommand() {
	}

	/**
	 * Команды мода. Игроку показываем только то, чем он реально пользуется.
	 *
	 * <p>⚠️ Разделение появилось перед раздачей мода чужим людям (решение
	 * игрока 02.08). Половина команд писалась ДЛЯ РАЗРАБОТКИ: `diag` печатает
	 * счётчики промахов, `dump` пишет собранное на диск, `test` гоняет
	 * самопроверку, `reload` перечитывает словари — а язык мод и так
	 * подхватывает сам. Игроку они не нужны, но в подсказке команд он видит
	 * их все и решает, что мод сложный.
	 *
	 * <p>Команды НЕ УДАЛЕНЫ, а спрятаны за {@code devCommands}: они нужны мне,
	 * а удалённое пришлось бы писать заново. Включается в config.json.
	 */
	public static void register() {
		ClientCommandRegistrationCallback.EVENT.register((dispatcher, access) -> {
			var root = literal("skyblockru")
					.executes(context -> stats(context.getSource()));
			if (RuConfig.get().devCommands) {
				addDevCommands(root);
			}
			addPlayerCommands(root);
			dispatcher.register(root);
		});
	}

	/** Ветки для разработки: счётчики, дамп, самопроверка, перечитывание. */
	private static void addDevCommands(
			com.mojang.brigadier.builder.LiteralArgumentBuilder<FabricClientCommandSource> root) {
		root
						.then(literal("reload").executes(context -> {
							RuConfig.load(SkyblockRuClient.configDir());
							Translator.reload(SkyblockRuClient.packsDir());
							TextTranslator.clearCache();
							reply(context.getSource(), ChatFormatting.GREEN,
									Component.translatable("skyblockru.cmd.reloaded",
											Translator.exactCount(), Translator.regexCount(),
											Translator.glossaryCount()));
							return 1;
						}))
						.then(literal("dump").executes(context -> {
							UnknownStrings.flush();
							reply(context.getSource(), ChatFormatting.GREEN,
									Component.translatable("skyblockru.cmd.dumped",
											SkyblockRuClient.configDir().resolve("dump").toString()));
							return 1;
						}))
						.then(literal("diag").executes(context -> diag(context.getSource())))
						.then(literal("test").executes(context -> {
							// Проверка строк, которые вручную не вызвать: чужой запрос
							// обмена, реплики NPC, полоса над хотбаром в разных видах
							for (Component line : ru.skyblockru.core.SelfTest.run()) {
								context.getSource().sendFeedback(line);
							}
							return 1;
						}))
						.then(literal("stats").executes(context -> stats(context.getSource())))
						// ⚠️ Переключатели РАСШИРЕННОГО перевода (ванильные названия,
						// зачарования SkyBlock, характеристики-жаргон). Игроку их больше
						// не показываем — работа отложена целиком (решение 03.08),
						// а словари убраны из index.json и в jar не едут. Здесь они
						// остались, чтобы не писать всё заново, когда работа вернётся:
						// впиши словарь обратно в index.json — и переключатель оживёт.
						.then(literal("packs").executes(context -> packs(context.getSource())))
						.then(literal("pack")
								.then(net.fabricmc.fabric.api.client.command.v2.ClientCommands
										.argument("id", com.mojang.brigadier.arguments.StringArgumentType.word())
										.then(literal("on").executes(context -> setPack(context.getSource(),
												com.mojang.brigadier.arguments.StringArgumentType
														.getString(context, "id"), true)))
										.then(literal("off").executes(context -> setPack(context.getSource(),
												com.mojang.brigadier.arguments.StringArgumentType
														.getString(context, "id"), false)))));
	}

	/** Ветки для игрока: что включить, что выключить, есть ли обновление. */
	private static void addPlayerCommands(
			com.mojang.brigadier.builder.LiteralArgumentBuilder<FabricClientCommandSource> root) {
		root
						.then(literal("update").executes(context -> {
							reply(context.getSource(), ChatFormatting.GRAY,
									Component.translatable("skyblockru.cmd.checking"));
							ru.skyblockru.core.UpdateService.check(true);
							return 1;
						}))
						// ⚠️ Команды clear здесь БОЛЬШЕ НЕТ и возвращать её не надо.
						// Она стирала собранное за все сессии разом, без отмены и без
						// подтверждения — одна опечатка рядом с /skyblockru dump стоила бы
						// всей работы. Нужно начать сбор заново — удалить файлы в
						// config/skyblockru/dump/ руками, осознанно.
						// ⚠️ Команд packs / pack <id> on|off здесь БОЛЬШЕ НЕТ (решение
						// игрока 03.08). Ими включался РАСШИРЕННЫЙ перевод: ванильные
						// названия предметов, названия зачарований SkyBlock и
						// характеристики-жаргон. Работа отложена целиком, а не отменена:
						// сами словари лежат в репозитории, но из index.json убраны
						// и в jar не попадают, поэтому включать нечего.
						// Команды переехали в ветку разработчика (devCommands) —
						// удалённое пришлось бы писать заново, когда до этой работы
						// дойдут руки.
						// Отправка непереведённого: включена по умолчанию, и игрок
						// должен иметь возможность её выключить одной командой —
						// иначе настройка невидима, а невидимая всё равно что нет.
						.then(literal("telemetry")
								.executes(context -> telemetry(context.getSource(), null))
								.then(literal("on").executes(context ->
										telemetry(context.getSource(), true)))
								.then(literal("off").executes(context ->
										telemetry(context.getSource(), false))))
						.then(literal("on").executes(context -> toggle(context.getSource(), true)))
						.then(literal("off").executes(context -> toggle(context.getSource(), false)));
	}

	/**
	 * Показать или переключить отправку непереведённых строк.
	 *
	 * @param on {@code null} — только показать состояние
	 */
	private static int telemetry(FabricClientCommandSource source, Boolean on) {
		RuConfig config = RuConfig.get();
		if (on != null) {
			config.telemetry = on;
			// ⚠️ Выключил — значит уже знает, что отправка есть: второй раз
			// рассказывать незачем.
			config.telemetryNotified = true;
			config.save();
		}
		reply(source, config.telemetry ? ChatFormatting.GREEN : ChatFormatting.GRAY,
				Component.translatable(config.telemetry
						? "skyblockru.telemetry.on" : "skyblockru.telemetry.off.done"));
		if (config.telemetry) {
			reply(source, ChatFormatting.GRAY,
					Component.translatable("skyblockru.telemetry.what"));
			reply(source, ChatFormatting.GRAY,
					Component.translatable("skyblockru.telemetry.off"));
		}
		return 1;
	}

	/** Что можно включить или выключить по вкусу. */
	private static int packs(FabricClientCommandSource source) {
		java.util.Map<String, String> optional = Translator.optionalPacks();
		reply(source, ChatFormatting.AQUA, Component.translatable("skyblockru.packs.title"));
		if (optional.isEmpty()) {
			reply(source, ChatFormatting.GRAY, Component.translatable("skyblockru.packs.none"));
			return 1;
		}
		optional.forEach((id, about) -> {
			boolean on = RuConfig.get().packs.getOrDefault(id, false);
			reply(source, on ? ChatFormatting.GREEN : ChatFormatting.GRAY,
					Component.translatable("skyblockru.packs.line", id,
							Component.translatable(on ? "skyblockru.word.on" : "skyblockru.word.off")));
			if (!about.isBlank()) {
				reply(source, ChatFormatting.GRAY,
						Component.translatable("skyblockru.packs.about", about));
			}
		});
		reply(source, ChatFormatting.GRAY, Component.translatable("skyblockru.packs.howto"));
		return 1;
	}

	private static int setPack(FabricClientCommandSource source, String id, boolean on) {
		if (!Translator.optionalPacks().containsKey(id)) {
			reply(source, ChatFormatting.RED, Component.translatable("skyblockru.packs.unknown", id));
			return 0;
		}
		RuConfig.get().packs.put(id, on);
		RuConfig.save();
		Translator.reload(SkyblockRuClient.packsDir());
		TextTranslator.clearCache();
		reply(source, on ? ChatFormatting.GREEN : ChatFormatting.YELLOW,
				Component.translatable("skyblockru.packs.set", id,
						Component.translatable(on ? "skyblockru.word.on" : "skyblockru.word.off"),
						Translator.exactCount() + Translator.glossaryCount()));
		return 1;
	}

	private static int toggle(FabricClientCommandSource source, boolean enabled) {
		RuConfig.get().enabled = enabled;
		RuConfig.save();
		reply(source, enabled ? ChatFormatting.GREEN : ChatFormatting.RED,
				Component.translatable(enabled ? "skyblockru.cmd.on" : "skyblockru.cmd.off"));
		return 1;
	}

	/**
	 * Полный разбор состояния. В чат — только сводка и то, что требует внимания;
	 * весь отчёт уходит в файл, потому что в чате он не поместится.
	 */
	private static int diag(FabricClientCommandSource source) {
		String report = Diagnostics.report(Translator.allRulePatterns());
		java.nio.file.Path file = SkyblockRuClient.configDir().resolve("diagnostics.txt");
		try {
			java.nio.file.Files.createDirectories(file.getParent());
			java.nio.file.Files.writeString(file, report, java.nio.charset.StandardCharsets.UTF_8);
		} catch (java.io.IOException exception) {
			reply(source, ChatFormatting.RED,
					Component.translatable("skyblockru.diag.writefailed", exception.toString()));
		}

		reply(source, ChatFormatting.AQUA, Component.translatable("skyblockru.diag.title"));
		reply(source, ChatFormatting.GRAY, Component.translatable("skyblockru.diag.session",
				Diagnostics.hitTotal(), UnknownStrings.total()));

		int problems = Diagnostics.loadProblemCount();
		reply(source, problems > 0 ? ChatFormatting.RED : ChatFormatting.GREEN,
				Component.translatable("skyblockru.diag.problems", problems));

		int colorLoss = Diagnostics.colorLossCount();
		reply(source, colorLoss > 0 ? ChatFormatting.YELLOW : ChatFormatting.GREEN,
				Component.translatable("skyblockru.diag.colorloss", colorLoss));

		// Сработавшая защита — не беда, а работа: показываем серым, не жёлтым.
		// Пока это считалось тем же счётчиком, «537» читалось как поломка.
		reply(source, ChatFormatting.GRAY,
				Component.translatable("skyblockru.diag.colorguard", Diagnostics.colorGuardCount()));

		int errors = Diagnostics.errorCount();
		reply(source, errors > 0 ? ChatFormatting.RED : ChatFormatting.GREEN,
				Component.translatable("skyblockru.diag.errors", errors));

		// ⚠️ Сбои, пойманные оградой в чужих точках перехвата. Без этой строки
		// Guard был бы обычной глушилкой: подсказка молча остаётся английской,
		// и понять почему нечем. Показываем ГДЕ упало — по одному месту в строку.
		int guarded = ru.skyblockru.core.Guard.total();
		reply(source, guarded > 0 ? ChatFormatting.RED : ChatFormatting.GREEN,
				Component.translatable("skyblockru.diag.guarded", guarded));
		if (guarded > 0) {
			ru.skyblockru.core.Guard.failures().forEach((where, count) ->
					reply(source, ChatFormatting.RED,
							Component.literal("   " + where + ": " + count)));
		}

		reply(source, ChatFormatting.GRAY,
				Component.translatable("skyblockru.diag.report", file.toString()));
		return 1;
	}

	private static int stats(FabricClientCommandSource source) {
		reply(source, ChatFormatting.AQUA,
				Component.translatable("skyblockru.stats.title", SkyblockRuClient.modVersion()));
		reply(source, ChatFormatting.GRAY,
				Component.translatable("skyblockru.stats.built", SkyblockRuClient.buildTime()));
		reply(source, ChatFormatting.GRAY, Component.translatable("skyblockru.stats.state",
				Component.translatable(RuConfig.get().enabled
						? "skyblockru.word.on" : "skyblockru.word.off"),
				Component.translatable(Hypixel.isOnHypixel()
						? "skyblockru.word.yes" : "skyblockru.word.no")));

		// Язык и есть ли под него словари — без этого игрок с чужим языком
		// увидит английскую игру и не поймёт, мод сломался или перевода нет.
		boolean has = Translator.hasLanguagePacks();
		reply(source, has ? ChatFormatting.GRAY : ChatFormatting.YELLOW,
				Component.translatable("skyblockru.stats.language", Translator.languageCode(),
						Component.translatable(has ? "skyblockru.word.yes" : "skyblockru.word.no")));
		if (!has) {
			reply(source, ChatFormatting.YELLOW, Component.translatable("skyblockru.stats.nopacks"));
		}
		// ⚠️ Язык игры и язык перевода — РАЗНЫЕ вещи, и когда они расходятся,
		// это надо сказать прямо. Мод переводит на русский независимо от языка
		// клиента; без этой строки игрок с английской игрой видел бы русский
		// текст и гадал, откуда он взялся и чем управляется.
		String dictionary = Translator.dictionaryLanguage();
		if (!dictionary.equalsIgnoreCase(Translator.languageCode())) {
			reply(source, ChatFormatting.GRAY,
					Component.translatable("skyblockru.stats.translateto", dictionary));
		}

		// Режим Hypixel и работает ли перевод прямо сейчас: без этой строки
		// «почему ничего не переводится» диагностировать нечем.
		boolean active = Hypixel.isActive();
		reply(source, active ? ChatFormatting.GRAY : ChatFormatting.YELLOW,
				Component.translatable("skyblockru.stats.mode", Hypixel.currentMode(),
						Component.translatable(active ? "skyblockru.word.yes" : "skyblockru.word.no")));

		// ⚠️ Клавиши называем ЗДЕСЬ, потому что возможность без упоминания —
		// невидимая, а невидимая настройка всё равно что отсутствующая.
		// Приглашения «Shift — подробности» видно на предмете со справкой,
		// а «показать оригинал» работает на ЛЮБОЙ подсказке, и подсказать
		// про него больше негде. Имя клавиши берём текущее: игрок мог
		// переназначить её в «Настройки → Управление».
		reply(source, ChatFormatting.GRAY, Component.translatable("skyblockru.stats.keys",
				ru.skyblockru.core.Keys.label(ru.skyblockru.core.Keys.ORIGINAL)));

		reply(source, ChatFormatting.GRAY, Component.translatable("skyblockru.stats.packs",
				Translator.packCount(), Translator.exactCount(),
				Translator.regexCount(), Translator.glossaryCount()));
		reply(source, ChatFormatting.GRAY,
				Component.translatable("skyblockru.stats.untranslated", UnknownStrings.total()));
		UnknownStrings.countsBySource().forEach((origin, count) ->
				reply(source, ChatFormatting.GRAY,
						Component.translatable("skyblockru.stats.source", origin, count)));
		return 1;
	}

	private static void reply(FabricClientCommandSource source, ChatFormatting color, Component text) {
		source.sendFeedback(text.copy().withStyle(color));
	}
}
