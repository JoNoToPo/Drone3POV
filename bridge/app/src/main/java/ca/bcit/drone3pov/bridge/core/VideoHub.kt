package ca.bcit.drone3pov.bridge.core

import java.io.IOException
import java.io.InputStream
import java.util.concurrent.CopyOnWriteArrayList
import java.util.concurrent.LinkedBlockingQueue
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicLong

/**
 * Fans the drone's raw H.264 stream out to the laptops watching GET /v1/video.
 *
 * The DJI SDK hands us video in chunks on its own thread ([publish]). Each viewer gets its own
 * bounded queue, read through an [InputStream] that the HTTP server streams to the socket.
 *
 * Latency beats completeness here: the follow controller steers by these frames, so a viewer that
 * falls behind is disconnected instead of being allowed to build up seconds of delay. It can simply
 * reconnect; the decoder picks up again at the next keyframe.
 */
class VideoHub(
    private val maxViewers: Int = Limits.MAX_VIDEO_VIEWERS,
    private val maxQueuedChunks: Int = Limits.MAX_VIDEO_QUEUE_CHUNKS,
    private val clock: () -> Long = System::currentTimeMillis,
) {
    private val viewers = CopyOnWriteArrayList<Viewer>()
    private val bytesTotal = AtomicLong()
    private val chunksTotal = AtomicLong()
    @Volatile private var lastChunkAt = 0L

    // Rolling one-second byte counter for the status screen and telemetry.
    private var windowStart = 0L
    private var windowBytes = 0L
    @Volatile var bytesPerSecond = 0L; private set

    val viewerCount: Int get() = viewers.size
    val totalBytes: Long get() = bytesTotal.get()

    /** True when video arrived in the last two seconds. */
    fun isFlowing(): Boolean = clock() - lastChunkAt <= 2000

    /** A new viewer. Throws 429 when [maxViewers] are already watching. */
    @Synchronized
    fun open(): Viewer {
        if (viewers.size >= maxViewers) throw BridgeError(429, "too many video viewers (max $maxViewers)")
        return Viewer().also { viewers += it }
    }

    /** Called by the DJI SDK thread with each chunk of video. Never blocks. */
    fun publish(data: ByteArray, size: Int) {
        if (size <= 0) return
        val now = clock()
        lastChunkAt = now
        bytesTotal.addAndGet(size.toLong())
        chunksTotal.incrementAndGet()
        countRate(now, size)

        if (viewers.isEmpty()) return
        // One copy shared by every viewer: the SDK reuses its buffer after this call returns.
        val chunk = data.copyOf(size)
        for (viewer in viewers) {
            if (!viewer.queue.offer(chunk)) {
                viewer.closeBecause("fell behind")
            }
        }
    }

    /** Disconnects every viewer, e.g. when the drone goes away. */
    fun closeAll(reason: String) {
        for (viewer in viewers) viewer.closeBecause(reason)
    }

    @Synchronized
    private fun countRate(now: Long, size: Int) {
        if (now - windowStart >= 1000) {
            bytesPerSecond = windowBytes
            windowStart = now
            windowBytes = 0
        }
        windowBytes += size
    }

    fun status(): Map<String, Any?> = mapOf(
        "video_flowing" to isFlowing(),
        "video_viewers" to viewerCount,
        "video_kbps" to bytesPerSecond * 8 / 1000,
    )

    /** One connected viewer, read by the HTTP server as a byte stream. */
    inner class Viewer : InputStream() {
        internal val queue = LinkedBlockingQueue<ByteArray>(maxQueuedChunks)
        @Volatile private var closed = false
        @Volatile var closeReason: String? = null; private set
        private var current: ByteArray? = null
        private var offset = 0

        internal fun closeBecause(reason: String) {
            if (closed) return
            closeReason = reason
            closed = true
            viewers.remove(this)
            queue.clear()
        }

        override fun read(): Int {
            val one = ByteArray(1)
            return if (read(one, 0, 1) == -1) -1 else one[0].toInt() and 0xff
        }

        /** Returns whatever is ready in the current chunk; blocks only when nothing is queued. */
        override fun read(b: ByteArray, off: Int, len: Int): Int {
            if (len == 0) return 0
            while (current == null || offset >= current!!.size) {
                if (closed) return -1
                current = queue.poll(250, TimeUnit.MILLISECONDS)
                offset = 0
            }
            val chunk = current!!
            val n = minOf(len, chunk.size - offset)
            System.arraycopy(chunk, offset, b, off, n)
            offset += n
            return n
        }

        override fun available(): Int = current?.let { it.size - offset } ?: 0

        /** The HTTP server closes the stream when the laptop disconnects. */
        @Throws(IOException::class)
        override fun close() = closeBecause("viewer disconnected")
    }
}

/** Which DJI video feed to watch. `primary` is the drone's own stream; `transcoded` is re-encoded by the SDK. */
enum class VideoFeedKind {
    PRIMARY, TRANSCODED;

    companion object {
        /** Reads ?feed= from GET /v1/video. Missing means primary. */
        fun fromQuery(value: String?): VideoFeedKind = when (value?.lowercase()) {
            null, "", "primary" -> PRIMARY
            "transcoded" -> TRANSCODED
            else -> throw BridgeError(400, "feed must be primary or transcoded")
        }
    }
}

/** What the HTTP server needs to stream video. DjiDrone is the real one. */
interface VideoSource {
    /** A byte stream of raw H.264 (Annex B). Throws [BridgeError] when no drone is connected. */
    fun openVideo(feed: VideoFeedKind): InputStream
}
