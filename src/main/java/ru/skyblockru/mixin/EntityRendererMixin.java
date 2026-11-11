package ru.skyblockru.mixin;

import com.llamalad7.mixinextras.injector.ModifyExpressionValue;
import com.llamalad7.mixinextras.sugar.Local;
import net.minecraft.client.renderer.entity.EntityRenderer;
import net.minecraft.network.chat.Component;
import net.minecraft.world.entity.Entity;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import ru.skyblockru.config.RuConfig;
import ru.skyblockru.core.TextTranslator;

/**
 * Надписи над сущностями — в ТОЧКЕ ОТРИСОВКИ, а не в методе чтения.
 *
 * <p>На Hypixel это главным образом «голограммы»: невидимые стойки для брони
 * с текстом — здоровье мобов, таймеры, вывески у NPC.
 *
 * <p>⚠️ До 17.09 перевод стоял на {@code Entity.getCustomName} — и доставался
 * ВСЕМ, кто спрашивает имя у игры. Замер по сборке SkyBlock Enhanced 5.2.11
 * (константный пул каждого jar, вложенные тоже): имя сущности читают
 * Skyblocker ({@code HealthBars}, {@code DungeonManager}, {@code FishingHelper},
 * {@code CompactDamage} — 10 классов через {@code getCustomName}, 23 через
 * {@code getName}), SkyHanni ({@code MinionFeatures}, {@code DataWatcherApi},
 * 33 класса через {@code getName}), Feesh (таймеры по именам стендов,
 * 8 классов), SBO ({@code DianaMobDetect}), Odin (12) и skyblock-api
 * (вложена в Custom Scoreboard, SkyOcean, SkyBlockPv, Catharsis, Stella).
 * {@code HealthBars} ищет в имени стойки английские «Blaze», «The Professor»,
 * «Guardian» — а получал «Ифрит». Это ЧЕТВЁРТОЕ повторение одной семьи:
 * так же ломали таб (дважды), имя предмета и заголовок окна.
 *
 * <p>Здесь подмена живёт ровно до экрана: игра зовёт {@code getNameTag},
 * кладёт результат в {@code EntityRenderState.nameTag} и рисует. Мы меняем
 * значение МЕЖДУ вызовом и записью — всякий, кто спросит сущность сам,
 * получит оригинал Hypixel.
 *
 * <p>⚠️ Почему ВЫЗОВ, а не {@code @ModifyReturnValue} на самом {@code getNameTag}:
 * его тоже читают соседи. Skyblocker ({@code EntityRendererMixin}) меняет
 * его результат своим именем, owo-lib зовёт его через accessor. Встав
 * на вызов, мы переводим ПОСЛЕДНИМИ — уже после чужих правок, и на экран
 * уходит то, что решили они, только по-русски.
 *
 * <p>⚠️ Только сущности С custom name — ровно область прежнего перехвата.
 * {@code getNameTag} отдаёт {@code getDisplayName()} и у игроков тоже,
 * а там ник с рангом из команды: без оговорки чужие ники потекли бы
 * в дамп и на сервер как строки {@code name_tag}.
 *
 * <p>⚠️ Точка на каждой версии одна, и она ЗАМЕРЕНА по байткоду: {@code getNameTag}
 * зовётся ровно один раз — в 26.2 внутри
 * {@code extractNameTags(Entity, EntityRenderState, float, double, double)},
 * а в 26.1.x и 1.21.11 — прямо в {@code extractRenderState(Entity,
 * EntityRenderState, float)}; метода {@code extractNameTags} там нет вовсе.
 * Переопределяет {@code getNameTag} только {@code ItemFrameRenderer}, и его
 * результат идёт через тот же вызов.
 *
 * <p>⚠️⚠️ ПОЭТОМУ ЦЕЛЕЙ ДВЕ, и это не перестраховка. Jar для 26.x один на
 * 26.1–26.2, а 17.09 цель указали только для 26.2 — 11.10 игра на 26.1.2
 * (сборка SkyBlock Enhanced) упала на старте: «could not find any targets
 * matching 'extractNameTags…'». Отсутствующий в версии метод Mixin просто
 * пропускает: минимум совпадений у селектора по умолчанию 0 (проверено по
 * байткоду sponge-mixin 0.17.3, {@code Quantifier.DEFAULT}), а падает он,
 * только если не нашлось НИ ОДНОГО метода. Вызов при этом есть ровно в одном
 * месте на каждой версии, так что перевод не удвоится.
 * Дескриптор полный: у {@code extractNameTags} в 26.2 два перегруженных
 * варианта, и вызов есть только в пятиаргументном. Сторожит
 * {@code check_mixin_gate} — по байткоду КАЖДОЙ версии, на которую рассчитан jar.
 */
@Mixin(EntityRenderer.class)
public abstract class EntityRendererMixin {

	@ModifyExpressionValue(
			method = {
					"extractNameTags(Lnet/minecraft/world/entity/Entity;Lnet/minecraft/client/renderer/entity/state/EntityRenderState;FDD)V",
					"extractRenderState(Lnet/minecraft/world/entity/Entity;Lnet/minecraft/client/renderer/entity/state/EntityRenderState;F)V"
			},
			at = @At(value = "INVOKE",
					target = "Lnet/minecraft/client/renderer/entity/EntityRenderer;"
							+ "getNameTag(Lnet/minecraft/world/entity/Entity;)"
							+ "Lnet/minecraft/network/chat/Component;"))
	private Component skyblockru$nameTag(Component shown, @Local(argsOnly = true) Entity entity) {
		if (shown == null || entity == null || !entity.hasCustomName()) {
			return shown;
		}
		if (!RuConfig.get().enabled || !RuConfig.get().targets.nameTag) {
			return shown;
		}
		Component translated = TextTranslator.translate(shown, TextTranslator.SRC_NAME_TAG);
		return translated == null ? shown : translated;
	}
}
