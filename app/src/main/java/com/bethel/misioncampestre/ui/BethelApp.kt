package com.bethel.misioncampestre.ui

import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.consumeWindowInsets
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Icon
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.navigation.NavDestination
import androidx.navigation.NavDestination.Companion.hasRoute
import androidx.navigation.NavDestination.Companion.hierarchy
import androidx.navigation.NavGraph.Companion.findStartDestination
import androidx.navigation.NavHostController
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import com.bethel.misioncampestre.navigation.BethelNavHost
import com.bethel.misioncampestre.navigation.PestanaInferior

/**
 * Raíz de la interfaz: barra de navegación inferior con las cinco pestañas
 * (Inicio, Miembros, Grupos, Asistencia, Eventos) y el [BethelNavHost].
 */
@Composable
fun BethelApp() {
    val navController = rememberNavController()
    val entradaActual by navController.currentBackStackEntryAsState()
    val destinoActual = entradaActual?.destination

    Scaffold(
        modifier = Modifier.fillMaxSize(),
        // Cada pantalla gestiona la barra de estado con su propia TopAppBar;
        // la barra inferior gestiona la barra de navegación del sistema.
        contentWindowInsets = WindowInsets(0, 0, 0, 0),
        bottomBar = {
            BarraNavegacionInferior(
                destinoActual = destinoActual,
                alSeleccionar = { pestana -> navController.navegarAPestana(pestana) },
            )
        },
    ) { relleno ->
        BethelNavHost(
            navController = navController,
            modifier = Modifier
                .padding(relleno)
                .consumeWindowInsets(relleno),
        )
    }
}

@Composable
private fun BarraNavegacionInferior(
    destinoActual: NavDestination?,
    alSeleccionar: (PestanaInferior) -> Unit,
) {
    NavigationBar {
        PestanaInferior.entries.forEach { pestana ->
            val seleccionada = destinoActual.perteneceA(pestana)
            NavigationBarItem(
                selected = seleccionada,
                onClick = { alSeleccionar(pestana) },
                icon = {
                    Icon(
                        imageVector = if (seleccionada) pestana.iconoSeleccionado else pestana.icono,
                        contentDescription = pestana.etiqueta,
                    )
                },
                label = { Text(text = pestana.etiqueta) },
                alwaysShowLabel = true,
            )
        }
    }
}

/** Indica si el destino actual (o alguno de sus ancestros) pertenece a la pestaña dada. */
private fun NavDestination?.perteneceA(pestana: PestanaInferior): Boolean =
    this?.hierarchy?.any { destino -> destino.hasRoute(pestana.claseRuta) } == true

/**
 * Navega a una pestaña de nivel superior conservando el estado de cada una y
 * evitando acumular copias del mismo destino en la pila de retroceso.
 */
private fun NavHostController.navegarAPestana(pestana: PestanaInferior) {
    navigate(pestana.ruta) {
        popUpTo(graph.findStartDestination().id) {
            saveState = true
        }
        launchSingleTop = true
        restoreState = true
    }
}
