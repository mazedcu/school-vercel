package com.radonacademy.app

import android.Manifest
import android.annotation.SuppressLint
import android.app.DownloadManager
import android.content.ActivityNotFoundException
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Bitmap
import android.net.Uri
import android.net.http.SslError
import android.os.Build
import android.os.Bundle
import android.os.Environment
import android.print.PrintAttributes
import android.print.PrintManager
import android.view.View
import android.webkit.CookieManager
import android.webkit.JavascriptInterface
import android.webkit.SslErrorHandler
import android.webkit.URLUtil
import android.webkit.ValueCallback
import android.webkit.WebChromeClient
import android.webkit.WebResourceError
import android.webkit.WebResourceRequest
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.Button
import android.widget.ProgressBar
import android.widget.TextView
import android.widget.Toast
import androidx.activity.OnBackPressedCallback
import androidx.activity.SystemBarStyle
import androidx.activity.addCallback
import androidx.activity.enableEdgeToEdge
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import androidx.core.view.ViewCompat
import androidx.core.view.WindowInsetsCompat
import androidx.swiperefreshlayout.widget.SwipeRefreshLayout

/**
 * Shows the Radon Academy website full screen.
 *
 * Besides displaying pages it makes the parts of the site that a plain WebView
 * can't handle work: printing report cards (window.print), PDF downloads that
 * need the login session, photo uploads, the back button, pull-to-refresh and
 * an offline screen. It also schedules [ResultsCheckWorker], which notifies
 * students and parents of new class test results.
 */
class MainActivity : AppCompatActivity() {

    private lateinit var webView: WebView
    private lateinit var swipe: SwipeRefreshLayout
    private lateinit var progress: ProgressBar
    private lateinit var offline: View
    private lateinit var offlineTitle: TextView
    private lateinit var offlineMessage: TextView

    private lateinit var backCallback: OnBackPressedCallback

    private var fileCallback: ValueCallback<Array<Uri>>? = null
    private var mainFrameFailed = false

    private val askNotificationPermission =
        registerForActivityResult(ActivityResultContracts.RequestPermission()) { }

    private val pickFiles =
        registerForActivityResult(ActivityResultContracts.StartActivityForResult()) { result ->
            val data = result.data
            val uris: Array<Uri>? = when {
                result.resultCode != RESULT_OK || data == null -> null
                data.clipData != null -> {
                    val clip = data.clipData!!
                    Array(clip.itemCount) { clip.getItemAt(it).uri }
                }
                data.data != null -> arrayOf(data.data!!)
                else -> null
            }
            fileCallback?.onReceiveValue(uris)
            fileCallback = null
        }

    override fun onCreate(savedInstanceState: Bundle?) {
        val bar = ContextCompat.getColor(this, R.color.brand_dark)
        enableEdgeToEdge(
            statusBarStyle = SystemBarStyle.dark(bar),
            navigationBarStyle = SystemBarStyle.dark(bar),
        )
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        Notifications.createChannels(this)
        ResultsCheckWorker.schedule(this)

        webView = findViewById(R.id.webview)
        swipe = findViewById(R.id.swipe)
        progress = findViewById(R.id.progress)
        offline = findViewById(R.id.offline)
        offlineTitle = findViewById(R.id.offline_title)
        offlineMessage = findViewById(R.id.offline_message)

        // Keep the page clear of the status bar, navigation bar and keyboard.
        ViewCompat.setOnApplyWindowInsetsListener(findViewById(R.id.root)) { v, insets ->
            val bars = insets.getInsets(
                WindowInsetsCompat.Type.systemBars() or WindowInsetsCompat.Type.ime()
            )
            v.setPadding(bars.left, bars.top, bars.right, bars.bottom)
            WindowInsetsCompat.CONSUMED
        }

        setUpWebView()

        swipe.setColorSchemeColors(ContextCompat.getColor(this, R.color.brand))
        swipe.setOnRefreshListener { webView.reload() }
        // Only pull to refresh when the page itself is scrolled to the top.
        swipe.setOnChildScrollUpCallback { _, _ -> webView.scrollY > 0 }

        findViewById<Button>(R.id.retry).setOnClickListener {
            offline.visibility = View.GONE
            if (webView.url.isNullOrEmpty()) webView.loadUrl(BuildConfig.START_URL) else webView.reload()
        }

        // Back goes to the previous page; on the first page it leaves the app as usual.
        // Enabled only while there is a page to go back to (kept up to date below).
        backCallback = onBackPressedDispatcher.addCallback(this, enabled = false) {
            webView.goBack()
        }

        if (savedInstanceState == null || webView.restoreState(savedInstanceState) == null) {
            webView.loadUrl(siteUrlFrom(intent) ?: BuildConfig.START_URL)
        }
        backCallback.isEnabled = webView.canGoBack()
    }

