"""The app's settings on this PC (backend/i18n.py keeps them in animator_settings.json next to the saved animations).

    GET  /api/settings      {language, language_auto, languages: [codes]} ({languages} only before the first start)
    POST /api/settings      {language: 'de'} -> the settings after the change (unknown names are ignored)
"""
import i18n


def _get(q):
    return {**i18n.settings(), 'languages': list(i18n.LANGUAGES)}


def _post(body, q):
    return {**i18n.save_settings(body), 'languages': list(i18n.LANGUAGES)}


GET = {'settings': _get}
POST = {'settings': _post}
