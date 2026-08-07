// ⚠️ Импорты обязательны: в build-скрипте имя `java` занято расширением
// Gradle, поэтому `java.text.SimpleDateFormat` не разрешается.
import java.text.SimpleDateFormat
import java.util.Date

// Сборка для НЕобфусцированных версий (26.1+).
//
// ⚠️ Здесь плагин `net.fabricmc.fabric-loom`: он НИЧЕГО не ремапит, потому что
// с 26.1 Minecraft поставляется необфусцированным. Отсюда особенности, которые
// выглядят странно рядом с обычными гайдами по Fabric:
//   * зависимости берутся через `implementation`, а не `modImplementation`;
//   * строки `mappings` нет вовсе;
//   * задача сборки — `jar`, а не `remapJar`.
// Для старых версий всё наоборот — см. build-obfuscated.gradle.kts.
plugins {
    id("net.fabricmc.fabric-loom")
}

val mcVersion: String = stonecutter.current.version

// Версии Fabric API держим здесь, а не в gradle.properties: свойство одно
// на весь проект, а версий сборки теперь несколько.
val fabricApiVersion: String = when (mcVersion) {
    "26.2" -> "0.155.2+26.2"
    "26.1" -> "0.155.2+26.1.2"
    else -> error("не знаю версию Fabric API для $mcVersion — допиши сюда")
}

version = "${property("mod_version")}+$mcVersion"
group = property("maven_group")!!

base {
    archivesName.set(property("archives_base_name") as String)
}

repositories {
    mavenCentral()
    // Официальная библиотека Hypixel Mod API. Своей реализации протокола
    // не пишем намеренно: FAQ Hypixel не советует их из-за рейт-лимитов
    // и согласования версий пакетов.
    maven("https://repo.hypixel.net/repository/Hypixel/") { name = "Hypixel" }
}

dependencies {
    minecraft("com.mojang:minecraft:$mcVersion")
    implementation("net.fabricmc:fabric-loader:${property("loader_version")}")
    implementation("net.fabricmc.fabric-api:fabric-api:$fabricApiVersion")

    // ⚠️ Библиотека ЧИСТО JAVA: она умеет только собирать и разбирать пакеты,
    // а сеть не трогает вовсе — транспорт пишем сами (core/HypixelApi.java).
    //
    // ⚠️⚠️ ВКЛАДЫВАТЬ ЕЁ НЕЛЬЗЯ — так мы ломали чужие сборки НАСМЕРТЬ.
    // Было `include(...)`, и Fabric раздавал нашу 1.0.2 всем: мод-обёртка
    // `hypixel-mod-api 1.0.1` из сборки игрока собрана под 1.0.1, звала
    // `setPacketSender(Predicate)` — метод, которого в 1.0.2 больше нет, —
    // и игра не запускалась вовсе (NoSuchMethodError на старте).
    // Библиотеку обязан поставлять мод-обёртка, а не мы: у неё обе половины
    // согласованы по построению.
    // Отсюда compileOnly: собираемся против неё, но в jar не кладём и в
    // рантайме её отсутствие переживаем (SkyblockRuClient ловит Throwable,
    // режим определяется заголовком панели, как до появления Mod API).
    compileOnly("net.hypixel:mod-api:${property("hypixel_modapi_version")}")
}

tasks.processResources {
    // ⚠️ Loom кладёт в jar ВСЁ из resources, поэтому ручная копия словаря,
    // снятая перед правкой, уезжает игрокам. Так в jar полгода лежал
    // packs/index.json.bak — устаревший на три словаря, но настоящий с виду.
    // Запрещаем не привычку, а попадание в jar.
    exclude("**/*.bak*", "**/*.orig*", "**/*.rej*", "**/*.tmp*", "**/*~", "**/*.old*", "**/*.save*")

    // ⚠️ РАСШИРЕННЫЙ ПЕРЕВОД ОТЛОЖЕН (решение игрока 03.08) — эти словари
    // в jar не едут. Они остаются в репозитории: инструменты читают файлы
    // напрямую и считают их «переводить не надо», иначе те же 3417 записей
    // ушли бы в платную очередь заново (записанная грабля про «Огранку V»).
    // Вернуть работу = убрать отсюда И вписать имя обратно в packs/index.json.
    exclude("**/80-vanilla-names.json", "**/77-sb-enchants.json", "**/78-sb-stats.json")

    val modVersion = version.toString()
    // Время сборки видно в игре по /skyblockru — иначе не понять, запущена
    // свежая сборка или та, что была до правки. На этом уже спотыкались дважды.
    val buildTime = SimpleDateFormat("dd.MM.yyyy HH:mm").format(Date())
    inputs.property("version", modVersion)
    inputs.property("buildTime", buildTime)

    // ⚠️ ДИАПАЗОН ВЕРСИЙ ИГРЫ ПОДСТАВЛЯЕТСЯ, а не лежит в файле строкой.
    //
    // Пока сборка была одна, `">=26.1 <26.3"` в fabric.mod.json было верно
    // всегда. Со Stonecutter сборок несколько, и статическая строка означала
    // бы, что jar для 1.21.11 объявляет себя модом для 26.x — Fabric Loader
    // отказывается его грузить: «requires any version between 26.1 and 26.3,
    // but only the wrong version is present: 1.21.11». Компиляция такого
    // не ловит по построению: метаданные она не читает.
    filesMatching("fabric.mod.json") {
        expand(
            "version" to modVersion,
            "build_time" to buildTime,
            // 26.1 и 26.2 проверены одним jar — классы побайтово совпадают
            "minecraft_range" to ">=26.1 <26.3",
            "java_version" to "25",
        )
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(25)
    options.encoding = "UTF-8"
}

java {
    sourceCompatibility = JavaVersion.VERSION_25
    targetCompatibility = JavaVersion.VERSION_25
}

tasks.jar {
    from("LICENSE") { rename { "${it}_${base.archivesName.get()}" } }
}
