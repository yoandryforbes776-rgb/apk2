package com.bethel.misioncampestre.navigation

import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.navigation.NavHostController
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import com.bethel.misioncampestre.ui.componentes.PantallaEnConstruccion

/**
 * Grafo de navegación principal. Por ahora cada pestaña muestra una pantalla
 * provisional; a medida que se generen los módulos, cada `composable<...>`
 * pasará a mostrar su pantalla real y se añadirán las rutas de detalle.
 */
@Composable
fun BethelNavHost(
    navController: NavHostController,
    modifier: Modifier = Modifier,
) {
    NavHost(
        navController = navController,
        startDestination = RutaInicio,
        modifier = modifier,
    ) {
        composable<RutaInicio> {
            PantallaEnConstruccion(
                titulo = PestanaInferior.INICIO.etiqueta,
                icono = PestanaInferior.INICIO.icono,
                descripcion = "Resumen general de la congregación: Bethel Central, La Bodeguita y La Angelita.",
            )
        }

        composable<RutaMiembros> {
            PantallaEnConstruccion(
                titulo = PestanaInferior.MIEMBROS.etiqueta,
                icono = PestanaInferior.MIEMBROS.icono,
                descripcion = "Padrón de miembros con filtro por misión, datos de contacto y estado.",
            )
        }

        composable<RutaGrupos> {
            PantallaEnConstruccion(
                titulo = PestanaInferior.GRUPOS.etiqueta,
                icono = PestanaInferior.GRUPOS.icono,
                descripcion = "Grupos y ministerios de cada misión con sus integrantes y responsables.",
            )
        }

        composable<RutaAsistencia> {
            PantallaEnConstruccion(
                titulo = PestanaInferior.ASISTENCIA.etiqueta,
                icono = PestanaInferior.ASISTENCIA.icono,
                descripcion = "Registro de asistencia a cultos y reuniones por misión y por fecha.",
            )
        }

        composable<RutaEventos> {
            PantallaEnConstruccion(
                titulo = PestanaInferior.EVENTOS.etiqueta,
                icono = PestanaInferior.EVENTOS.icono,
                descripcion = "Calendario de eventos y actividades de la congregación y sus misiones.",
            )
        }
    }
}
