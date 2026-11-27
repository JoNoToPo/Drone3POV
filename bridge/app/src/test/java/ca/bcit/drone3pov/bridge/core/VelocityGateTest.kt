package ca.bcit.drone3pov.bridge.core

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Test

class VelocityGateTest {
    private var now = 1_000L
    private val gate = VelocityGate { now }

    @Test
    fun hoversBeforeAnyCommand() {
        assertEquals(Velocity.ZERO, gate.next(1.5f))
    }

    @Test
    fun passesAFreshCommandThrough() {
        gate.submit(Velocity(0.5f, -0.2f, 0.1f, 30f))
        assertEquals(Velocity(0.5f, -0.2f, 0.1f, 30f), gate.next(1.5f))
    }

    @Test
    fun clampsSpeedAndYaw() {
        gate.submit(Velocity(5f, -5f, 0.2f, 500f))
        val v = gate.next(1.5f)
        assertEquals(Limits.MAX_SPEED_MPS, v.forwardMps)
        assertEquals(-Limits.MAX_SPEED_MPS, v.rightMps)
        assertEquals(0.2f, v.upMps)
        assertEquals(Limits.MAX_YAW_DPS, v.yawDps)
    }

    @Test
    fun hoversWhenTheCommandGoesStale() {
        gate.submit(Velocity(0.5f, 0f, 0f, 0f))
        now += Limits.COMMAND_TIMEOUT_MS
        assertEquals(0.5f, gate.next(1.5f).forwardMps)
        now += 1
        assertEquals(Velocity.ZERO, gate.next(1.5f))
    }

    @Test
    fun emergencyStopLatchesUntilRearmed() {
        gate.submit(Velocity(0.5f, 0f, 0f, 0f))
        gate.stop()
        assertTrue(gate.stopped)
        assertEquals(Velocity.ZERO, gate.next(1.5f))
        try {
            gate.submit(Velocity(0.5f, 0f, 0f, 0f))
            fail("velocity accepted while stopped")
        } catch (e: BridgeError) {
            assertEquals(409, e.status)
        }
        gate.rearm()
        gate.submit(Velocity(0.3f, 0f, 0f, 0f))
        assertEquals(0.3f, gate.next(1.5f).forwardMps)
    }

    @Test
    fun noClimbAtTheCeiling() {
        gate.submit(Velocity(0.2f, 0f, 0.5f, 0f))
        assertEquals(0f, gate.next(Limits.MAX_HEIGHT_M).upMps)
        assertEquals(0.2f, gate.next(Limits.MAX_HEIGHT_M).forwardMps)
    }

    @Test
    fun noDescentAtTheFloor() {
        gate.submit(Velocity(0f, 0f, -0.5f, 0f))
        assertEquals(0f, gate.next(Limits.MIN_HEIGHT_M).upMps)
        assertEquals(-0.5f, gate.next(1.5f).upMps)
    }

    @Test
    fun noClimbWhenHeightIsUnknown() {
        gate.submit(Velocity(0f, 0f, 0.5f, 0f))
        assertEquals(0f, gate.next(null).upMps)
        gate.submit(Velocity(0f, 0f, -0.3f, 0f))
        assertEquals(-0.3f, gate.next(null).upMps)
    }
}
