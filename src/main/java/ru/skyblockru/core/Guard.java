package ru.skyblockru.core;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;

/**
 * Ограда вокруг нашего кода в ЧУЖИХ точках перехвата.
 *
 * <p>Зачем. Подсказку предмета строит {@code ItemStack.getTooltipLines}, и на
 * ней висят события, которые слушаем не только мы: REI, JEI, Skyblocker, NEU.
 * Если наш перевод бросит исключение, оно уйдёт вверх через Fabric, и метод
 * упадёт ЦЕЛИКОМ — подсказка не покажется ни у нас, ни у соседей, а игрок
 * увидит поломку и решит, что виноват последний поставленный мод. Пока мод
 * стоял один у одного игрока, цена такой ошибки была «у меня не работает»;
 * с раздачей другим людям она становится «ваш мод ломает мою сборку».
 *
 * <p>⚠️ Это НЕ глушилка багов, и разница принципиальна. Молча проглоченное
 * исключение — способ потерять поломку навсегда: в этом проекте уже были
 * беды, которые жили месяцами именно потому, что никто не жаловался
 * (потолок сбора, обнулённый словарь). Поэтому:
 * <ul>
 *   <li>ПЕРВЫЙ сбой в каждом месте пишется в лог полностью, со стеком;</li>
 *   <li>дальше по этому месту только счётчик — иначе лог забьётся за минуту
 *       (подсказка строится десятки раз в секунду);</li>
 *   <li>счётчики видны в {@code /skyblockru diag}, то есть беда остаётся
 *       ЗАМЕТНОЙ, просто перестаёт быть разрушительной.</li>
 * </ul>
 *
 * <p>⚠️ Ловим {@link Throwable}, а не только {@link RuntimeException}. Чужая
 * сборка приносит чужие версии библиотек, и типичный отказ там —
 * {@code NoSuchMethodError} или {@code NoClassDefFoundError}, то есть
 * {@link LinkageError}. Именно они и означают «мод собран под другое», и
 * именно их важнее всего пережить. {@link Error} про исчерпание ресурсов
 * ({@link OutOfMemoryError}, {@link StackOverflowError}) пробрасываем дальше:
 * их глушить нельзя, они говорят о состоянии всей игры, а не о нашем промахе.
 */
public final class Guard {

	private Guard() {
	}

	/** Сколько раз упало каждое место. Видно в {@code /skyblockru diag}. */
	private static final Map<String, AtomicInteger> FAILURES = new ConcurrentHashMap<>();

	/** Тело перехвата, которое может бросить. */
	@FunctionalInterface
	public interface Body {
		void run() throws Throwable;
	}

	/**
	 * Выполнить наш код так, чтобы его поломка не унесла чужую подсказку.
	 *
	 * @param where короткое имя места — оно попадёт в лог и в диагностику
	 * @param body  что делаем
	 * @return true, если отработало без сбоя
	 */
	public static boolean run(String where, Body body) {
		try {
			body.run();
			return true;
		} catch (OutOfMemoryError | StackOverflowError fatal) {
			// Не наша беда и не наше дело — это состояние всей игры.
			throw fatal;
		} catch (Throwable failure) {
			note(where, failure);
			return false;
		}
	}

	/**
	 * То же, но для кода, который что-то возвращает. При сбое отдаётся
	 * {@code fallback} — как правило, исходное значение без перевода.
	 */
	public static <T> T get(String where, java.util.concurrent.Callable<T> body, T fallback) {
		try {
			return body.call();
		} catch (OutOfMemoryError | StackOverflowError fatal) {
			throw fatal;
		} catch (Throwable failure) {
			note(where, failure);
			return fallback;
		}
	}

	/**
	 * ⚠️ Логгер СВОЙ, а не {@code SkyblockRuClient.LOG}, и это не мелочь:
	 * тот класс тянет за собой Minecraft, и тогда ограду нельзя было бы
	 * прогнать без игры. Здесь зависимость только от slf4j — значит
	 * {@code tools/check_guard.py} проверяет её настоящей Java, как
	 * {@code ColorLayout} и {@code ParagraphColors}. Защита, которую нечем
	 * проверить, — это ещё одно место, где поломка живёт молча.
	 */
	private static final org.slf4j.Logger LOG =
			org.slf4j.LoggerFactory.getLogger("SkyblockRU");

	private static void note(String where, Throwable failure) {
		AtomicInteger count = FAILURES.computeIfAbsent(where, key -> new AtomicInteger());
		int seen = count.incrementAndGet();
		if (seen == 1) {
			// ⚠️ Полный стек — ровно один раз на место. Логи читает разработчик,
			// и по-английски: отчёт на незнакомом языке хуже английского.
			LOG.error("[skyblockru] failed in {} — translation skipped here, "
					+ "the tooltip is shown untranslated. Further failures "
					+ "in this spot are counted silently (see /skyblockru diag).",
					where, failure);
		}
	}

	/** Только для проверок: забыть накопленные счётчики. */
	public static void reset() {
		FAILURES.clear();
	}

	/** Сводка для {@code /skyblockru diag}: где и сколько раз мы упали. */
	public static Map<String, Integer> failures() {
		Map<String, Integer> out = new java.util.TreeMap<>();
		FAILURES.forEach((where, count) -> out.put(where, count.get()));
		return out;
	}

	/** Всего сбоев — для короткой строки в {@code /skyblockru}. */
	public static int total() {
		int sum = 0;
		for (AtomicInteger count : FAILURES.values()) {
			sum += count.get();
		}
		return sum;
	}
}
