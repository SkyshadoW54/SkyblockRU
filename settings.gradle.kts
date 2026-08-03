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
        id("net.fabricmc.fabric-loom-remap") version "1.17-SNAPSHOT"
    }
}

plugins {
    id("dev.kikugie.stonecutter") version "0.9.7"
}

// ⚠️ ДВА ПОКОЛЕНИЯ MINECRAFT — ДВА РАЗНЫХ ПЛАГИНА LOOM, и это официально.
//
// docs.fabricmc.net/develop/loom:
//   net.fabricmc.fabric-loom        — 26.1+, НЕобфусцированные, ремапа нет вовсе
//   net.fabricmc.fabric-loom-remap  — 1.21.11 и старше, обфусцированные
//
// Отсюда и разные build-скрипты: в новом плагине нет ни `mappings`, ни
// `modImplementation` не потому, что «API поменялся», а потому что ремапить
// нечего. Полдня перебора версий Loom стоило того, что это не было прочитано
// сразу — см. CLAUDE.md, раздел про порт.
stonecutter {
    kotlinController = true
    shared {
        fun mc(vararg versions: String) {
            for (version in versions) {
                val script = if (eval(version, ">=26.1")) {
                    "build-unobfuscated.gradle.kts"
                } else {
                    "build-obfuscated.gradle.kts"
                }
                version(version, version).buildscript(script)
            }
        }
        // ⚠️ Порядок важен: ПОСЛЕДНЯЯ становится активной по умолчанию.
        // 26.2 — основная версия игрока, её и держим активной.
        //
        // ⚠️⚠️ ЗДЕСЬ ТОЛЬКО ТО, КУДА HYPIXEL ПУСКАЕТ В SKYBLOCK. Сервер
        // говорит это прямым текстом, и планка у него ползёт вверх сама:
        //     «You must be using Minecraft Version 1.21.11 or later
        //      to play SkyBlock!»
        // 1.21.9 и 1.21.10 сняты 08.07.2026 вместе с релизом SkyBlock 0.26,
        // 1.21–1.21.8 сеть не пускает вовсе. Правило Hypixel — «последние
        // два контент-обновления», то есть список СТАРЕЕТ БЕЗ НАС.
        //
        // ⚠️ ДВЕ сборки покрывают ЧЕТЫРЕ версии игры: у 26.x диапазон
        // `>=26.1 <26.3`, один jar идёт на 26.1, 26.1.1, 26.1.2 и 26.2
        // (проверено: классы побайтово одинаковы). У 1.21.11 диапазон
        // РОВНО свой — ветка 1.21 неоднородна, широкий диапазон значил бы,
        // что мод грузится там, где не собирался.
        //
        // ⚠️ Ветка 1.21.0–1.21.10 БЫЛА доведена до зелёной сборки 03.08,
        // и Stonecutter-условия под неё ОСТАЛИСЬ в коде — вернуть версию
        // можно одной строкой здесь. Убрана она не потому, что не собирается,
        // а потому, что собранный под неё jar не может подключиться
        // к серверу: раздавать его — значит выдавать игроку отказ Hypixel
        // за поломку мода. Подробности и цена ошибки — в CLAUDE.md.
        //
        // ⚠️ Правило прежнее: версия попадает сюда, только когда РЕАЛЬНО
        // собралась. Недоделанная цель красит `gradlew build` в красный
        // навсегда и приучает не смотреть на красное.
        mc("1.21.11", "26.2")
    }
    create(rootProject)
}

rootProject.name = "SkyblockRU"
