package ru.skyblockru.core;

/**
 * Подмена заголовка экрана на время отрисовки — и возврат оригинала после.
 *
 * <p>⚠️ ЗАЧЕМ ОТДЕЛЬНЫЙ ИНТЕРФЕЙС, а не просто {@code @Shadow} поля. Поле
 * {@code title} объявлено в {@code Screen}, а перехватывать надо
 * {@code AbstractContainerScreen.extractLabels} — там рисуется заголовок
 * контейнера. Mixin ищет теневое поле ТОЛЬКО в самом целевом классе и
 * в суперкласс не заглядывает; попытка обошлась крашем при запуске:
 * <pre>
 *   InvalidMixinException: @Shadow field title was not located in the target
 *   class net.minecraft.client.gui.screens.inventory.AbstractContainerScreen
 * </pre>
 * Поэтому доступ к полю живёт в миксине на {@code Screen} (он его видит),
 * а контейнерный миксин зовёт его отсюда приведением {@code (TitleSwap) this}.
 *
 * <p>⚠️ Компиляция такого не ловит по построению — цель и поле у Mixin
 * разрешаются при ЗАГРУЗКЕ класса. Сторожит запуск игры, а из проверок —
 * {@code tools/check_mixin_gate.py} (цели) и {@code check_neighbours.py}
 * (возврат поля к оригиналу).
 */
public interface TitleSwap {

	/** Поставить перевод в поле заголовка — только на время отрисовки. */
	void skyblockru$showTranslatedTitle();

	/** Вернуть в поле оригинал Hypixel: его читают соседние моды. */
	void skyblockru$restoreOriginalTitle();
}
