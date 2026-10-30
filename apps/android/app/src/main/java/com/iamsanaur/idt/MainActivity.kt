package com.iamsanaur.idt

import android.Manifest
import android.app.NotificationChannel
import android.app.NotificationManager
import android.content.Intent
import android.content.pm.ApplicationInfo
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowForward
import androidx.compose.material.icons.filled.MoreVert
import androidx.compose.material.icons.filled.Notifications
import androidx.compose.material3.Icon
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.NavigationBarItemDefaults
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import androidx.navigation.NavHostController
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import com.iamsanaur.idt.ui.AlertsScreen
import com.iamsanaur.idt.ui.IdtTheme
import com.iamsanaur.idt.ui.IndexDetailScreen
import com.iamsanaur.idt.ui.JournalScreen
import com.iamsanaur.idt.ui.LocalPalette
import com.iamsanaur.idt.ui.MarketsScreen
import com.iamsanaur.idt.ui.MoreScreen
import com.iamsanaur.idt.ui.OptionsScreen
import com.iamsanaur.idt.ui.ResearchScreen
import com.iamsanaur.idt.ui.SettingsScreen
import com.iamsanaur.idt.ui.StrategyScreen
import com.iamsanaur.idt.ui.TradeScreen
import kotlinx.coroutines.delay
import org.json.JSONObject

class AppState(private val store: ConnectionStore) {
    var conn by mutableStateOf(store.load())
    var status by mutableStateOf<JSONObject?>(null)
    var theme by mutableStateOf(store.theme)
    var tradeStep by mutableStateOf(0)
    var alertsVersion by mutableStateOf(0)

    val api get() = Api(conn)

    fun pair(c: Connection) {
        conn = c
        store.save(c)
    }

    fun setThemePref(t: String) {
        theme = t
        store.theme = t
    }

    suspend fun refreshStatus() {
        status = runCatching { api.obj("/status") }.getOrNull()
    }
}

val LocalApp = staticCompositionLocalOf<AppState> { error("AppState not provided") }

private data class Tab(val route: String, val label: String, val icon: ImageVector)

private val tabs = listOf(
    Tab("markets", "Markets", com.iamsanaur.idt.ui.IdtIcons.Markets),
    Tab("options", "Options", com.iamsanaur.idt.ui.IdtIcons.Options),
    Tab("trade", "Trade", Icons.Filled.ArrowForward),
    Tab("alerts", "Alerts", Icons.Filled.Notifications),
    Tab("more", "More", Icons.Filled.MoreVert),
)

class MainActivity : ComponentActivity() {
    private lateinit var app: AppState
    private var nav: NavHostController? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        app = AppState(ConnectionStore(this))
        handleIntent(intent)
        createChannel()
        setContent {
            androidx.compose.runtime.CompositionLocalProvider(LocalApp provides app) {
                IdtTheme(app.theme) { Root() }
            }
        }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        handleIntent(intent)
    }

    /** Pairing deep link, plus debug-only launch extras used for screenshots. */
    private fun handleIntent(intent: Intent?) {
        intent?.data?.toString()?.let { Connection.fromPairing(it) }?.let { app.pair(it) }
        val debuggable = applicationInfo.flags and ApplicationInfo.FLAG_DEBUGGABLE != 0
        if (debuggable && intent != null) {
            val url = intent.getStringExtra("idtURL"); val token = intent.getStringExtra("idtToken")
            if (url != null && token != null) app.pair(Connection(url, token))
            intent.getStringExtra("idtStep")?.toIntOrNull()?.let { app.tradeStep = it }
            pendingTab = intent.getStringExtra("idtTab")
        }
    }

    private var pendingTab: String? = null

    private fun createChannel() {
        if (Build.VERSION.SDK_INT >= 26) {
            getSystemService(NotificationManager::class.java)
                .createNotificationChannel(NotificationChannel("alerts", "Trade alerts", NotificationManager.IMPORTANCE_HIGH))
        }
    }

    fun requestNotifications() {
        if (Build.VERSION.SDK_INT >= 33 && checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(arrayOf(Manifest.permission.POST_NOTIFICATIONS), 1)
        }
    }

    private fun notify(alert: JSONObject) {
        if (Build.VERSION.SDK_INT >= 33 && checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) return
        val n = NotificationCompat.Builder(this, "alerts")
            .setSmallIcon(android.R.drawable.ic_dialog_info)
            .setContentTitle(alert.optString("label"))
            .setContentText("Observed ${alert.opt("observed") ?: ""}")
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .build()
        NotificationManagerCompat.from(this).notify(alert.optString("id").hashCode(), n)
    }

    @Composable
    private fun Root() {
        val navController = rememberNavController().also { nav = it }
        val back by navController.currentBackStackEntryAsState()
        val p = LocalPalette.current

        LaunchedEffect(app.conn) {
            app.refreshStatus()
            pendingTab?.let { t -> pendingTab = null; navController.navigate(t) }
            // Live alerts while the app is open; reconnect every 10 s on failure.
            while (app.conn.configured) {
                runCatching {
                    app.api.events { event, data ->
                        if (event == "alert") runCatching { JSONObject(data) }.getOrNull()?.let { notify(it); app.alertsVersion++ }
                    }
                }
                delay(10_000)
            }
        }

        Scaffold(
            containerColor = p.bg,
            bottomBar = {
                NavigationBar(containerColor = p.surface) {
                    val current = back?.destination?.route.orEmpty()
                    tabs.forEach { t ->
                        val selected = current == t.route || current.startsWith(t.route + "/") ||
                            (t.route == "more" && current in setOf("strategy", "journal", "research", "settings"))
                        NavigationBarItem(
                            selected = selected,
                            onClick = { navController.navigate(t.route) { popUpTo("markets"); launchSingleTop = true } },
                            icon = { Icon(t.icon, contentDescription = t.label) },
                            label = { Text(t.label) },
                            colors = NavigationBarItemDefaults.colors(selectedIconColor = p.accent, selectedTextColor = p.accent, indicatorColor = p.accentSoft),
                        )
                    }
                }
            },
        ) { padding ->
            Box(Modifier.fillMaxSize().background(p.bg).padding(padding)) {
                NavHost(navController, startDestination = "markets") {
                    composable("markets") { MarketsScreen { navController.navigate("markets/$it") } }
                    composable("markets/{symbol}") { e ->
                        IndexDetailScreen(e.arguments?.getString("symbol") ?: "NIFTY") { app.tradeStep = 0; navController.navigate("trade") }
                    }
                    composable("options") { OptionsScreen() }
                    composable("trade") { TradeScreen() }
                    composable("alerts") { AlertsScreen(onAsk = ::requestNotifications) }
                    composable("more") { MoreScreen { navController.navigate(it) } }
                    composable("strategy") { StrategyScreen { app.tradeStep = 1; navController.navigate("trade") } }
                    composable("journal") { JournalScreen() }
                    composable("research") { ResearchScreen() }
                    composable("settings") { SettingsScreen() }
                }
            }
        }
    }
}
