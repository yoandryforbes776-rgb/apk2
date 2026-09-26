package com.bethel.misioncampestre.navigation

import kotlinx.serialization.Serializable

/*
 * Rutas tipadas de Navigation Compose (kotlinx.serialization).
 *
 * Estos cinco destinos son los de nivel superior y corresponden a las pestañas
 * de la barra de navegación inferior. Las pantallas de detalle/edición de cada
 * módulo añadirán aquí sus propias rutas (por ejemplo, `data class RutaDetalleMiembro(val id: Long)`).
 */

@Serializable
data object RutaInicio

@Serializable
data object RutaMiembros

@Serializable
data object RutaGrupos

@Serializable
data object RutaAsistencia

@Serializable
data object RutaEventos
