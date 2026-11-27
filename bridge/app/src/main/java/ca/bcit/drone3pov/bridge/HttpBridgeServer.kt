package ca.bcit.drone3pov.bridge

import ca.bcit.drone3pov.bridge.core.Limits
import ca.bcit.drone3pov.bridge.core.Reply
import ca.bcit.drone3pov.bridge.core.Router
import fi.iki.elonen.NanoHTTPD
import org.json.JSONObject
import java.io.DataInputStream

/**
 * NanoHTTPD front end for [Router].
 *
 * NanoHTTPD serves each connection on its own thread, so a slow request can't hold up
 * /v1/emergency-stop.
 */
class HttpBridgeServer(port: Int, private val router: Router) : NanoHTTPD(port) {

    override fun serve(session: IHTTPSession): Response {
        val reply = try {
            val body = if (session.method == Method.POST) readJson(session) else null
            router.handle(session.method.name, session.uri.trimEnd('/'), body)
        } catch (e: BadBody) {
            Reply(e.status, mapOf("ok" to false, "error" to e.message))
        }
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
}
