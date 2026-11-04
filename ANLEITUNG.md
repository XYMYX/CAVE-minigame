# Anleitung: heute streamen

Die lange deutsche Fassung steht in [README.de.md](README.de.md). Die englische README ist [README.md](README.md). Das hier ist die Reihenfolge am Stream-Tag.

Die Texte im Fenster sind Englisch, solange in `config.yaml` `language: en` steht. Für Deutsch `language: de` setzen und neu starten.

## 1. Spiel starten

Windows: `start.bat` doppelklicken.

Linux oder macOS im Projektordner:

```bash
./start.sh
```

Es muss ein Hochformat-Fenster aufgehen, die Spitzhacke fällt, unten stehen erfundene Chat-Namen. Wenn nicht: die Meldung in der Konsole lesen und `logs/cave_dig.log` öffnen.

Pfeil links und rechts lenken zum Probieren. Esc beendet und speichert.

Stürzt das Spiel ab, startet das Skript es nach 10 Sekunden neu. Bei einer falschen `config.yaml` bleibt es stehen und zeigt die Meldung, denn da hilft kein Neustart. Der Grund eines Absturzes steht in `logs/cave_dig.log`.

## 2. YouTube-Schlüssel (einmalig)

1. [Google Cloud Console](https://console.cloud.google.com/) → neues Projekt.
2. **APIs und Dienste → Bibliothek** → **YouTube Data API v3** → Aktivieren.
3. Entweder einen **API-Schlüssel** anlegen (nur diese API erlauben) **oder** eine **OAuth-Desktop-Client-ID** und die JSON als `client_secret.json` hierher legen.
4. Datei `.env` anlegen (Kopie von `.env.example`):

   ```env
   YOUTUBE_API_KEY=dein_schluessel
   YOUTUBE_VIDEO_ID=die_elf_zeichen
   ```

   Bei OAuth statt der Video-ID einmal ausführen:

   ```bash
   python -m cave_dig.auth
   ```

5. In `config.yaml` `chat.provider` auf `youtube` stellen. Bei OAuth zusätzlich `chat.youtube.mode: oauth`. `min_poll_seconds` bei 50 lassen, wenn der Rechner den ganzen Tag streamt. Kleiner nur für kurze Streams, sonst ist das Tageslimit (10.000 Einheiten, ein Chat-Abruf kostet 5) vor Mitternacht leer.
6. Spiel neu starten, **nachdem** der Livestream wirklich live ist und der Chat offen ist. Vorher wartet das Spiel und zeigt das unten im Bild an.

Den Streamschlüssel von YouTube brauchst du hier nicht. Der gehört nur in OBS.

## Twitch-Chat anschliessen

Twitch braucht kein Konto und keinen Token, das Spiel liest nur mit.

1. In `config.yaml` unter `chat.twitch.channel` deinen Kanalnamen eintragen.
2. `chat.provider` auf `twitch` stellen, oder für beide Chats gleichzeitig auf `[youtube, twitch]`.
3. Spiel neu starten. Unten im Bild steht pro Chat eine Zeile, ob er verbunden ist.

Reisst die Verbindung ab, verbindet sich das Spiel selbst neu. Dieselbe Person auf YouTube und Twitch zählt als zwei Personen. Sperren geht mit `twitch:` und der Benutzernummer in `chat.blocked`, oder über den Namen.

## 3. OBS

1. YouTube Studio → Livestream starten → Streamschlüssel kopieren.
2. OBS → Einstellungen → Video: Leinwand und Ausgabe **1080×1920**, **60** FPS.
3. Einstellungen → Stream: YouTube, Schlüssel einfügen.
4. Quelle: Fensteraufnahme von Cave Dig, an die Leinwand anpassen.
5. Erweitert: automatisch neu verbinden.
6. Windows-Energieoptionen: nie schlafen gehen.
7. Stream starten. Spiel und OBS getrennt lassen. Wenn OBS kurz weg ist, läuft die Höhle weiter.

## 4. Wenn niemand lenkt

- Steht unten noch „Test: arrows steer …“ (auf Deutsch: „Test: Pfeile …“)? Dann ist `provider` noch `simulator`.
- Steht „API key or video id missing“ (auf Deutsch: „API-Key oder Video-ID fehlt“)? `.env` liegt nicht neben `config.yaml`, oder der Name ist falsch.
- Steht „No active live chat“ (auf Deutsch: „Kein aktiver Live-Chat“)? Stream ist noch nicht live, oder der Chat ist im Studio aus.
- Steht „daily quota“ (auf Deutsch: „Tageslimit“)? Bis zum nächsten pazifischen Mitternacht warten, oder in der Cloud Console ein höheres Kontingent beantragen. Nicht die Wartezeit auf eine Sekunde setzen.
- Ein Zuschauer schreibt `left`, aber nichts passiert: ein einzelnes Fenster dauert 2,5 Sekunden, und pro Fenster zählt jede Person nur einmal. Mehrere Leute auf einer Seite schieben stärker.

## 5. Danach etwas ändern

- Chat-Wörter: `languages.yaml`, dann neu starten.
- Texte im Fenster: `locales/en.yaml` und `locales/de.yaml`, Sprache über `game.language` in `config.yaml`.
- Punkte, Farben, Wartezeiten: `config.yaml`.
- Ein Erz oder ein Ereignis: Abschnitt in der README, „Einen Block dazunehmen“ und „Ein Ereignis dazunehmen“. Den Banner-Text in beiden Sprachdateien ergänzen.
