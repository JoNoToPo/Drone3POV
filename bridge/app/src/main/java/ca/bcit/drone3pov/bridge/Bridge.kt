package ca.bcit.drone3pov.bridge

import android.content.Context
import ca.bcit.drone3pov.bridge.core.Limits
import ca.bcit.drone3pov.bridge.core.Router
import java.net.Inet4Address
import java.net.NetworkInterface

/** Owns the drone and the HTTP server for the life of [BridgeService]. */
object Bridge {
    @Volatile var drone: DjiDrone? = null; private set
    @Volatile private var server: HttpBridgeServer? = null
    @Volatile var serverError: String? = null; private set

    @Synchronized
    fun start(context: Context) {
        if (drone != null) return
        val d = DjiDrone(context.applicationContext)
        d.start()
        drone = d
        try {
            server = HttpBridgeServer(Limits.PORT, Router(d)).also {
                it.start(5_000, false)
            }
            d.events.add("HTTP server on port ${Limits.PORT}")
        } catch (e: Exception) {
            serverError = e.message
            d.events.add("HTTP server failed: ${e.message}")
        }
    }

    @Synchronized
    fun stop() {
        server?.stop()
        server = null
        drone?.shutdown()
        drone = null
    }

    /** The phone's IPv4 addresses, for setting BRIDGE_URL on the edge laptop. */
    fun addresses(): List<String> = try {
        NetworkInterface.getNetworkInterfaces().toList()
            .filter { it.isUp && !it.isLoopback }
            .flatMap { it.inetAddresses.toList() }
            .filterIsInstance<Inet4Address>()
            .map { "http://${it.hostAddress}:${Limits.PORT}" }
    } catch (e: Exception) {
        emptyList()
    }
}
