package com.radonacademy.app

import android.content.Context
import android.webkit.CookieManager
import androidx.work.Constraints
import androidx.work.CoroutineWorker
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.ExistingWorkPolicy
import androidx.work.NetworkType
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder
import java.util.concurrent.TimeUnit

/**
 * Runs about every 15 minutes in the background (when there's internet) and asks
 * the website for new class test results for the logged-in student or parent,
 * then shows a notification for each.
 *
 * The website returns a "cursor" (a time) with every answer; the next check asks
 * only for results after it. The very first check just stores the cursor, so a
 * fresh install doesn't notify about old results.
 */
class ResultsCheckWorker(context: Context, params: WorkerParameters) : CoroutineWorker(context, params) {

    override suspend fun doWork(): Result {
        val prefs = applicationContext.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        val site = BuildConfig.START_URL.trimEnd('/')

        // The login cookie is shared with the app's web view. CookieManager is read on the main thread.
        val cookie = withContext(Dispatchers.Main) {
            try { CookieManager.getInstance().getCookie(site) } catch (e: Exception) { null }
        }
        if (cookie.isNullOrBlank()) return Result.success()   // not logged in yet

        return withContext(Dispatchers.IO) {
            val since = prefs.getString(KEY_CURSOR, null)
            val query = if (since != null) "?since=" + URLEncoder.encode(since, "UTF-8") else ""
            var connection: HttpURLConnection? = null
            try {
                connection = (URL("$site/api/app/notifications/$query").openConnection() as HttpURLConnection).apply {
                    connectTimeout = 15_000
                    readTimeout = 15_000
                    instanceFollowRedirects = false
                    setRequestProperty("Cookie", cookie)
                    setRequestProperty("Accept", "application/json")
                    setRequestProperty("User-Agent", "RadonAcademyApp/${BuildConfig.VERSION_NAME}")
                }
                when (connection.responseCode) {
                    HttpURLConnection.HTTP_OK -> {
                        val json = JSONObject(connection.inputStream.bufferedReader().use { it.readText() })
                        val items = json.optJSONArray("items")
                        if (since != null && items != null) {
                            for (i in 0 until items.length()) {
                                val item = items.getJSONObject(i)
                                Notifications.showResult(
                                    applicationContext,
                                    id = item.optInt("id", i),
                                    title = item.optString("title"),
                                    body = item.optString("body"),
                                    path = item.optString("url", "/"),
                                )
                            }
                        }
                        json.optString("cursor").takeIf { it.isNotBlank() }?.let {
                            prefs.edit().putString(KEY_CURSOR, it).apply()
                        }
                        Result.success()
                    }
                    // Logged out (or the session expired): try again at the next scheduled check.
                    else -> Result.success()
                }
            } catch (e: IOException) {
                Result.retry()
            } catch (e: Exception) {
                Result.success()
            } finally {
                connection?.disconnect()
            }
        }
    }

    companion object {
        private const val PREFS = "notifications"
        private const val KEY_CURSOR = "cursor"
        private const val WORK_NAME = "class-test-results-check"

        private fun network() =
            Constraints.Builder().setRequiredNetworkType(NetworkType.CONNECTED).build()

        /** Check once soon, e.g. right after logging in, so the starting point is set. */
        fun checkNow(context: Context) {
            val request = OneTimeWorkRequestBuilder<ResultsCheckWorker>().setConstraints(network()).build()
            WorkManager.getInstance(context)
                .enqueueUniqueWork("$WORK_NAME-now", ExistingWorkPolicy.KEEP, request)
        }

        /** Schedule the periodic check (safe to call on every app start). */
        fun schedule(context: Context) {
            val request = PeriodicWorkRequestBuilder<ResultsCheckWorker>(15, TimeUnit.MINUTES)
                .setConstraints(network())
                .build()
            WorkManager.getInstance(context)
                .enqueueUniquePeriodicWork(WORK_NAME, ExistingPeriodicWorkPolicy.KEEP, request)
        }
    }
}
