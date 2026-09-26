# Reglas de R8/ProGuard del módulo :app.
# Solo se aplican cuando `isMinifyEnabled = true` en app/build.gradle.kts.
#
# Room, Jetpack Compose, Navigation y kotlinx.serialization ya incluyen sus
# propias reglas "consumer" dentro de sus artefactos, por lo que normalmente no
# hace falta añadir nada aquí.

# Conservar nombres de archivo y números de línea para trazas legibles.
-keepattributes SourceFile,LineNumberTable
-renamesourcefileattribute SourceFile
