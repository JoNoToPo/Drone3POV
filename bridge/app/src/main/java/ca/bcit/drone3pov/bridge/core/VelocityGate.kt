package ca.bcit.drone3pov.bridge.core

/**
 * Sits between the HTTP API and the 20 Hz virtual-stick loop.
 *
 * The edge laptop posts setpoints whenever it likes; the control loop asks [next]
 * for what to send on each tick. The gate makes sure the drone hovers when:
 * - no setpoint has arrived yet, or the last one is older than [Limits.COMMAND_TIMEOUT_MS]
 *   (edge crashed, Wi-Fi dropped, laptop lid closed);
 * - the emergency stop latch is set. Only [rearm] clears it.
 *
 * It also stops climbing above [Limits.MAX_HEIGHT_M] and descending below
 * [Limits.MIN_HEIGHT_M], and refuses to climb when the height is unknown.
 */
class VelocityGate(private val clock: () -> Long = System::currentTimeMillis) {
    private var latest = Velocity.ZERO
    private var receivedAt: Long? = null

    @Volatile
    var stopped = false
        private set

    @Synchronized
    fun submit(v: Velocity) {
        if (stopped) throw BridgeError(409, "emergency stop is latched; POST /v1/connect to re-arm")
        latest = v.clamped()
        receivedAt = clock()
    }

    /** Emergency stop. Velocity is refused until [rearm]. */
    @Synchronized
    fun stop() {
        stopped = true
        clear()
    }

    @Synchronized
    fun rearm() {
        stopped = false
        clear()
    }

    /** Drops the current setpoint, e.g. before landing. */
    @Synchronized
    fun clear() {
        latest = Velocity.ZERO
        receivedAt = null
    }

    /** The setpoint to send on this tick, given the current height (null if unknown). */
    @Synchronized
    fun next(heightM: Float?): Velocity {
        val at = receivedAt
        if (stopped || at == null || clock() - at > Limits.COMMAND_TIMEOUT_MS) return Velocity.ZERO

        var up = latest.upMps
        if (heightM == null) {
            up = minOf(up, 0f)
        } else {
            if (heightM >= Limits.MAX_HEIGHT_M && up > 0f) up = 0f
            if (heightM <= Limits.MIN_HEIGHT_M && up < 0f) up = 0f
        }
        return latest.copy(upMps = up)
    }
}
