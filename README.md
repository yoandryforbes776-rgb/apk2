# Bethel Misión Campestre — App de gestión

Aplicación Android nativa para la gestión de la congregación cristiana
**Bethel Misión Campestre**, con su sede central y sus dos misiones:

| Misión           | Descripción                          |
|------------------|--------------------------------------|
| Bethel Central   | Sede central de la congregación      |
| La Bodeguita     | Misión                               |
| La Angelita      | Misión                               |

Toda lista de la aplicación (miembros, grupos, asistencia, eventos) es filtrable
por misión.

## Stack técnico

| Componente              | Versión / Tecnología                                   |
|-------------------------|--------------------------------------------------------|
| Lenguaje                | Kotlin 2.4.20                                          |
| Interfaz                | Jetpack Compose (BOM 2026.09.00) + Material 3          |
| Arquitectura            | MVVM: `ViewModel` + `StateFlow`                        |
| Navegación              | Navigation Compose 2.10.2 (rutas tipadas)              |
| Persistencia            | Room 2.8.5 (KSP 2.3.12)                                |
| Compilación             | Android Gradle Plugin 9.3.3 · Gradle 9.5.0 · JDK 17+   |
| SDK                     | `minSdk` 26 · `targetSdk` 36 · `compileSdk` 37         |
| Idioma de la interfaz   | Español                                                |

AGP 9 incluye soporte Kotlin integrado (*built-in Kotlin*), por lo que **no** se
aplica el plugin `org.jetbrains.kotlin.android`.

## Diseño

Estilo sobrio para iglesia: azul oscuro primario (`#1B365D`), superficies
blancas / gris claro y acentos dorados suaves (`#D8B95C`). Modo claro y oscuro
(`ui/theme/BethelTheme`).

## Estructura del módulo `app`

```
app/src/main/java/com/bethel/misioncampestre/
├── BethelApplication.kt          # Application (alojará el contenedor de dependencias)
├── MainActivity.kt               # Actividad única, edge-to-edge, setContent
├── navigation/
│   ├── Rutas.kt                  # Rutas tipadas (@Serializable)
│   ├── PestanaInferior.kt        # Las 5 pestañas: Inicio, Miembros, Grupos, Asistencia, Eventos
│   └── BethelNavHost.kt          # NavHost principal
└── ui/
    ├── BethelApp.kt              # Scaffold raíz + NavigationBar
    ├── componentes/
    │   └── PantallaEnConstruccion.kt
    └── theme/
        ├── Color.kt · Shape.kt · Type.kt · Theme.kt
```

Los módulos de funcionalidad (datos Room, repositorios, ViewModels y pantallas)
se irán añadiendo bajo `data/`, `ui/<modulo>/` y `navigation/`.

## Compilar

1. Abrir la carpeta raíz del repositorio en **Android Studio** (Quail 3 / 2026.1.3
   o superior, con soporte para AGP 9.3).
2. Aceptar la instalación del SDK Platform 37 si el IDE la solicita.
3. Ejecutar la configuración `app` o, desde terminal:

```bash
./gradlew :app:assembleDebug
```
