package com.bethel.misioncampestre.navigation

import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Event
import androidx.compose.material.icons.filled.FactCheck
import androidx.compose.material.icons.filled.Groups
import androidx.compose.material.icons.filled.Home
import androidx.compose.material.icons.filled.People
import androidx.compose.material.icons.outlined.Event
import androidx.compose.material.icons.outlined.FactCheck
import androidx.compose.material.icons.outlined.Groups
import androidx.compose.material.icons.outlined.Home
import androidx.compose.material.icons.outlined.People
import androidx.compose.ui.graphics.vector.ImageVector
import kotlin.reflect.KClass

/**
 * Pestañas de la barra de navegación inferior, en el orden en que se muestran.
 *
 * @property etiqueta Texto visible bajo el icono.
 * @property ruta Objeto de ruta tipada al que se navega.
 * @property claseRuta Clase de la ruta, usada para saber si la pestaña está seleccionada.
 * @property icono Icono en estado normal (contorno).
 * @property iconoSeleccionado Icono en estado seleccionado (relleno).
 */
enum class PestanaInferior(
    val etiqueta: String,
    val ruta: Any,
    val claseRuta: KClass<*>,
    val icono: ImageVector,
    val iconoSeleccionado: ImageVector,
) {
    INICIO(
        etiqueta = "Inicio",
        ruta = RutaInicio,
        claseRuta = RutaInicio::class,
        icono = Icons.Outlined.Home,
        iconoSeleccionado = Icons.Filled.Home,
    ),
    MIEMBROS(
        etiqueta = "Miembros",
        ruta = RutaMiembros,
        claseRuta = RutaMiembros::class,
        icono = Icons.Outlined.People,
        iconoSeleccionado = Icons.Filled.People,
    ),
    GRUPOS(
        etiqueta = "Grupos",
        ruta = RutaGrupos,
        claseRuta = RutaGrupos::class,
        icono = Icons.Outlined.Groups,
        iconoSeleccionado = Icons.Filled.Groups,
    ),
    ASISTENCIA(
        etiqueta = "Asistencia",
        ruta = RutaAsistencia,
        claseRuta = RutaAsistencia::class,
        icono = Icons.Outlined.FactCheck,
        iconoSeleccionado = Icons.Filled.FactCheck,
    ),
    EVENTOS(
        etiqueta = "Eventos",
        ruta = RutaEventos,
        claseRuta = RutaEventos::class,
        icono = Icons.Outlined.Event,
        iconoSeleccionado = Icons.Filled.Event,
    ),
}
