# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Michele Salerno e i contributori di EduWISP
"""Catalogo iniziale della piattaforma (ADR-0019).

Solo nomi di pacchetto verificati o molto noti: un nome sbagliato non blocca nulla, ma darebbe
una falsa sicurezza. L'amministratore di sistema può aggiungerne altri dall'amministrazione.
"""

from django.db import migrations

CONSENTITE = {
    "istruzione": [
        ("Google Classroom", "com.google.android.apps.classroom"),
        ("MyLIM (Loescher)", "it.maieuticallabs.mylim"),
        ("Booktab (Zanichelli)", "it.zanichelli.booktab"),
        # Argo: registro elettronico per famiglie e studenti. Pacchetto da verificare sul Play Store.
        ("didUP - Famiglia (Argo)", "it.argosoft.didup.famiglia.new"),
        ("GeoGebra Calculator Suite", "org.geogebra.android.calculator.suite"),
        ("GeoGebra Classic", "org.geogebra.android"),
        ("GeoGebra Geometria", "org.geogebra.android.geometry"),
        ("GeoGebra 3D", "org.geogebra.android.g3d"),
        ("Desmos", "com.desmos.calculator"),
        ("Khan Academy", "org.khanacademy.android"),
        ("Duolingo", "com.duolingo"),
        ("Quizlet", "com.quizlet.quizletandroid"),
        ("Kahoot!", "no.mobitroll.kahoot.android"),
        ("AnkiDroid", "com.ichi2.anki"),
        ("ScratchJr", "org.scratchjr.android"),
        ("Stellarium", "com.noctuasoftware.stellarium_free"),
        ("Photomath", "com.microblink.photomath"),
        ("Wikipedia", "org.wikipedia"),
        ("Google Traduttore", "com.google.android.apps.translate"),
    ],
    "ufficio": [
        ("Microsoft 365 (Office)", "com.microsoft.office.officehubrow"),
        ("Microsoft Word", "com.microsoft.office.word"),
        ("Microsoft Excel", "com.microsoft.office.excel"),
        ("Microsoft PowerPoint", "com.microsoft.office.powerpoint"),
        ("Microsoft OneNote", "com.microsoft.office.onenote"),
        ("Google Drive", "com.google.android.apps.docs"),
        ("Google Documenti", "com.google.android.apps.docs.editors.docs"),
        ("Google Fogli", "com.google.android.apps.docs.editors.sheets"),
        ("Google Presentazioni", "com.google.android.apps.docs.editors.slides"),
        ("Collabora Office", "com.collabora.libreoffice"),
    ],
    "comunicazione": [
        ("Microsoft Teams", "com.microsoft.teams"),
        ("Google Meet", "com.google.android.apps.tachyon"),
        ("WhatsApp", "com.whatsapp"),
    ],
    "navigazione": [
        ("Firefox", "org.mozilla.firefox"),
    ],
}

VIETATE = {
    "social": [
        ("TikTok", "com.zhiliaoapp.musically"),
        ("TikTok", "com.ss.android.ugc.trill"),
        ("TikTok Lite", "com.zhiliaoapp.musically.go"),
        ("Facebook", "com.facebook.katana"),
        ("Facebook Lite", "com.facebook.lite"),
        ("Messenger", "com.facebook.orca"),
        ("Instagram", "com.instagram.android"),
        ("Instagram Lite", "com.instagram.lite"),
        ("Threads", "com.instagram.barcelona"),
        ("Snapchat", "com.snapchat.android"),
        ("X (Twitter)", "com.twitter.android"),
        ("BeReal", "com.bereal.ft"),
        ("Reddit", "com.reddit.frontpage"),
        ("Tumblr", "com.tumblr"),
        ("Pinterest", "com.pinterest"),
        ("Discord", "com.discord"),
        ("Twitch", "tv.twitch.android.app"),
        ("Likee", "video.like"),
        ("Kwai", "com.kwai.video"),
        ("Bigo Live", "sg.bigo.live"),
        ("Yubo", "co.yellw.yellowapp"),
    ],
    "incontri": [
        ("Tinder", "com.tinder"),
        ("Bumble", "com.bumble.app"),
        ("Grindr", "com.grindrapp.android"),
    ],
    "tor": [
        ("Tor Browser", "org.torproject.torbrowser"),
        ("Orbot", "org.torproject.android"),
        ("Orfox", "info.guardianproject.orfox"),
    ],
    "vpn": [
        ("Opera (con VPN integrata)", "com.opera.browser"),
        ("Aloha Browser (con VPN integrata)", "com.aloha.browser"),
        ("Proton VPN", "ch.protonvpn.android"),
        ("NordVPN", "com.nordvpn.android"),
        ("ExpressVPN", "com.expressvpn.vpn"),
        ("Surfshark", "com.surfshark.vpnclient.android"),
        ("Mullvad VPN", "net.mullvad.mullvadvpn"),
        ("Private Internet Access", "com.privateinternetaccess.android"),
        ("TunnelBear", "com.tunnelbear.android"),
        ("Windscribe", "com.windscribe.vpn"),
        ("Hotspot Shield", "hotspotshield.android.vpn"),
        ("Turbo VPN", "free.vpn.unblock.proxy.turbovpn"),
        ("Psiphon", "com.psiphon3"),
        ("Psiphon Pro", "com.psiphon3.subscription"),
        ("Cloudflare 1.1.1.1 + WARP", "com.cloudflare.onedotonedotonedotone"),
        ("Mozilla VPN", "org.mozilla.firefox.vpn"),
        ("OpenVPN for Android", "de.blinkt.openvpn"),
        ("OpenVPN Connect", "net.openvpn.openvpn"),
        ("WireGuard", "com.wireguard.android"),
        ("v2rayNG", "com.v2ray.ang"),
    ],
}


def carica(apps, schema_editor):
    PlatformApp = apps.get_model("eduwisp_apps", "PlatformApp")
    Versione = apps.get_model("eduwisp_apps", "PlatformCatalogVersion")
    for status, gruppi in (("consentita", CONSENTITE), ("vietata", VIETATE)):
        for categoria, elenco in gruppi.items():
            for nome, pacchetto in elenco:
                PlatformApp.objects.update_or_create(
                    platform="android",
                    identifier=pacchetto,
                    defaults={"name": nome, "category": categoria, "status": status},
                )
    Versione.objects.update_or_create(pk=1, defaults={"version": 1})


class Migration(migrations.Migration):
    dependencies = [("eduwisp_apps", "0002_catalogo_piattaforma")]
    operations = [migrations.RunPython(carica, migrations.RunPython.noop)]
