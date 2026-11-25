package ca.bcit.drone3pov.bridge

import android.content.Context
import android.util.Log
import ca.bcit.drone3pov.bridge.core.BridgeError
import ca.bcit.drone3pov.bridge.core.DroneControl
import ca.bcit.drone3pov.bridge.core.Limits
import ca.bcit.drone3pov.bridge.core.Telemetry
import ca.bcit.drone3pov.bridge.core.Velocity
import ca.bcit.drone3pov.bridge.core.VelocityGate
import dji.common.error.DJIError
import dji.common.error.DJISDKError
import dji.common.flightcontroller.FlightControllerState
import dji.common.flightcontroller.FlightMode
import dji.common.flightcontroller.virtualstick.FlightControlData
import dji.common.flightcontroller.virtualstick.FlightCoordinateSystem
import dji.common.flightcontroller.virtualstick.RollPitchControlMode
import dji.common.flightcontroller.virtualstick.VerticalControlMode
import dji.common.flightcontroller.virtualstick.YawControlMode
import dji.sdk.base.BaseComponent
import dji.sdk.base.BaseProduct
import dji.sdk.flightcontroller.FlightController
import dji.sdk.products.Aircraft
import dji.sdk.sdkmanager.DJISDKInitEvent
import dji.sdk.sdkmanager.DJISDKManager
import java.util.concurrent.Executors
import java.util.concurrent.ScheduledExecutorService
import java.util.concurrent.TimeUnit

private const val TAG = "Drone3POV.DjiDrone"

/**
 * Flies the Mini 2 through DJI Mobile SDK v4 virtual sticks.
 *
 * Threading: SDK callbacks arrive on SDK threads, HTTP requests on NanoHTTPD threads, and the
 * stick loop on its own executor. Shared state is @Volatile or lives in [VelocityGate].
 */
class DjiDrone(private val context: Context) : DroneControl {

    private val gate = VelocityGate()
    private val loop: ScheduledExecutorService = Executors.newSingleThreadScheduledExecutor()

    @Volatile var sdkStatus = "not started"; private set
    @Volatile private var registered = false
    @Volatile private var aircraft: Aircraft? = null

    // Cached state, updated by SDK callbacks.
    @Volatile private var batteryPct: Int? = null
    @Volatile private var heightM: Float? = null
    @Volatile private var flying = false
    @Volatile private var motorsOn = false
    @Volatile private var flightMode: FlightMode? = null
    @Volatile private var lastStateAt = 0L

    @Volatile private var virtualStickOn = false
    @Volatile private var enableSticksWhenAirborne = false
    @Volatile private var landingRequested = false
    @Volatile private var lastSendError: String? = null

    /** Short log for the on-screen status. */
    val events = EventLog(40)

    // ---------------------------------------------------------------- SDK setup

    fun start() {
        sdkStatus = "registering"
        DJISDKManager.getInstance().registerApp(context.applicationContext, object : DJISDKManager.SDKManagerCallback {
            override fun onRegister(error: DJIError?) {
                if (error == DJISDKError.REGISTRATION_SUCCESS) {
                    registered = true
                    sdkStatus = "registered, waiting for the RC"
                    events.add("SDK registered")
                    DJISDKManager.getInstance().startConnectionToProduct()
                } else {
                    sdkStatus = "registration failed: ${error?.description}"
                    events.add(sdkStatus)
                }
            }

            override fun onProductDisconnect() {
                events.add("product disconnected")
                detach()
            }

            override fun onProductConnect(product: BaseProduct?) {
                events.add("product connected: ${product?.model?.displayName}")
                attach(product)
            }

            override fun onProductChanged(product: BaseProduct?) = attach(product)

            override fun onComponentChange(
                key: BaseProduct.ComponentKey?,
                old: BaseComponent?,
                new: BaseComponent?,
            ) {
                // The flight controller or battery can show up after the product does.
                attach(DJISDKManager.getInstance().product)
            }

            override fun onInitProcess(event: DJISDKInitEvent?, totalProcess: Int) {}
            override fun onDatabaseDownloadProgress(current: Long, total: Long) {}
        })

        loop.scheduleAtFixedRate({ tick() }, 0, Limits.SEND_PERIOD_MS, TimeUnit.MILLISECONDS)
    }

