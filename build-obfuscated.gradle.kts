// ⚠️ Импорты обязательны: в build-скрипте имя `java` занято расширением
// Gradle, поэтому `java.text.SimpleDateFormat` не разрешается.
import java.text.SimpleDateFormat
import java.util.Date

// Сборка для ОБФУСЦИРОВАННЫХ версий (1.21.11 и старше).
//
// ⚠️ Здесь плагин `net.fabricmc.fabric-loom-remap` — тот же Loom, но вариант,
// который умеет разбирать обфусцированную игру. Отличия от 26.x-скрипта
// не косметические, а обязательные (docs.fabricmc.net/develop/loom):
//   * нужны `mappings` — иначе имена классов останутся вида `aad`;
//   * зависимости-моды идут через `modImplementation`: Loom их ремапит
//     под наши маппинги. С обычным `implementation` сборка падает на
//     access-widener'ах Fabric API;
//   * готовый jar собирает `remapJar`, а не `jar`.
//
// ⚠️ Маппинги ОФИЦИАЛЬНЫЕ Mojang, а не Yarn. Замер 02.08: с Yarn код давал
// 200 ошибок компиляции (у него свои имена для всего), с mojmap — 70, потому
// что имена совпадают с теми, под которые написан мод.
plugins {
    id("net.fabricmc.fabric-loom-remap")
}

val mcVersion: String = stonecutter.current.version

// ⚠️ Версии взяты у самого maven.fabricmc.net (последняя под каждую игру),
// а не по памяти: у каждой версии Minecraft свой Fabric API, и «примерно
// подходящий» не годится — на этом игрок уже спотыкался дважды, кладя
// в инстанс API от соседней версии.
val fabricApiVersion: String = when (mcVersion) {
    "1.21.11" -> "0.141.6+1.21.11"
    "1.21.10" -> "0.138.4+1.21.10"
    "1.21.9" -> "0.134.1+1.21.9"
    "1.21.8" -> "0.136.1+1.21.8"
    "1.21.7" -> "0.129.0+1.21.7"
    "1.21.6" -> "0.128.2+1.21.6"
    "1.21.5" -> "0.128.2+1.21.5"
    "1.21.4" -> "0.119.4+1.21.4"
    "1.21.3" -> "0.114.1+1.21.3"
    "1.21.2" -> "0.106.1+1.21.2"
    "1.21.1" -> "0.116.15+1.21.1"
    "1.21" -> "0.102.0+1.21"
    else -> error("не знаю версию Fabric API для $mcVersion — допиши сюда")
}

// ⚠️ 1.21.x работает на Java 21, а 26.x — на 25. Соберёшь классы под 25 —
// игра их просто не загрузит.
val javaVersion = 21

version = "${property("mod_version")}+$mcVersion"
group = property("maven_group")!!

base {
    archivesName.set(property("archives_base_name") as String)
}

repositories {
    mavenCentral()
    maven("https://repo.hypixel.net/repository/Hypixel/") { name = "Hypixel" }
}

dependencies {
    minecraft("com.mojang:minecraft:$mcVersion")
    mappings(loom.officialMojangMappings())

    modImplementation("net.fabricmc:fabric-loader:${property("loader_version")}")
    modImplementation("net.fabricmc.fabric-api:fabric-api:$fabricApiVersion")

    // ⚠️ НЕ вкладываем: наша копия библиотеки перебивала ту, под которую
    // собран сторонний `hypixel-mod-api`, и его падение роняло всю игру.
    // Подробности — в build-unobfuscated.gradle.kts и в граблях CLAUDE.md.
    compileOnly("net.hypixel:mod-api:${property("hypixel_modapi_version")}")
}

tasks.processResources {
    exclude("**/*.bak*", "**/*.orig*", "**/*.rej*", "**/*.tmp*", "**/*~", "**/*.old*", "**/*.save*")

    // ⚠️ РАСШИРЕННЫЙ ПЕРЕВОД ОТЛОЖЕН (решение игрока 03.08) — эти словари
    // в jar не едут. Они остаются в репозитории: инструменты читают файлы
    // напрямую и считают их «переводить не надо», иначе те же 3417 записей
    // ушли бы в платную очередь заново (записанная грабля про «Огранку V»).
    // Вернуть работу = убрать отсюда И вписать имя обратно в packs/index.json.
    exclude("**/80-vanilla-names.json", "**/77-sb-enchants.json", "**/78-sb-stats.json")

    val modVersion = version.toString()
    val buildTime = SimpleDateFormat("dd.MM.yyyy HH:mm").format(Date())
    inputs.property("version", modVersion)
    inputs.property("buildTime", buildTime)

    // ⚠️ Диапазон версий игры — РОВНО та версия, под которую собрано.
    //
    // Соблазн написать «>=1.21» велик, и он неверен: замер 02.08 показал, что
    // ветка 1.21.x НЕ однородна — 1.21 и 1.21.5 не компилируются тем же кодом,
    // что 1.21.11 (разные `Identifier`/`ResourceLocation`, `KeyMapping.Category`,
    // методы NBT). Широкий диапазон значил бы, что мод грузится на версии,
    // под которую не собирался, и падает уже в игре.
    // Появится проверенная соседняя версия — расширять диапазон осознанно.
    filesMatching("fabric.mod.json") {
        expand(
            "version" to modVersion,
            "build_time" to buildTime,
            "minecraft_range" to mcVersion,
            "java_version" to javaVersion.toString(),
        )
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(javaVersion)
    options.encoding = "UTF-8"
}

java {
    sourceCompatibility = JavaVersion.toVersion(javaVersion)
    targetCompatibility = JavaVersion.toVersion(javaVersion)
}

tasks.jar {
    from("LICENSE") { rename { "${it}_${base.archivesName.get()}" } }
}
