pluginManagement {
    repositories {
        maven("https://maven.fabricmc.net/")
        maven("https://maven.kikugie.dev/releases")
        maven("https://maven.kikugie.dev/snapshots")
        mavenCentral()
        gradlePluginPortal()
    }
    // Версии плагинов Loom задаём здесь, чтобы build-скрипты применяли их
    // без версии — иначе пришлось бы держать номер в двух местах.
    plugins {
        id("net.fabricmc.fabric-loom") version "1.17-SNAPSHOT"
    }
}

plugins {
    id("dev.kikugie.stonecutter") version "0.9.7"
}

// ⚠️ ВСЕ ВЕРСИИ — НЕОБФУСЦИРОВАННЫЕ (26.1+), плагин Loom один.
//
// docs.fabricmc.net/develop/loom:
//   net.fabricmc.fabric-loom        — 26.1+, НЕобфусцированные, ремапа нет вовсе
//   net.fabricmc.fabric-loom-remap  — 1.21.11 и старше, обфусцированные
//
// Второй плагин и build-obfuscated.gradle.kts жили ради 1.21.11 и сняты
// вместе с ней 11.10.2026 (копия скрипта — notes/archive/). Вернётся
// обфусцированная версия — возвращать и плагин, и выбор скрипта ниже.
stonecutter {
    kotlinController = true
    shared {
        // ⚠️ Список версий в вызове ниже читают по шаблону tools/build_all.py
        // и tools/check_mixin_gate.py — форму вызова не менять, а в комментариях
        // не писать образец вызова с кавычками: шаблон найдёт его первым.
        fun mc(vararg versions: String) {
            for (version in versions) {
                version(version, version).buildscript("build-unobfuscated.gradle.kts")
            }
        }
        // ⚠️ Порядок важен: ПОСЛЕДНЯЯ становится активной по умолчанию.
        // 26.2 — основная версия игрока, её и держим активной.
        //
        // ⚠️⚠️ ЗДЕСЬ ТОЛЬКО ТО, КУДА HYPIXEL ПУСКАЕТ В SKYBLOCK. Планка
        // у сервера ползёт вверх сама: правило Hypixel — «последние два
        // контент-обновления», то есть список СТАРЕЕТ БЕЗ НАС.
        //
        // ⚠️ 1.21.11 СНЯТА 11.10.2026: с выходом 26.3 SkyBlock на ней больше
        // не работает (со слов игрока), а мод там больше не обновляем — решение
        // игрока. Вместе с ней ушла последняя обфусцированная версия:
        // build-obfuscated.gradle.kts и ветки `< 26.1` в коде больше не нужны.
        //
        // ⚠️ Правило прежнее: версия попадает сюда, только когда РЕАЛЬНО
        // собралась. Недоделанная цель красит `gradlew build` в красный
        // навсегда и приучает не смотреть на красное.
        mc("26.3", "26.2")
    }
    create(rootProject)
}

rootProject.name = "SkyblockRU"
