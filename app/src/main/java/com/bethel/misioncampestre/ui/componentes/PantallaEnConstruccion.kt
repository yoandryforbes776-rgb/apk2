package com.bethel.misioncampestre.ui.componentes

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.People
import androidx.compose.material3.CenterAlignedTopAppBar
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp
import com.bethel.misioncampestre.ui.theme.BethelTheme

/**
 * Pantalla provisional que ocupa el lugar de un módulo aún no generado.
 * Se sustituirá por la pantalla real de cada módulo (Inicio, Miembros, etc.).
 *
 * @param titulo Nombre del módulo (se muestra en la barra superior y como encabezado).
 * @param icono Icono representativo del módulo.
 * @param descripcion Breve explicación de lo que ofrecerá el módulo.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun PantallaEnConstruccion(
    titulo: String,
    icono: ImageVector,
    descripcion: String,
    modifier: Modifier = Modifier,
) {
    Scaffold(
        modifier = modifier,
        topBar = {
            CenterAlignedTopAppBar(
                title = { Text(text = titulo) },
            )
        },
    ) { relleno ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(relleno)
                .padding(horizontal = 32.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.Center,
        ) {
            Icon(
                imageVector = icono,
                contentDescription = null,
                modifier = Modifier.size(72.dp),
                tint = MaterialTheme.colorScheme.primary,
            )
            Spacer(modifier = Modifier.height(16.dp))
            Text(
                text = "Módulo $titulo",
                style = MaterialTheme.typography.titleLarge,
                color = MaterialTheme.colorScheme.onBackground,
                textAlign = TextAlign.Center,
            )
            Spacer(modifier = Modifier.height(8.dp))
            Text(
                text = descripcion,
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                textAlign = TextAlign.Center,
            )
            Spacer(modifier = Modifier.height(24.dp))
            Surface(
                color = MaterialTheme.colorScheme.secondaryContainer,
                contentColor = MaterialTheme.colorScheme.onSecondaryContainer,
                shape = MaterialTheme.shapes.small,
            ) {
                Text(
                    text = "En preparación",
                    style = MaterialTheme.typography.labelLarge,
                    modifier = Modifier.padding(horizontal = 14.dp, vertical = 6.dp),
                )
            }
        }
    }
}

@Preview(name = "Claro", showBackground = true)
@Composable
private fun VistaPreviaPantallaEnConstruccionClaro() {
    BethelTheme(temaOscuro = false) {
        PantallaEnConstruccion(
            titulo = "Miembros",
            icono = Icons.Outlined.People,
            descripcion = "Padrón de miembros de Bethel Central, La Bodeguita y La Angelita.",
        )
    }
}

@Preview(name = "Oscuro", showBackground = true)
@Composable
private fun VistaPreviaPantallaEnConstruccionOscuro() {
    BethelTheme(temaOscuro = true) {
        PantallaEnConstruccion(
            titulo = "Miembros",
            icono = Icons.Outlined.People,
            descripcion = "Padrón de miembros de Bethel Central, La Bodeguita y La Angelita.",
        )
    }
}
