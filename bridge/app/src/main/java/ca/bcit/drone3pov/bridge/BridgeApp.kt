package ca.bcit.drone3pov.bridge

import android.app.Application
import android.content.Context

class BridgeApp : Application() {
    override fun attachBaseContext(base: Context) {
        super.attachBaseContext(base)
        // MSDK v4 has to load its classes before anything touches the SDK.
        // Since 4.16 the loader is com.cySdkyc.clx.Helper; older docs and samples say com.secneo.sdk.Helper.
        com.cySdkyc.clx.Helper.install(this)
    }
}
