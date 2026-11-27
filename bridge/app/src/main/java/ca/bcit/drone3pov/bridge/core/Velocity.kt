package ca.bcit.drone3pov.bridge.core

/** Body-frame velocity setpoint, in the units the API uses. */
data class Velocity(
    val forwardMps: Float,
    val rightMps: Float,
    val upMps: Float,
    val yawDps: Float,
) {
    fun clamped() = Velocity(
        forwardMps = forwardMps.coerceIn(-Limits.MAX_SPEED_MPS, Limits.MAX_SPEED_MPS),
        rightMps = rightMps.coerceIn(-Limits.MAX_SPEED_MPS, Limits.MAX_SPEED_MPS),
        upMps = upMps.coerceIn(-Limits.MAX_SPEED_MPS, Limits.MAX_SPEED_MPS),
        yawDps = yawDps.coerceIn(-Limits.MAX_YAW_DPS, Limits.MAX_YAW_DPS),
    )

    companion object {
        val ZERO = Velocity(0f, 0f, 0f, 0f)

        /** Reads the /v1/velocity body. All four fields are required and must be finite numbers. */
        fun fromBody(body: Map<String, Any?>): Velocity = Velocity(
            forwardMps = number(body, "forward_mps"),
            rightMps = number(body, "right_mps"),
            upMps = number(body, "up_mps"),
            yawDps = number(body, "yaw_dps"),
        )

        private fun number(body: Map<String, Any?>, key: String): Float {
            val raw = body[key] ?: throw BridgeError(400, "missing $key")
            if (raw !is Number) throw BridgeError(400, "$key must be a number")
            val value = raw.toDouble()
            if (!value.isFinite()) throw BridgeError(400, "$key must be finite")
            return value.toFloat()
        }
    }
}
