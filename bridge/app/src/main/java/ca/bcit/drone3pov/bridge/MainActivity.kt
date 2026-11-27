package ca.bcit.drone3pov.bridge

import android.Manifest
import android.app.Activity
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Color
import android.graphics.Typeface
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.view.Gravity
import android.view.ViewGroup.LayoutParams.MATCH_PARENT
import android.view.ViewGroup.LayoutParams.WRAP_CONTENT
import android.view.WindowManager
import android.widget.Button
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView

/**
 * Status screen for the phone on the RC. Shows the URL to give the edge laptop, live
 * telemetry and recent events, plus an on-screen emergency stop and land.
 */
class MainActivity : Activity() {
    private val handler = Handler(Looper.getMainLooper())
    private lateinit var status: TextView

    private val refresh = object : Runnable {
        override fun run() {
            status.text = statusText()
            handler.postDelayed(this, 500)
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        setContentView(layout())
        requestPermissionsThenStart()
    }

    override fun onResume() {
        super.onResume()
        handler.post(refresh)
    }

    override fun onPause() {
        handler.removeCallbacks(refresh)
        super.onPause()
    }

    // ------------------------------------------------------------- permissions

    private val needed: Array<String>
        get() = buildList {
            add(Manifest.permission.ACCESS_FINE_LOCATION)
            add(Manifest.permission.ACCESS_COARSE_LOCATION)
            add(Manifest.permission.READ_PHONE_STATE)
            if (Build.VERSION.SDK_INT <= Build.VERSION_CODES.P) {
                add(Manifest.permission.WRITE_EXTERNAL_STORAGE)
                add(Manifest.permission.READ_EXTERNAL_STORAGE)
            }
        }.toTypedArray()

    private fun requestPermissionsThenStart() {
        val missing = needed.filter { checkSelfPermission(it) != PackageManager.PERMISSION_GRANTED }
        if (missing.isEmpty()) startBridge() else requestPermissions(missing.toTypedArray(), REQUEST_PERMISSIONS)
    }

    override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<out String>, results: IntArray) {
        super.onRequestPermissionsResult(requestCode, permissions, results)
        // DJI registration fails without these. Start anyway so the screen explains why.
        startBridge()
    }

    private fun startBridge() {
        val intent = Intent(this, BridgeService::class.java)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) startForegroundService(intent) else startService(intent)
    }

    // ------------------------------------------------------------- UI

    private fun layout(): LinearLayout {
        val pad = (16 * resources.displayMetrics.density).toInt()

        val stop = Button(this).apply {
            text = "EMERGENCY STOP"
            textSize = 22f
            setTextColor(Color.WHITE)
            setBackgroundColor(Color.rgb(200, 30, 30))
            setOnClickListener { Thread { Bridge.drone?.emergencyStop() }.start() }
        }
        val land = Button(this).apply {
            text = "Land"
            setOnClickListener { Thread { runCatching { Bridge.drone?.land() } }.start() }
        }

        status = TextView(this).apply {
            typeface = Typeface.MONOSPACE
            textSize = 13f
            setPadding(0, pad, 0, 0)
        }

        return LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.TOP
            setPadding(pad, pad, pad, pad)
            addView(stop, LinearLayout.LayoutParams(MATCH_PARENT, (88 * resources.displayMetrics.density).toInt()))
            addView(land, LinearLayout.LayoutParams(MATCH_PARENT, WRAP_CONTENT))
            addView(ScrollView(context).apply { addView(status) }, LinearLayout.LayoutParams(MATCH_PARENT, 0, 1f))
        }
    }

    private fun statusText(): String {
        val drone = Bridge.drone ?: return "Starting…"
        val t = drone.telemetry()
        return buildString {
            if (t.extra["simulator_active"] == true) {
                appendLine("*** SIMULATOR ON: the drone stays on the ground. Propellers must be off. ***")
                appendLine()
            }
            appendLine("BRIDGE_URL")
            Bridge.addresses().ifEmpty { listOf("(no network)") }.forEach { appendLine("  $it") }
            Bridge.serverError?.let { appendLine("HTTP server error: $it") }
            appendLine()
            appendLine("SDK        ${drone.sdkStatus}")
            appendLine("link_ok    ${t.linkOk}")
            appendLine("battery    ${t.batteryPct}%")
            appendLine("height     ${"%.2f".format(t.heightM)} m")
            for ((k, v) in t.extra) if (k != "sdk") appendLine("${k.padEnd(10)} $v")
            appendLine()
            drone.events.snapshot().forEach { appendLine(it) }
        }
    }

    companion object {
        private const val REQUEST_PERMISSIONS = 1
    }
}