    @SuppressLint("SetJavaScriptEnabled")
    private fun setUpWebView() {
        with(webView.settings) {
            javaScriptEnabled = true
            domStorageEnabled = true
            loadWithOverviewMode = true
            useWideViewPort = true
            builtInZoomControls = true      // pinch to zoom wide tables and printouts
            displayZoomControls = false
            setSupportMultipleWindows(false) // "open in new tab" links open in the app
            mixedContentMode = WebSettings.MIXED_CONTENT_NEVER_ALLOW
            allowFileAccess = false
            allowContentAccess = false
            mediaPlaybackRequiresUserGesture = true
            // Lets the website tell it's running inside the app if it ever needs to.
            userAgentString = "$userAgentString RadonAcademyApp/${BuildConfig.VERSION_NAME}"
        }

        CookieManager.getInstance().apply {
            setAcceptCookie(true)                         // stay logged in
            setAcceptThirdPartyCookies(webView, false)
        }

        webView.addJavascriptInterface(AppBridge(), "RadonApp")
        webView.webViewClient = SiteClient()
        webView.webChromeClient = ChromeClient()
        webView.setDownloadListener { url, userAgent, contentDisposition, mimeType, _ ->
            download(url, userAgent, contentDisposition, mimeType)
        }
    }

    // ── Links ───────────────────────────────────────────────────────────────

    private fun isOwnSite(uri: Uri): Boolean {
        val host = uri.host ?: return false
        val site = BuildConfig.SITE_HOST
        return (uri.scheme == "https" || uri.scheme == "http") &&
            (host.equals(site, ignoreCase = true) || host.endsWith(".$site", ignoreCase = true))
    }

    private fun siteUrlFrom(intent: Intent?): String? {
        val uri = intent?.data ?: return null
        return if (intent.action == Intent.ACTION_VIEW && isOwnSite(uri)) uri.toString() else null
    }

    /** Phone numbers, email, WhatsApp, maps and other websites open in their own apps. */
    private fun openOutside(uri: Uri) {
        try {
            val intent = if (uri.scheme == "intent") {
                Intent.parseUri(uri.toString(), Intent.URI_INTENT_SCHEME).apply {
                    addCategory(Intent.CATEGORY_BROWSABLE)
                    component = null
                    selector = null
                }
            } else {
                Intent(Intent.ACTION_VIEW, uri)
            }
            startActivity(intent)
        } catch (e: ActivityNotFoundException) {
            Toast.makeText(this, R.string.no_app_for_link, Toast.LENGTH_SHORT).show()
        } catch (e: Exception) {
            Toast.makeText(this, R.string.no_app_for_link, Toast.LENGTH_SHORT).show()
        }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        siteUrlFrom(intent)?.let { webView.loadUrl(it) }
    }

    // ── Result notifications ────────────────────────────────────────────────

