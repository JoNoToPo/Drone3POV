package ca.bcit.drone3pov.bridge

import ca.bcit.drone3pov.bridge.core.DroneControl
import ca.bcit.drone3pov.bridge.core.Router
import ca.bcit.drone3pov.bridge.core.SimulatorStart
import ca.bcit.drone3pov.bridge.core.Telemetry
import ca.bcit.drone3pov.bridge.core.Velocity
import ca.bcit.drone3pov.bridge.core.VideoFeedKind
import ca.bcit.drone3pov.bridge.core.VideoHub
import ca.bcit.drone3pov.bridge.core.VideoSource
import org.junit.After
import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Test
import java.io.InputStream
import java.net.HttpURLConnection
import java.net.ServerSocket
import java.net.URL

/**
 * Runs the real NanoHTTPD server on the laptop and reads GET /v1/video over HTTP, the same way the
 * edge laptop will. Checks that video is streamed as it arrives instead of being buffered.
 * (Only the video path is exercised: the JSON paths use Android's org.json, which isn't available here.)
 */
class HttpVideoStreamTest {
    private val hub = VideoHub(maxViewers = 2, maxQueuedChunks = 64)
    private var requestedFeed: VideoFeedKind? = null

    private val video = object : VideoSource {
        override fun openVideo(feed: VideoFeedKind): InputStream {
            requestedFeed = feed
            return hub.open()
        }
    }

    private val unusedDrone = object : DroneControl {
        override fun connect(): Map<String, Any?> = error("unused")
        override fun takeoff() = error("unused")
        override fun land() = error("unused")
        override fun emergencyStop(): String = error("unused")
        override fun velocity(v: Velocity) = error("unused")
        override fun telemetry(): Telemetry = error("unused")
        override fun startSimulator(start: SimulatorStart): Map<String, Any?> = error("unused")
        override fun stopSimulator(): Map<String, Any?> = error("unused")
    }

    private val port = ServerSocket(0).use { it.localPort }
    private val server = HttpBridgeServer(port, Router(unusedDrone), video).also { it.start(5_000, true) }

    @After
    fun stop() = server.stop()

    private fun connect(query: String = ""): HttpURLConnection =
        (URL("http://127.0.0.1:$port/v1/video$query").openConnection() as HttpURLConnection).apply {
            connectTimeout = 2000
            readTimeout = 2000
        }

    private fun waitForViewer() {
        val deadline = System.currentTimeMillis() + 2000
        while (hub.viewerCount == 0 && System.currentTimeMillis() < deadline) Thread.sleep(10)
        assertEquals(1, hub.viewerCount)
    }

    private fun InputStream.readExactly(n: Int): ByteArray {
        val out = ByteArray(n)
        var got = 0
        while (got < n) {
            val r = read(out, got, n - got)
            check(r != -1) { "stream ended after $got bytes" }
            got += r
        }
        return out
    }

    @Test
    fun streamsVideoAsItArrives() {
        val conn = connect()
        // Publishing happens after the request is open: the bytes must reach the client while the
        // response is still in progress, which is what a live feed needs.
        val stream = Thread {
            waitForViewer()
            hub.publish(byteArrayOf(0, 0, 0, 1, 0x67), 5) // an H.264 start code and an SPS header byte
            Thread.sleep(100)
            hub.publish(byteArrayOf(0, 0, 0, 1, 0x65), 5) // start code and an IDR slice header byte
        }
        val input = conn.inputStream // blocks until headers arrive
        stream.start()

        assertEquals(200, conn.responseCode)
        assertEquals("video/h264", conn.contentType)
        assertArrayEquals(byteArrayOf(0, 0, 0, 1, 0x67, 0, 0, 0, 1, 0x65), input.readExactly(10))
        assertEquals(VideoFeedKind.PRIMARY, requestedFeed)
        conn.disconnect()
        stream.join()
    }

    @Test
    fun feedParameterIsPassedThrough() {
        val conn = connect("?feed=transcoded")
        val publisher = Thread {
            waitForViewer()
            hub.publish(byteArrayOf(1), 1)
        }
        publisher.start()
        assertEquals(200, conn.responseCode)
        conn.inputStream.readExactly(1)
        assertEquals(VideoFeedKind.TRANSCODED, requestedFeed)
        conn.disconnect()
        publisher.join()
    }
}
