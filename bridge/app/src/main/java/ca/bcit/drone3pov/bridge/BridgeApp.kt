package ca.bcit.drone3pov.bridge

import android.app.Application
import android.content.Context

class BridgeApp : Application() {
    override fun attachBaseContext(base: Context) {
        super.attachBaseContext(base)
        // MSDK v4 has to load its classes before anything touches the SDK.
        com.secneo.sdk.Helper.install(this)
    }
}
