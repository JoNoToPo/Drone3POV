package ca.bcit.drone3pov.bridge.core

/** An error with the HTTP status the API should answer with. */
class BridgeError(val status: Int, message: String) : RuntimeException(message)

data class Telemetry(
    val batteryPct: Int,
    val heightM: Float,
    val linkOk: Boolean,
    /** Extra fields for debugging. api/app/mini2.py ignores them. */
    val extra: Map<String, Any?> = emptyMap(),
)

/** What the HTTP layer needs from the drone. DjiDrone is the real one; tests use a fake. */
interface DroneControl {
    /** Checks the SDK and aircraft are ready and clears the emergency-stop latch. */
    fun connect(): Map<String, Any?>
    fun takeoff()
    fun land()
    /** Returns a short name for what it actually did, e.g. "motors_off". */
    fun emergencyStop(): String
    fun velocity(v: Velocity)
    fun telemetry(): Telemetry

    /**
     * Starts DJI's simulator on the aircraft's flight controller. Only allowed on the ground with the
     * motors off. While it runs, takeoff and velocity move a virtual aircraft; the real one stays put
     * (but its motors may spin, so the propellers must be off).
     */
    fun startSimulator(start: SimulatorStart): Map<String, Any?>
    /** Stops the simulator. Refused while the simulated aircraft is flying: land it first. */
    fun stopSimulator(): Map<String, Any?>
}

data class Reply(val status: Int, val body: Map<String, Any?>)

/**
 * Maps the bridge API (see bridge/README.md) onto [DroneControl].
 *
 * Every call returns quickly. api/app/mini2.py uses a 0.5 s timeout, so takeoff and
 * land are accepted and run in the background; poll /v1/telemetry to follow them.
 */
class Router(private val drone: DroneControl) {

    fun handle(method: String, path: String, body: Map<String, Any?>?): Reply {
        val route = ROUTES[path] ?: return error(404, "no such endpoint: $path")
        if (route != method) return error(405, "$path takes $route")

        return try {
            when (path) {
                // Checked first and runs on the request thread, so it never waits behind anything.
                "/v1/emergency-stop" -> ok("action" to drone.emergencyStop())
                "/v1/connect" -> Reply(200, mapOf("ok" to true) + drone.connect())
                "/v1/takeoff" -> { drone.takeoff(); ok("accepted" to true) }
                "/v1/land" -> { drone.land(); ok("accepted" to true) }
                "/v1/velocity" -> { drone.velocity(Velocity.fromBody(body ?: emptyMap())); ok() }
                "/v1/simulator/start" -> Reply(200, mapOf("ok" to true) + drone.startSimulator(SimulatorStart.fromBody(body)))
                "/v1/simulator/stop" -> Reply(200, mapOf("ok" to true) + drone.stopSimulator())
                "/v1/telemetry" -> {
                    val t = drone.telemetry()
                    Reply(
                        200,
                        t.extra + mapOf(
                            "battery_pct" to t.batteryPct,
                            "height_m" to t.heightM,
                            "link_ok" to t.linkOk,
                        ),
                    )
                }
                else -> error(404, "no such endpoint: $path")
            }
        } catch (e: BridgeError) {
            error(e.status, e.message ?: "error")
        } catch (e: Exception) {
            error(500, e.message ?: e.javaClass.simpleName)
        }
    }

    private fun ok(vararg extra: Pair<String, Any?>) = Reply(200, mapOf("ok" to true, *extra))

    private fun error(status: Int, message: String) =
        Reply(status, mapOf("ok" to false, "error" to message))

    companion object {
        val ROUTES = mapOf(
            "/v1/connect" to "POST",
            "/v1/takeoff" to "POST",
            "/v1/land" to "POST",
            "/v1/emergency-stop" to "POST",
            "/v1/velocity" to "POST",
            "/v1/telemetry" to "GET",
            "/v1/simulator/start" to "POST",
            "/v1/simulator/stop" to "POST",
        )
    }
}
