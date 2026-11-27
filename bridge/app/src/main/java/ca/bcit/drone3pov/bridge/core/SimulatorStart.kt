package ca.bcit.drone3pov.bridge.core

/**
 * Where DJI's simulator puts the virtual aircraft. Body of POST /v1/simulator/start; both fields optional.
 *
 * The simulator runs on the Mini 2's flight controller, so it still needs the real drone connected
 * (propellers off), but the aircraft never leaves the ground while it is active.
 */
data class SimulatorStart(val latitude: Double, val longitude: Double) {
    companion object {
        /** BCIT Burnaby campus. Any open area works; the simulator only needs a valid GPS position. */
        const val DEFAULT_LATITUDE = 49.2504
        const val DEFAULT_LONGITUDE = -123.0016

        /** How often the simulator reports its state (Hz) and how many satellites it pretends to see. */
        const val UPDATE_HZ = 10
        const val SATELLITES = 15

        fun fromBody(body: Map<String, Any?>?): SimulatorStart = SimulatorStart(
            latitude = coordinate(body, "latitude", DEFAULT_LATITUDE, 90.0),
            longitude = coordinate(body, "longitude", DEFAULT_LONGITUDE, 180.0),
        )

        private fun coordinate(body: Map<String, Any?>?, key: String, default: Double, limit: Double): Double {
            val raw = body?.get(key) ?: return default
            if (raw !is Number) throw BridgeError(400, "$key must be a number")
            val value = raw.toDouble()
            if (!value.isFinite() || value < -limit || value > limit) {
                throw BridgeError(400, "$key must be between -$limit and $limit")
            }
            return value
        }
    }
}

/** What the simulator reports, plus how far the aircraft moved along its own axes since the start. */
data class SimulatorPose(
    val northM: Float,
    val eastM: Float,
    val heightM: Float,
    val yawDeg: Float,
    val flying: Boolean,
    val motorsOn: Boolean,
) {
    /**
     * Movement from the start point expressed in the aircraft's frame, using its current heading.
     * After a pure forward command, forwardM grows and rightM stays near 0. That's the axis check.
     * Yaw is degrees clockwise from north, as DJI reports it.
     */
    fun bodyFrame(): Pair<Float, Float> {
        val yaw = Math.toRadians(yawDeg.toDouble())
        val forward = northM * Math.cos(yaw) + eastM * Math.sin(yaw)
        val right = -northM * Math.sin(yaw) + eastM * Math.cos(yaw)
        return forward.toFloat() to right.toFloat()
    }

    fun toMap(): Map<String, Any?> {
        val (forward, right) = bodyFrame()
        return mapOf(
            "north_m" to northM,
            "east_m" to eastM,
            "height_m" to heightM,
            "yaw_deg" to yawDeg,
            "forward_m" to forward,
            "right_m" to right,
            "flying" to flying,
            "motors_on" to motorsOn,
        )
    }
}
