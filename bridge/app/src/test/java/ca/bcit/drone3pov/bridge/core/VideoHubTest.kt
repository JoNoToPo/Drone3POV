package ca.bcit.drone3pov.bridge.core

import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class VideoHubTest {
    private var now = 10_000L
    private fun hub(maxViewers: Int = 2, queue: Int = 4) = VideoHub(maxViewers, queue) { now }

    private fun VideoHub.Viewer.readExactly(n: Int): ByteArray {
        val out = ByteArray(n)
        var got = 0
        while (got < n) {
            val r = read(out, got, n - got)
            if (r == -1) error("stream ended after $got bytes")
            got += r
        }
        return out
    }

    @Test
    fun viewerGetsChunksInOrder() {
        val h = hub()
        val v = h.open()
        h.publish(byteArrayOf(1, 2, 3, 99), 3) // only the first 3 bytes count
        h.publish(byteArrayOf(4, 5), 2)
        assertArrayEquals(byteArrayOf(1, 2, 3, 4, 5), v.readExactly(5))
    }

    @Test
    fun publishCopiesTheSdkBuffer() {
        val h = hub()
        val v = h.open()
        val sdkBuffer = byteArrayOf(7, 8)
        h.publish(sdkBuffer, 2)
        sdkBuffer[0] = 0 // the SDK reuses its buffer
        assertArrayEquals(byteArrayOf(7, 8), v.readExactly(2))
    }

    @Test
    fun publishingWithNoViewersStillCounts() {
        val h = hub()
        h.publish(ByteArray(100), 100)
        assertEquals(100L, h.totalBytes)
        assertTrue(h.isFlowing())
    }

    @Test
    fun viewerLimitIs429() {
        val h = hub(maxViewers = 1)
        h.open()
        try {
            h.open()
            error("expected a 429")
        } catch (e: BridgeError) {
            assertEquals(429, e.status)
        }
    }

    @Test
    fun aViewerThatFallsBehindIsDisconnectedWithoutAffectingOthers() {
        val h = hub(queue = 2)
        val slow = h.open()
        val fast = h.open()
        repeat(2) { i ->
            h.publish(byteArrayOf(i.toByte()), 1)
            fast.readExactly(1) // keeps up
        }
        h.publish(byteArrayOf(10), 1)
        h.publish(byteArrayOf(11), 1) // slow already has 2 queued: this one overflows it

        assertEquals("fell behind", slow.closeReason)
        assertEquals(-1, slow.read(ByteArray(8), 0, 8))
        assertArrayEquals(byteArrayOf(10, 11), fast.readExactly(2))
        assertEquals(1, h.viewerCount)
    }

    @Test
    fun closingAViewerFreesItsSlot() {
        val h = hub(maxViewers = 1)
        h.open().close()
        assertEquals(0, h.viewerCount)
        h.open() // no 429
    }

    @Test
    fun closeAllEndsEveryStream() {
        val h = hub()
        val a = h.open()
        val b = h.open()
        h.closeAll("drone disconnected")
        assertEquals(-1, a.read(ByteArray(1), 0, 1))
        assertEquals(-1, b.read(ByteArray(1), 0, 1))
        assertEquals("drone disconnected", a.closeReason)
    }

    @Test
    fun flowingTurnsFalseAfterTwoSecondsWithoutVideo() {
        val h = hub()
        h.publish(ByteArray(10), 10)
        now += 2500
        assertFalse(h.isFlowing())
    }

    @Test
    fun bitrateIsReportedPerSecond() {
        val h = hub()
        h.publish(ByteArray(1000), 1000)
        now += 1000
        h.publish(ByteArray(10), 10) // closes the first one-second window
        assertEquals(8L, h.status()["video_kbps"]) // 1000 bytes in a second = 8 kbps
    }

    @Test
    fun feedQueryIsParsed() {
        assertEquals(VideoFeedKind.PRIMARY, VideoFeedKind.fromQuery(null))
        assertEquals(VideoFeedKind.PRIMARY, VideoFeedKind.fromQuery("primary"))
        assertEquals(VideoFeedKind.TRANSCODED, VideoFeedKind.fromQuery("Transcoded"))
        try {
            VideoFeedKind.fromQuery("4k")
            error("expected a 400")
        } catch (e: BridgeError) {
            assertEquals(400, e.status)
        }
    }
}