    /**
     * When a student or parent reaches their home page (so they're logged in): check for
     * results once, and on Android 13+ ask once for permission to show notifications.
     */
    private fun onHomePageShown(url: String) {
        val path = Uri.parse(url).path ?: return
        if (!path.startsWith("/student_dashboard") && !path.startsWith("/parent_dashboard")) return
        ResultsCheckWorker.checkNow(this)
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.TIRAMISU) return
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS) ==
            PackageManager.PERMISSION_GRANTED
        ) return
        val prefs = getSharedPreferences("notifications", MODE_PRIVATE)
        if (prefs.getBoolean("asked_permission", false)) return
        prefs.edit().putBoolean("asked_permission", true).apply()
        askNotificationPermission.launch(Manifest.permission.POST_NOTIFICATIONS)
    }

    // ── Downloads (PDF timetables, ID cards, lesson plans…) ─────────────────

    private fun download(url: String, userAgent: String?, contentDisposition: String?, mimeType: String?) {
        try {
            val name = URLUtil.guessFileName(url, contentDisposition, mimeType)
            val request = DownloadManager.Request(Uri.parse(url)).apply {
                setMimeType(mimeType)
                // Send the login session so protected files download.
                CookieManager.getInstance().getCookie(url)?.let { addRequestHeader("Cookie", it) }
                userAgent?.let { addRequestHeader("User-Agent", it) }
                setTitle(name)
                setNotificationVisibility(DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED)
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                    setDestinationInExternalPublicDir(Environment.DIRECTORY_DOWNLOADS, name)
                } else {
                    // Older Android needs a storage permission for the shared Downloads folder;
                    // the app's own folder needs none, and the notification still opens the file.
                    setDestinationInExternalFilesDir(this@MainActivity, Environment.DIRECTORY_DOWNLOADS, name)
                }
            }
            getSystemService(DownloadManager::class.java).enqueue(request)
            Toast.makeText(this, getString(R.string.download_started, name), Toast.LENGTH_SHORT).show()
        } catch (e: Exception) {
            Toast.makeText(this, R.string.download_failed, Toast.LENGTH_SHORT).show()
        }
    }

    // ── Printing (report cards, CT reports, receipts) ───────────────────────

    private fun printPage() {
        val title = webView.title?.takeIf { it.isNotBlank() } ?: getString(R.string.app_name)
        val printManager = getSystemService(PrintManager::class.java)
        val attributes = PrintAttributes.Builder()
            .setMediaSize(PrintAttributes.MediaSize.ISO_A4)
            .build()
        printManager.print(title, webView.createPrintDocumentAdapter(title), attributes)
    }

    /** Called from the website's JavaScript (see [SiteClient.onPageFinished]). */
    private inner class AppBridge {
        @JavascriptInterface
        fun print() = runOnUiThread { printPage() }

        @JavascriptInterface
        fun close() = runOnUiThread { if (webView.canGoBack()) webView.goBack() }
    }

    // ── Page loading ────────────────────────────────────────────────────────

    private inner class SiteClient : WebViewClient() {

        override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean {
            val uri = request.url
            if (isOwnSite(uri)) return false   // stay in the app
            openOutside(uri)
            return true
        }

        override fun doUpdateVisitedHistory(view: WebView, url: String?, isReload: Boolean) {
            backCallback.isEnabled = view.canGoBack()
        }

        override fun onPageStarted(view: WebView, url: String?, favicon: Bitmap?) {
            mainFrameFailed = false
            progress.visibility = View.VISIBLE
        }

        override fun onPageFinished(view: WebView, url: String?) {
            progress.visibility = View.GONE
            swipe.isRefreshing = false
            offline.visibility = if (mainFrameFailed) View.VISIBLE else View.GONE
            CookieManager.getInstance().flush()
            if (url != null && !mainFrameFailed) onHomePageShown(url)
            if (url != null && isOwnSite(Uri.parse(url))) {
                // A WebView ignores window.print() and window.close(); route them to the app so
                // "Print or save as PDF" opens Android's print dialog and "Close" goes back.
                view.evaluateJavascript(
                    "window.print=function(){RadonApp.print();};" +
                        "window.close=function(){RadonApp.close();};",
                    null
                )
            }
        }

        override fun onReceivedError(view: WebView, request: WebResourceRequest, error: WebResourceError) {
            if (request.isForMainFrame) {
                mainFrameFailed = true
                offlineTitle.setText(R.string.offline_title)
                offlineMessage.setText(R.string.offline_message)
            }
        }

        @SuppressLint("WebViewClientOnReceivedSslError")
        override fun onReceivedSslError(view: WebView, handler: SslErrorHandler, error: SslError) {
            // Never load a page whose certificate can't be trusted.
            handler.cancel()
            mainFrameFailed = true
            offlineTitle.setText(R.string.secure_error_title)
            offlineMessage.setText(R.string.secure_error_message)
            offline.visibility = View.VISIBLE
            swipe.isRefreshing = false
            progress.visibility = View.GONE
        }
    }

    private inner class ChromeClient : WebChromeClient() {

        override fun onProgressChanged(view: WebView, newProgress: Int) {
            progress.progress = newProgress
            if (newProgress >= 100) progress.visibility = View.GONE
        }

        /** Photo and document uploads from forms. */
        override fun onShowFileChooser(
            view: WebView,
            callback: ValueCallback<Array<Uri>>,
            params: WebChromeClient.FileChooserParams,
        ): Boolean {
            fileCallback?.onReceiveValue(null)
            fileCallback = callback
            val chooser = params.createIntent().apply {
                if (params.mode == WebChromeClient.FileChooserParams.MODE_OPEN_MULTIPLE) {
                    putExtra(Intent.EXTRA_ALLOW_MULTIPLE, true)
                }
            }
            return try {
                pickFiles.launch(Intent.createChooser(chooser, getString(R.string.choose_file)))
                true
            } catch (e: ActivityNotFoundException) {
                fileCallback = null
                false
            }
        }
    }

    // ── Lifecycle ───────────────────────────────────────────────────────────

    override fun onSaveInstanceState(outState: Bundle) {
        super.onSaveInstanceState(outState)
        webView.saveState(outState)
    }

    override fun onResume() {
        super.onResume()
        webView.onResume()
    }

    override fun onPause() {
        webView.onPause()
        CookieManager.getInstance().flush()
        super.onPause()
    }

    override fun onDestroy() {
        fileCallback?.onReceiveValue(null)
        fileCallback = null
        webView.destroy()
        super.onDestroy()
    }
}
