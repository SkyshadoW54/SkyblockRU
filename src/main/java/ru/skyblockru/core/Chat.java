package ru.skyblockru.core;

import net.minecraft.client.player.LocalPlayer;
import net.minecraft.network.chat.Component;

/**
 * Сообщение игроку в чат — ОДНО место на все версии игры.
 *
 * <p>⚠️ Зачем отдельный класс ради одной строки. Метод отправки — единственное
 * различие между поколениями, которое НЕ ЛЕЧИТСЯ переименованием: у него разная
 * сигнатура, а не имя.
 *
 * <pre>
 *   26.1+      player.sendSystemMessage(Component)
 *   1.21.x     player.displayClientMessage(Component, boolean)
 * </pre>
 *
 * <p>Общего метода нет ни в одной из версий — проверено javap по обеим. Значит
 * нужна условная компиляция, а её лучше держать в ОДНОЙ точке: иначе правка
 * чата разъехалась бы по трём файлам, и однажды кто-то поправил бы две из трёх.
 * Тот же довод, по которому тело перехвата надписей вынесено в OverlayHooks.
 */
public final class Chat {

	private Chat() {
	}

	/** Написать игроку в чат. Второй аргумент старого API — «не в полосу над хотбаром». */
	public static void tell(LocalPlayer player, Component message) {
		//? if >=26.1 {
		player.sendSystemMessage(message);
		//?} else
		/*player.displayClientMessage(message, false);*/
	}
}
