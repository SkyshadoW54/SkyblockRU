# -*- coding: utf-8 -*-
"""
Имя говорящего в реплике NPC: русское в режиме, английское без него.

    python tools/check_npc_prefix.py

⚠️ ЗАЧЕМ. Реплики переведены ЦЕЛИКОМ (9322 записи), имя в них английское,
и в полном режиме оно подменяется УЖЕ В ГОТОВОМ ПЕРЕВОДЕ (`core/NpcPrefix`).
Копия словаря с русскими именами весила бы +1.7 МБ и уехала бы всем.

⚠️ ОБА КРАЯ ОБЯЗАТЕЛЬНЫ, и второй важнее первого:
  * в РЕЖИМЕ имя обязано стать русским — иначе механика мертва;
  * БЕЗ режима имя обязано остаться английским — иначе мы нарушили решение
    проекта и сломали поиск по гайдам у всех, кто режим не включал;
  * в ТЕЛЕ реплики имя НЕ ТРОГАЕМ — там нужен падеж, а он машинно
    не выводится. Подмена в теле дала бы «расскажи Кэт» в позиции, где
    именительный неверен.
"""
import io
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
CLASSES = ROOT / "versions" / "26.2" / "build" / "classes" / "java" / "main"
RESOURCES = ROOT / "src" / "main" / "resources"

JAVA_SRC = r'''
import ru.skyblockru.core.NpcPrefix;

public class NpcPrefixRun {
    static int bad = 0;

    static void check(String what, boolean ok) {
        System.out.println((ok ? "  [ok]   " : "  [СЛОМАНО] ") + what);
        if (!ok) bad++;
    }

    public static void main(String[] args) {
        // разбор подписи
        check("имя из «[NPC] Kat: привет»",
                "Kat".equals(NpcPrefix.speakerOf("[NPC] Kat: hello")));
        check("имя из реплики с рангом мэра",
                "Mayor Cole".equals(NpcPrefix.speakerOf("[NPC] Mayor Cole: hi")));
        check("обычная строка подписи не даёт",
                NpcPrefix.speakerOf("You bought Gold Ore for 10 coins!") == null);
        check("двоеточие без метки [NPC] не считается",
                NpcPrefix.speakerOf("Purse: 1,000") == null);

        // подмена
        java.util.function.UnaryOperator<String> ru = name ->
                "Kat".equals(name) ? "Кэт" : null;

        check("в режиме имя стало русским",
                "[NPC] Кэт: Привет!".equals(
                        NpcPrefix.apply("[NPC] Kat: Hi!", "[NPC] Kat: Привет!", ru)));

        check("перевода имени нет — не трогаем",
                "[NPC] Ike: Привет!".equals(
                        NpcPrefix.apply("[NPC] Ike: Hi!", "[NPC] Ike: Привет!", ru)));

        // ⚠️ ГЛАВНЫЙ ОБРАТНЫЙ КРАЙ: имя в ТЕЛЕ реплики остаётся как было —
        // там нужен падеж, а подпись стоит в именительном.
        check("имя в ТЕЛЕ реплики не трогаем",
                "[NPC] Кэт: Поговори с Kat позже.".equals(
                        NpcPrefix.apply("[NPC] Kat: Talk to Kat later.",
                                "[NPC] Kat: Поговори с Kat позже.", ru)));

        // §-коды перевода не мешают
        check("имя меняется и под §-кодами",
                "§e[NPC] §cКэт§f: Привет!".equals(
                        NpcPrefix.apply("[NPC] Kat: Hi!", "§e[NPC] §cKat§f: Привет!", ru)));

        // ⚠️ ГЛАВНЫЙ СЛУЧАЙ, НА КОТОРОМ МЕХАНИКА СПОТКНУЛАСЬ: Hypixel красит
        // куски имени по отдельности, и §-код встаёт ПОСРЕДИ имени.
        // Дословный поиск его не находил — «Melody ♫» осталась английской.
        java.util.function.UnaryOperator<String> mel = name ->
                "Melody ♫".equals(name) ? "Мелоди ♫" : null;
        check("код ВНУТРИ имени не мешает",
                "§e[NPC] Мелоди ♫§f: Привет!".equals(
                        NpcPrefix.apply("[NPC] Melody ♫: Hi!",
                                "§e[NPC] Melody §d♫§f: Привет!", mel)));

        check("не реплика — перевод не меняется",
                "Кошелёк: 1,000".equals(
                        NpcPrefix.apply("Purse: 1,000", "Кошелёк: 1,000", ru)));

        check("пустой перевод имени не применяется",
                "[NPC] Kat: Привет!".equals(
                        NpcPrefix.apply("[NPC] Kat: Hi!", "[NPC] Kat: Привет!",
                                name -> "  ")));

        System.out.println(bad == 0
                ? "\nСЛОМАНО: 0 — подпись говорящего ведёт себя как задумано"
                : "\nСЛОМАНО: " + bad);
        System.exit(bad == 0 ? 0 : 1);
    }
}
'''


def classpath() -> list[str] | None:
    import check_click_events as helper
    return helper.classpath()


def main() -> int:
    cp = classpath()
    if cp is None:
        print("нет классов игры — сперва сборка")
        return 0
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        (tmp / "NpcPrefixRun.java").write_text(JAVA_SRC, encoding="utf-8")
        full = [str(CLASSES), str(RESOURCES), *cp]
        sep = ";" if sys.platform == "win32" else ":"
        rc = subprocess.run(
            ["javac", "-encoding", "UTF-8", "-cp", sep.join(full),
             "-d", str(tmp), str(tmp / "NpcPrefixRun.java")],
            capture_output=True, text=True)
        if rc.returncode != 0:
            print(rc.stderr[-2000:])
            return 1
        rc = subprocess.run(
            ["java", "-Dstdout.encoding=UTF-8", "-cp", sep.join([str(tmp), *full]),
             "NpcPrefixRun"],
            capture_output=True, text=True, encoding="utf-8")
        print(rc.stdout)
        if rc.stderr.strip():
            print(rc.stderr[-500:])
        return rc.returncode


if __name__ == "__main__":
    sys.exit(main())
