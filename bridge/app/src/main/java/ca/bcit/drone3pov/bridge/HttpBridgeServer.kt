package ca.bcit.drone3pov.bridge

import ca.bcit.drone3pov.bridge.core.BridgeError
import ca.bcit.drone3pov.bridge.core.Limits
import ca.bcit.drone3pov.bridge.core.Reply
import ca.bcit.drone3pov.bridge.core.Router
import ca.bcit.drone3pov.bridge.core.VideoFeedKind
import ca.bcit.drone3pov.bridge.core.VideoSource
import fi.iki.elonen.NanoHTTPD
import org.json.JSONObject
import java.io.DataInputStream

/**
 * NanoHTTPD front end for [Router].
 *
 * NanoHTTPD serves each connection on its own thread, so a slow request can't hold up
 * /v1/emergency-stop.
 */
class HttpBridgeServer(
    port: Int,
    private val router: Router,
    private val video: VideoSource,
) : NanoHTTPD(port) {

    override fun serve(session: IHTTPSession): Response {
        // Video is a long-lived byte stream, not a JSON reply, so it skips the router.
        if (session.uri.trimEnd('/') == VIDEO_PATH) return serveVideo(session)

        val reply = try {
            val body = if (session.method == Method.POST) readJson(session) else null
            router.handle(session.method.name, session.uri.trimEnd('/'), body)
        } catch (e: BadBody) {
            Reply(e.status, mapOf("ok" to false, "error" to e.message))
        }
        return json(reply)
    }

    /**
     * GET /v1/video[?feed=primary|transcoded]: raw H.264 (Annex B) for as long as the client stays connected.
     * Play it with `ffplay -f h264 http://<phone>:8765/v1/video`, or read it with PyAV on the edge laptop.
     */
    private fun serveVideo(session: IHTTPSession): Response {
        if (session.method != Method.GET) return json(Reply(405, mapOf("ok" to false, "error" to "$VIDEO_PATH takes GET")))
        return try {
            val feed = VideoFeedKind.fromQuery(session.parameters["feed"]?.firstOrNull())
            newChunkedResponse(Response.Status.OK, "video/h264", video.openVideo(feed)).apply {
                addHeader("Cache-Control", "no-store")
            }
        } catch (e: BridgeError) {
            json(Reply(e.status, mapOf("ok" to false, "error" to e.message)))
        }
    }

    private fun json(reply: Reply): Response {
        val status = Response.Status.lookup(reply.status) ?: Response.Status.INTERNAL_ERROR
        return newFixedLengthResponse(status, "application/json", JSONObject(reply.body).toString())
    }

    private fun readJson(session: IHTTPSession): Map<String, Any?> {
        val length = session.headers["content-length"]?.toIntOrNull() ?: 0
        if (length == 0) return emptyMap()
        if (length < 0 || length > Limits.MAX_BODY_BYTES) throw BadBody(413, "body too large")

        val bytes = ByteArray(length)
        DataInputStream(session.inputStream).readFully(bytes)
        val json = try {
            JSONObject(String(bytes, Charsets.UTF_8))
        } catch (e: Exception) {
            throw BadBody(400, "body must be a JSON object")
        }
        return json.keys().asSequence().associateWith { key -> json.get(key).takeUnless { it == JSONObject.NULL } }
    }

    private class BadBody(val status: Int, message: String) : Exception(message)

    companion object {
        const val VIDEO_PATH = "/v1/video"
    }
}