    fun shutdown() {
        loop.shutdownNow()
        aircraft?.flightController?.setVirtualStickModeEnabled(false, null)
    }

    private fun attach(product: BaseProduct?) {
        val a = product as? Aircraft ?: return
        aircraft = a
        sdkStatus = "connected: ${a.model?.displayName}"
        a.battery?.setStateCallback { s -> batteryPct = s.chargeRemainingInPercent }
        a.flightController?.setStateCallback { s -> onState(a.flightController, s) }
    }

    private fun detach() {
        aircraft = null
        virtualStickOn = false
        enableSticksWhenAirborne = false
        lastStateAt = 0L
        sdkStatus = if (registered) "registered, waiting for the RC" else sdkStatus
    }

    private fun onState(fc: FlightController, s: FlightControllerState) {
        lastStateAt = System.currentTimeMillis()
        heightM = s.aircraftLocation?.altitude
        flying = s.isFlying
        motorsOn = s.areMotorsOn()
        flightMode = s.flightMode

        // Turn on virtual sticks once auto takeoff has finished, not during it.
        if (enableSticksWhenAirborne && s.isFlying && s.flightMode != FlightMode.AUTO_TAKEOFF) {
            enableSticksWhenAirborne = false
            enableVirtualSticks(fc)
        }

        // The Mini 2 pauses about 0.3 m above the ground and waits for confirmation.
        if (landingRequested && s.isLandingConfirmationNeeded) {
            fc.confirmLanding { err -> log("confirm landing", err) }
        }
        if (landingRequested && !s.areMotorsOn()) landingRequested = false
    }

    private fun enableVirtualSticks(fc: FlightController) {
        fc.setRollPitchControlMode(RollPitchControlMode.VELOCITY)
        fc.setYawControlMode(YawControlMode.ANGULAR_VELOCITY)
        fc.setVerticalControlMode(VerticalControlMode.VELOCITY)
        fc.setRollPitchCoordinateSystem(FlightCoordinateSystem.BODY)
        fc.setVirtualStickModeEnabled(true) { err ->
            virtualStickOn = err == null
            log("enable virtual sticks", err)
        }
    }

    // ---------------------------------------------------------------- stick loop

    private fun tick() {
        try {
            val fc = aircraft?.flightController ?: return
            if (!virtualStickOn || !flying) return
            fc.sendVirtualStickFlightControlData(toStickData(gate.next(heightM))) { err ->
                lastSendError = err?.description
            }
        } catch (e: Exception) {
            // An exception would cancel the scheduled loop, so swallow it and keep ticking.
            Log.e(TAG, "tick failed", e)
        }
    }

    /**
     * In MSDK v4 VELOCITY mode with the BODY frame, `roll` is the forward (x) speed and
     * `pitch` is the right (y) speed. The names look swapped but match DJI's VirtualStickView
     * sample. Check this with the propellers off before the first flight.
     */
    private fun toStickData(v: Velocity) = FlightControlData(
        /* pitch = */ v.rightMps,
        /* roll = */ v.forwardMps,
        /* yaw = */ v.yawDps,
        /* verticalThrottle = */ v.upMps,
    )

    // ---------------------------------------------------------------- DroneControl

    override fun connect(): Map<String, Any?> {
        val fc = requireFlightController()
        gate.rearm()
        events.add("connect: emergency stop cleared")
        return mapOf(
            "product" to aircraft?.model?.displayName,
            "flying" to flying,
            "virtual_stick" to virtualStickOn,
            "fc_connected" to fc.isConnected,
        )
    }

