// Archivo de compilación raíz. Los plugins se declaran aquí con `apply false`
// y se aplican en el módulo :app. AGP 9 incluye soporte Kotlin integrado
// (built-in Kotlin), por lo que NO se aplica `org.jetbrains.kotlin.android`.
plugins {
    alias(libs.plugins.android.application) apply false
    alias(libs.plugins.kotlin.compose) apply false
    alias(libs.plugins.kotlin.serialization) apply false
    alias(libs.plugins.ksp) apply false
    alias(libs.plugins.room) apply false
}
