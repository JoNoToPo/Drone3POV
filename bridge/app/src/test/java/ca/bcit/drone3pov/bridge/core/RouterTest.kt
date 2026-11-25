package ca.bcit.drone3pov.bridge.core

import org.junit.Assert.assertEquals
import org.junit.Test

private class FakeDrone : DroneControl {
    val calls = mutableListOf<String>()
    var lastVelocity: Velocity? = null
    var failWith: BridgeError? = null

    private fun record(name: String) {
        calls += name
        failWith?.let { throw it }
    }

    override fun connect(): Map<String, Any?> { record("connect"); return mapOf("product" to "DJI Mini 2") }
    override fun takeoff() = record("takeoff")
    override fun land() = record("land")
    override fun emergencyStop(): String { record("emergency_stop"); return "motors_off" }
    override fun velocity(v: Velocity) { record("velocity"); lastVelocity = v }
    override fun telemetry(): Telemetry {
        record("telemetry")
        return Telemetry(80, 1.2f, true, mapOf("flying" to true, "battery_pct" to -1))
    }
}

class RouterTest {
    private val drone = FakeDrone()
    private val router = Router(drone)

    @Test
    fun telemetryHasTheFieldsMini2Reads() {
        val r = router.handle("GET", "/v1/telemetry", null)
        assertEquals(200, r.status)
        assertEquals(80, r.body["battery_pct"]) // the real value wins over a clashing extra
        assertEquals(1.2f, r.body["height_m"])
        assertEquals(true, r.body["link_ok"])
        assertEquals(true, r.body["flying"])
    }

    @Test
    fun velocityBodyIsParsed() {
        val body = mapOf("forward_mps" to 0.5, "right_mps" to -0.25, "up_mps" to 0, "yaw_dps" to 45.0)
        val r = router.handle("POST", "/v1/velocity", body)
        assertEquals(200, r.status)
        assertEquals(Velocity(0.5f, -0.25f, 0f, 45f), drone.lastVelocity)
    }

    @Test
    fun velocityWithAMissingFieldIs400() {
        val r = router.handle("POST", "/v1/velocity", mapOf("forward_mps" to 0.5))
        assertEquals(400, r.status)
        assertEquals(false, r.body["ok"])
        assertEquals(emptyList<String>(), drone.calls)
    }

    @Test
    fun velocityWithANonNumberIs400() {
        val body = mapOf("forward_mps" to "fast", "right_mps" to 0, "up_mps" to 0, "yaw_dps" to 0)
        assertEquals(400, router.handle("POST", "/v1/velocity", body).status)
    }

    @Test
    fun emergencyStopReportsWhatItDid() {
        val r = router.handle("POST", "/v1/emergency-stop", null)
        assertEquals(200, r.status)
        assertEquals("motors_off", r.body["action"])
        assertEquals(listOf("emergency_stop"), drone.calls)
    }

    @Test
    fun droneErrorsKeepTheirStatus() {
        drone.failWith = BridgeError(409, "not flying")
        val r = router.handle("POST", "/v1/land", null)
        assertEquals(409, r.status)
        assertEquals("not flying", r.body["error"])
    }

    @Test
    fun unknownPathIs404AndWrongMethodIs405() {
        assertEquals(404, router.handle("POST", "/v1/flip", null).status)
        assertEquals(405, router.handle("GET", "/v1/takeoff", null).status)
        assertEquals(405, router.handle("POST", "/v1/telemetry", null).status)
    }

    @Test
    fun connectMergesProductInfo() {
        val r = router.handle("POST", "/v1/connect", null)
        assertEquals(true, r.body["ok"])
        assertEquals("DJI Mini 2", r.body["product"])
    }
}
