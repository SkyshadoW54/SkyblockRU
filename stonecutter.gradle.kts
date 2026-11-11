// Контроллер Stonecutter: какая версия сейчас активна и чем версии отличаются.
//
// ⚠️ Строку `stonecutter active` НЕ править руками — её переписывает сам
// Stonecutter командой `gradlew "Set active project to <версия>"`.
plugins {
    id("dev.kikugie.stonecutter")
}
stonecutter active "26.2" /* [SC] DO NOT EDIT */

// ⚠️ ЗАМЕН ИМЁН БОЛЬШЕ НЕТ (11.10.2026). Здесь жили 22 замены между 1.21.x
// и 26.1+ (`GuiGraphics` -> `GuiGraphicsExtractor`, `"render"` ->
// `"extractRenderState"`, `ResourceLocation` -> `Identifier` и прочие). Все
// они нужны были только сборке под 1.21.11 — её сняли, а между 26.2 и 26.3
// имена не расходятся. Прежний вид файла — в git (коммит 1308fe1, 0.2.31).
//
// ⚠️ Различие 26.2 ↔ 26.3 одно — ввод с клавиатуры (GLFW -> SDL), и оно
// не переименование: другое число аргументов у `isKeyDown` и другие коды
// клавиш. Поэтому это условный блок `//? if <26.3` в `core/Keys.java`, а не
// замена здесь.
