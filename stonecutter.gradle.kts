// Контроллер Stonecutter: какая версия сейчас активна и чем версии отличаются.
//
// ⚠️ Строку `stonecutter active` НЕ править руками — её переписывает сам
// Stonecutter командой `gradlew "Set active project to <версия>"`.
plugins {
    id("dev.kikugie.stonecutter")
}
stonecutter active "26.2" /* [SC] DO NOT EDIT */

// ⚠️ Различия между поколениями Minecraft — ЗАМЕНАМИ, а не ветками кода.
//
// Замер 02.08: под 1.21.11 мод дал 70 ошибок компиляции, и все они сводятся
// к ВОСЬМИ переименованиям. Держать под них `if (версия)` в коде было бы
// худшим решением: правку пришлось бы дублировать, и однажды забыть.
// Stonecutter меняет имена сам при переключении версии, а исходник остаётся
// один.
//
// Направление: `direction = eval(...)` значит «в этих версиях — правая форма».
// То есть слева пишем имя для СТАРЫХ версий, справа — для 26.1+.
// ⚠️ Имена взяты из ОФИЦИАЛЬНОЙ страницы «Porting to Fabric API 26.1»
// (docs.fabricmc.net/develop/porting/fabric-api) и сверены с деревом
// исходников Fabric API по тегу 1.21.11 — не по памяти. Слева форма СТАРЫХ
// версий, справа — 26.1+; направление задаёт `direction`.
stonecutter parameters {
    replacements {
        // --- Fabric API: переезд на официальные маппинги Mojang в 26.1 ---
        string {
            direction = eval(current.version, ">=26.1")
            replace("keybinding.v1.KeyBindingHelper", "keymapping.v1.KeyMappingHelper")
        }
        string {
            direction = eval(current.version, ">=26.1")
            replace("KeyBindingHelper", "KeyMappingHelper")
        }
        string {
            direction = eval(current.version, ">=26.1")
            replace("ClientCommandManager", "ClientCommands")
        }
        string {
            direction = eval(current.version, ">=26.1")
            replace("C2SPlayChannelEvents", "ServerboundPlayChannelEvents")
        }
        string {
            direction = eval(current.version, ">=26.1")
            replace("playS2C(", "clientboundPlay(")
        }
        string {
            direction = eval(current.version, ">=26.1")
            replace("playC2S(", "serverboundPlay(")
        }

        string {
            direction = eval(current.version, ">=26.1")
            replace("registerKeyBinding", "registerKeyMapping")
        }

        // --- рендер: в 26.x состояние сперва извлекают, потом рисуют ---
        string {
            direction = eval(current.version, ">=26.1")
            replace("GuiGraphics", "GuiGraphicsExtractor")
        }
        string {
            direction = eval(current.version, ">=26.1")
            replace("renderTooltip(", "tooltip(")
        }

        // --- Mojang переименовал ResourceLocation -> Identifier ---
        //
        // ⚠️ Порог ЗАМЕРЕН, а не взят из головы: 1.21.10 не собирается
        // с `Identifier` (6 ошибок, все про этот класс), 1.21.11 собирается.
        // Значит переименование пришло ровно в 1.21.11.
        //
        // ⚠️ ЗАМЕНЯТЬ ГОЛОЕ СЛОВО НЕЛЬЗЯ — проверено, ломается сборка.
        // Первая попытка меняла «Identifier» везде и задела ЧУЖУЮ библиотеку:
        // `getClientboundIdentifiers()` из Hypixel Mod API превратилось
        // в `getClientboundResourceLocations()`, которого там нет. Имя метода
        // чужого API от версии Minecraft не зависит и трогать его нельзя.
        // Поэтому заменяем ровно три формы, в которых стоит КЛАСС.
        string {
            direction = eval(current.version, ">=1.21.11")
            replace("net.minecraft.resources.ResourceLocation", "net.minecraft.resources.Identifier")
        }
        string {
            direction = eval(current.version, ">=1.21.11")
            replace("ResourceLocation.", "Identifier.")
        }
        string {
            direction = eval(current.version, ">=1.21.11")
            replace("ResourceLocation ", "Identifier ")
        }

        // --- ЦЕЛИ МИКСИНОВ: имя метода внутри @Inject — СТРОКА ---
        //
        // ⚠️ Компиляция их не проверяет ВООБЩЕ, и это уже стоило падения игры
        // на 1.21.11: сборка прошла с нулём ошибок, а Mixin при запуске
        // не нашёл цель — «could not find any targets matching 'extractTooltip'».
        // Замены ниже идут ПО СТРОКЕ В КАВЫЧКАХ, чтобы не задеть обычные
        // вызовы: `renderTooltip(` у GuiGraphics — это другое, оно выше.
        string {
            direction = eval(current.version, ">=26.1")
            replace("\"renderTooltip\"", "\"extractTooltip\"")
        }
        string {
            direction = eval(current.version, ">=26.1")
            replace("\"render\"", "\"extractRenderState\"")
        }
    }
}
