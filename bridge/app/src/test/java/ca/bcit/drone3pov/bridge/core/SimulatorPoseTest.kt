package ca.bcit.drone3pov.bridge.core

import org.junit.Assert.assertEquals
import org.junit.Test

/** The axis check reads forward_m and right_m, so the conversion from north/east has to be right. */
class SimulatorPoseTest {
    private fun pose(north: Float, east: Float, yaw: Float) = SimulatorPose(north, east, 1.2f, yaw, true, true)

    @Test
    fun facingNorthForwardIsNorth() {
        val (forward, right) = pose(2f, 0f, 0f).bodyFrame()
        assertEquals(2f, forward, 1e-4f)
        assertEquals(0f, right, 1e-4f)
    }

    @Test
    fun facingNorthRightIsEast() {
        val (forward, right) = pose(0f, 1.5f, 0f).bodyFrame()
        assertEquals(0f, forward, 1e-4f)
        assertEquals(1.5f, right, 1e-4f)
    }

    @Test
    fun facingEastForwardIsEast() {
        val (forward, right) = pose(0f, 3f, 90f).bodyFrame()
        assertEquals(3f, forward, 1e-4f)
        assertEquals(0f, right, 1e-4f)
    }

    @Test
    fun facingSouthMovingNorthIsBackward() {
        val (forward, right) = pose(1f, 0f, 180f).bodyFrame()
        assertEquals(-1f, forward, 1e-4f)
        assertEquals(0f, right, 1e-4f)
    }

    @Test
    fun mapHasTheAxisCheckFields() {
        val m = pose(2f, 0f, 0f).toMap()
        assertEquals(2f, m["forward_m"] as Float, 1e-4f)
        assertEquals(true, m["flying"])
    }
}
