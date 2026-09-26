package com.bethel.misioncampestre.ui.theme

import android.os.Build
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.ColorScheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.dynamicDarkColorScheme
import androidx.compose.material3.dynamicLightColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.platform.LocalContext

private val EsquemaClaro: ColorScheme = lightColorScheme(
    primary = AzulPrimarioClaro,
    onPrimary = SobrePrimarioClaro,
    primaryContainer = ContenedorPrimarioClaro,
    onPrimaryContainer = SobreContenedorPrimarioClaro,
    inversePrimary = PrimarioInversoClaro,
    secondary = DoradoSecundarioClaro,
    onSecondary = SobreSecundarioClaro,
    secondaryContainer = ContenedorSecundarioClaro,
    onSecondaryContainer = SobreContenedorSecundarioClaro,
    tertiary = TerciarioClaro,
    onTertiary = SobreTerciarioClaro,
    tertiaryContainer = ContenedorTerciarioClaro,
    onTertiaryContainer = SobreContenedorTerciarioClaro,
    background = FondoClaro,
    onBackground = SobreFondoClaro,
    surface = SuperficieClara,
    onSurface = SobreSuperficieClara,
    surfaceVariant = SuperficieVarianteClara,
    onSurfaceVariant = SobreSuperficieVarianteClara,
    surfaceTint = AzulPrimarioClaro,
    inverseSurface = SuperficieInversaClara,
    inverseOnSurface = SobreSuperficieInversaClara,
    error = ErrorClaro,
    onError = SobreErrorClaro,
    errorContainer = ContenedorErrorClaro,
    onErrorContainer = SobreContenedorErrorClaro,
    outline = ContornoClaro,
    outlineVariant = ContornoVarianteClaro,
    surfaceBright = SuperficieBrillanteClara,
    surfaceDim = SuperficieTenueClara,
    surfaceContainer = ContenedorSuperficieClaro,
    surfaceContainerHigh = ContenedorSuperficieAltoClaro,
    surfaceContainerHighest = ContenedorSuperficieMasAltoClaro,
    surfaceContainerLow = ContenedorSuperficieBajoClaro,
    surfaceContainerLowest = ContenedorSuperficieMasBajoClaro,
)

private val EsquemaOscuro: ColorScheme = darkColorScheme(
    primary = AzulPrimarioOscuro,
    onPrimary = SobrePrimarioOscuro,
    primaryContainer = ContenedorPrimarioOscuro,
    onPrimaryContainer = SobreContenedorPrimarioOscuro,
    inversePrimary = PrimarioInversoOscuro,
    secondary = DoradoSecundarioOscuro,
    onSecondary = SobreSecundarioOscuro,
    secondaryContainer = ContenedorSecundarioOscuro,
    onSecondaryContainer = SobreContenedorSecundarioOscuro,
    tertiary = TerciarioOscuro,
    onTertiary = SobreTerciarioOscuro,
    tertiaryContainer = ContenedorTerciarioOscuro,
    onTertiaryContainer = SobreContenedorTerciarioOscuro,
    background = FondoOscuro,
    onBackground = SobreFondoOscuro,
    surface = SuperficieOscura,
    onSurface = SobreSuperficieOscura,
    surfaceVariant = SuperficieVarianteOscura,
    onSurfaceVariant = SobreSuperficieVarianteOscura,
    surfaceTint = AzulPrimarioOscuro,
    inverseSurface = SuperficieInversaOscura,
    inverseOnSurface = SobreSuperficieInversaOscura,
    error = ErrorOscuro,
    onError = SobreErrorOscuro,
    errorContainer = ContenedorErrorOscuro,
    onErrorContainer = SobreContenedorErrorOscuro,
    outline = ContornoOscuro,
    outlineVariant = ContornoVarianteOscuro,
    surfaceBright = SuperficieBrillanteOscura,
    surfaceDim = SuperficieTenueOscura,
    surfaceContainer = ContenedorSuperficieOscuro,
    surfaceContainerHigh = ContenedorSuperficieAltoOscuro,
    surfaceContainerHighest = ContenedorSuperficieMasAltoOscuro,
    surfaceContainerLow = ContenedorSuperficieBajoOscuro,
    surfaceContainerLowest = ContenedorSuperficieMasBajoOscuro,
)

/**
 * Tema Material 3 de Bethel Misión Campestre con soporte de modo claro y oscuro.
 *
 * @param temaOscuro Si se debe usar el esquema oscuro. Por defecto sigue al sistema.
 * @param colorDinamico Colores dinámicos de Android 12+ (Material You). Desactivado por
 * defecto para conservar la identidad visual institucional (azul y dorado).
 */
@Composable
fun BethelTheme(
    temaOscuro: Boolean = isSystemInDarkTheme(),
    colorDinamico: Boolean = false,
    content: @Composable () -> Unit,
) {
    val esquema = when {
        colorDinamico && Build.VERSION.SDK_INT >= Build.VERSION_CODES.S -> {
            val contexto = LocalContext.current
            if (temaOscuro) dynamicDarkColorScheme(contexto) else dynamicLightColorScheme(contexto)
        }

        temaOscuro -> EsquemaOscuro
        else -> EsquemaClaro
    }

    MaterialTheme(
        colorScheme = esquema,
        typography = Tipografia,
        shapes = Formas,
        content = content,
    )
}
