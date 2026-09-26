package com.bethel.misioncampestre

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import com.bethel.misioncampestre.ui.BethelApp
import com.bethel.misioncampestre.ui.theme.BethelTheme

/**
 * Actividad única de la aplicación. Toda la interfaz se construye con
 * Jetpack Compose y la navegación entre pantallas se resuelve en [BethelApp].
 */
class MainActivity : ComponentActivity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            BethelTheme {
                BethelApp()
            }
        }
    }
}