    override fun takeoff() {
        val fc = requireFlightController()
        if (gate.stopped) throw BridgeError(409, "emergency stop is latched; POST /v1/connect to re-arm")
        if (flying) {
            // Already up (maybe the pilot took off by hand). Just make sure the sticks are on.
            if (!virtualStickOn) enableVirtualSticks(fc)
            return
        }
        gate.clear()
        landingRequested = false
        fc.startTakeoff { err ->
            log("takeoff", err)
            if (err == null) enableSticksWhenAirborne = true
        }
    }

    override fun land() {
        val fc = requireFlightController()
        gate.clear()
        if (!flying) return
        landingRequested = true
        // Hand control back from virtual sticks first, then auto-land.
        fc.setVirtualStickModeEnabled(false) { err ->
            virtualStickOn = false
            log("disable virtual sticks for landing", err)
            fc.startLanding { e -> log("land", e) }
        }
    }

    override fun emergencyStop(): String {
        // Latch first, so no velocity command can slip in after this point.
        gate.stop()
        events.add("EMERGENCY STOP")
        val fc = aircraft?.flightController ?: return "no_aircraft"

        // Brake now instead of waiting up to one tick.
        if (virtualStickOn) fc.sendVirtualStickFlightControlData(toStickData(Velocity.ZERO), null)

        return when {
            !motorsOn -> "already_stopped"
            !flying -> {
                fc.turnOffMotors { err -> log("motors off", err) }
                "motors_off"
            }
            else -> {
                // MSDK v4 can't cut the motors in flight on the Mini 2. Hover, then land in place.
                landingRequested = true
                fc.setVirtualStickModeEnabled(false) { err ->
                    virtualStickOn = false
                    fc.startLanding { e -> log("emergency land", e) }
                    if (err != null) log("disable virtual sticks", err)
                }
                "hover_then_land"
            }
        }
    }

    override fun velocity(v: Velocity) {
        requireFlightController()
        if (!flying) throw BridgeError(409, "not flying")
        if (landingRequested) throw BridgeError(409, "landing")
        if (!virtualStickOn) throw BridgeError(409, "virtual sticks not enabled yet")
        gate.submit(v)
    }

    override fun telemetry(): Telemetry {
        val fc = aircraft?.flightController
        val fresh = System.currentTimeMillis() - lastStateAt <= Limits.STATE_STALE_MS
        val linkOk = fc != null && fc.isConnected && fresh
        return Telemetry(
            // mini2.py needs numbers here, so unknown reads as 0 with link_ok false.
            batteryPct = batteryPct ?: 0,
            heightM = heightM ?: 0f,
            linkOk = linkOk,
            extra = mapOf(
                "sdk" to sdkStatus,
                "flying" to flying,
                "motors_on" to motorsOn,
                "flight_mode" to flightMode?.name,
                "virtual_stick" to virtualStickOn,
                "landing" to landingRequested,
                "estopped" to gate.stopped,
                "last_send_error" to lastSendError,
            ),
        )
    }

    // ---------------------------------------------------------------- helpers

    private fun requireFlightController(): FlightController {
        if (!registered) throw BridgeError(503, "DJI SDK not registered ($sdkStatus). The phone needs internet on first run.")
        val a = aircraft ?: throw BridgeError(503, "Mini 2 not connected. Plug the phone into the RC and power on the drone.")
        return a.flightController ?: throw BridgeError(503, "flight controller not available yet")
    }

    private fun log(what: String, err: DJIError?) {
        val line = if (err == null) "$what: ok" else "$what failed: ${err.description}"
        Log.i(TAG, line)
        events.add(line)
    }
}

/** Fixed-size, thread-safe list of recent events for the status screen. */
class EventLog(private val size: Int) {
    private val lines = ArrayDeque<String>()

    @Synchronized
    fun add(line: String) {
        val t = java.text.SimpleDateFormat("HH:mm:ss", java.util.Locale.US).format(java.util.Date())
        lines.addFirst("$t  $line")
        while (lines.size > size) lines.removeLast()
    }

    @Synchronized
    fun snapshot(): List<String> = lines.toList()
}
