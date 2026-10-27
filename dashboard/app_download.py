"""Public page and download for the Android app (https://<site>/app/)."""
from django.conf import settings
from django.http import FileResponse, Http404
from django.shortcuts import render


def _app():
    info = dict(settings.ANDROID_APP)
    path = info['file']
    info['available'] = path.exists()
    info['size_mb'] = round(path.stat().st_size / 1_000_000, 1) if info['available'] else None
    return info


def app_page(request):
    """Download page for students and parents; no login needed."""
    ua = request.META.get('HTTP_USER_AGENT', '')
    return render(request, 'app_download.html', {
        'app': _app(),
        'in_app': 'RadonAcademyApp' in ua,
        'is_android': 'Android' in ua,
        'is_iphone': 'iPhone' in ua or 'iPad' in ua,
    })


def app_download(request):
    app = _app()
    if not app['available']:
        raise Http404("The app isn't available yet.")
    response = FileResponse(open(app['file'], 'rb'), as_attachment=True,
                            filename=f"RadonAcademy-{app['version']}.apk",
                            content_type='application/vnd.android.package-archive')
    response['Cache-Control'] = 'no-cache'
    return response
