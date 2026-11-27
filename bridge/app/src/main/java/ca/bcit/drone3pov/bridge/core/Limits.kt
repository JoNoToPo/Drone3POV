package ca.bcit.drone3pov.bridge.core

/**
 * Hard limits enforced in the bridge, the last stop before the drone.
 *
 * Speed, yaw and height values mirror api/app/safety.py and api/app/mini2.py.
 * If you change one side, change the other.
 */
object Limits {
    const val MAX_SPEED_MPS = 1.0f
    const val MAX_YAW_DPS = 90.0f

    /** No climbing above this height (m above the takeoff point). */
    const val MAX_HEIGHT_M = 2.5f

    /** No velocity descent below this height. Landing goes through /v1/land. */
    const val MIN_HEIGHT_M = 0.5f

    /** A velocity command older than this is dropped and the drone hovers. */
    const val COMMAND_TIMEOUT_MS = 300L

    /** DJI wants virtual-stick data at 5 to 25 Hz. 20 Hz leaves some margin. */
    const val SEND_PERIOD_MS = 50L

    /** Flight controller state older than this counts as a lost link. */
    const val STATE_STALE_MS = 1000L

    /** Request bodies are four numbers. Anything bigger is refused. */
    const val MAX_BODY_BYTES = 4096

    const val PORT = 8765

    /** At most this many laptops can watch GET /v1/video at once (the edge laptop plus one viewer). */
    const val MAX_VIDEO_VIEWERS = 2

    /**
     * Video chunks a viewer may have waiting. A viewer further behind than this is disconnected,
     * so the follow controller never steers by stale frames.
     */
    const val MAX_VIDEO_QUEUE_CHUNKS = 64
}
