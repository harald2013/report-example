# Report example: Verwendung und Betrieb

Staging ist auf wh-coolify eingerichtet: [API-Dokumentation](https://wh-coolify.tail8fba42.ts.net:15100/docs)
und [Temporal UI](https://wh-coolify.tail8fba42.ts.net:15101/) sind im Tailnet
zugänglich. [.agents/infra/staging/coolify.md](.agents/infra/staging/coolify.md) enthält die Ressourcenübersicht;
[deploy/staging.md](deploy/staging.md) beschreibt Konfiguration und Betrieb.
Der API-Schlüssel ist die Shared Variable `API_TOKEN` der Umgebung `staging`
in Coolify; nur bei Bedarf gezielt dort abrufen. Produktion läuft auf Railway; Aufbau und
offene Abnahmepunkte stehen in [deploy/production-setup.md](deploy/production-setup.md).
Die Vorlage wird vor der Ableitung allgemeiner Development-MCP-Regeln praktisch
erprobt.

## Kleine Browseroberfläche

Nach lokalem Start `http://127.0.0.1:18000/ui/` öffnen. Die Seite zeigt
den Titel „Report example“ und ein kleines Formular für Zahlen. Mit „Report erstellen“ startet
sie einen Workflow und zeigt anschließend Anzahl, Summe, Minimum, Maximum und
Mittelwert. Ein späteres „Status erneut prüfen“ lädt nur den angelegten Bericht.

Lokal ist der API-Schlüssel optional. In Staging und Produktion den API-Schlüssel
des jeweiligen API-Dienstes eingeben; er wird nicht dauerhaft im Browser
abgelegt. Seite und Skripte enthalten keinen vorgegebenen Schlüssel. Die
bestehende JSON-Route `/` und die API-Dokumentation `/docs` bleiben erhalten.
Die öffentliche Produktionsoberfläche benötigt weiterhin gültiges HTTPS.

Die UI-Dateien liegen im API-Image, also wird kein weiterer Container benötigt.
Beim Laden der Seite werden keine Reports oder Dependency-Healthchecks abgefragt.

## Lokal starten

Docker mit Compose v2 oder neuer ist erforderlich:

```bash
cp .env.example .env
docker compose up --build -d --wait --wait-timeout 240
curl --fail http://127.0.0.1:18000/ready
```

Die API läuft auf `http://127.0.0.1:18000`, die Temporal-Oberfläche auf
`http://127.0.0.1:18243`. PostgreSQL hat keinen veröffentlichten Port.
Die Zugangsdaten aus `.env.example` sind ausschließlich für lokale Testdaten.
Bei belegten Ports die Werte in `.env` ändern.

```bash
curl --fail -X POST http://127.0.0.1:18000/reports \
  -H 'Content-Type: application/json' \
  -d '{"values": [10, 20, 30], "delay_seconds": 10}'
# Die Antwort enthält id und url. Anschließend die zurückgegebene URL abrufen:
curl --fail http://127.0.0.1:18000/reports/BERICHTS-ID
```

Nach der Verarbeitung enthält `result` Anzahl, Summe, Minimum, Maximum und
Mittelwert. Status vor Abschluss kommt aus Temporal; fertige Ergebnisse bleiben
in PostgreSQL und sind auch nach Ablauf der Temporal-Historie abrufbar.
Ein fehlender Worker lässt den Auftrag zunächst warten. Nach einer Stunde endet
ein nicht abgeschlossener Workflow durch sein Ausführungszeitlimit. Datenbankfehler
werden pro Aktivität bis zu zehnmal wiederholt.

`GET /reports` listet die neuesten Berichte aus PostgreSQL, die neuesten zuerst,
und erfordert wie `POST /reports` den API-Schlüssel. Die Antwort hat die Form
`{"items": [...]}`; jeder Eintrag enthält dieselben Felder wie ein abgeschlossener
Bericht von `GET /reports/{id}`. Der Status stammt aus der Datenbank, nicht aus
Temporal. Der optionale Parameter `limit` (Standard 20, erlaubt 1 bis 100)
begrenzt die Anzahl; andere Werte ergeben HTTP 422, eine nicht erreichbare
Datenbank HTTP 503.

```bash
curl --fail 'http://127.0.0.1:18000/reports?limit=5'
```

POST erzeugt immer einen neuen Auftrag. Bei einem Verbindungsabbruch kann der
Auftrag schon angenommen worden sein: erneutes POST kann daher einen weiteren
Bericht erzeugen. Die API behauptet keine Exactly-once-Zustellung von HTTP-Anfragen.

## Durchlauf und Wiederaufnahme prüfen

Python ab 3.12 und `uv` werden für die Prüfbefehle benötigt:

```bash
uv sync --locked
./scripts/verify
uv run python scripts/smoke.py
uv run python scripts/smoke.py --restart-worker
docker compose exec -T api python < scripts/check_store.py
```

Der letzte Befehl startet einen Bericht mit 30 Sekunden Wartezeit, wartet auf
den ersten Datenbankeintrag, startet ausschließlich den lokalen Beispiel-Worker
neu und prüft das persistierte Ergebnis. Im Temporal UI ist die ursprüngliche
Workflow-ID weiterhin sichtbar. Der Befehl muss im Repository-Verzeichnis gegen
die lokale Compose-Umgebung laufen.

`scripts/verify` prüft Ruff, API-Verträge, Konfiguration und einen echten
Temporal-Testserver mit Wiederholung, Worker-Wechsel und History-Replay. Beim
ersten Lauf lädt das Temporal-SDK sein Testserver-Binary; alternativ kann
`TEMPORAL_TEST_SERVER` auf ein vorhandenes Binary zeigen. Der zusätzliche
Smoke-Test prüft die echte API, Temporal und PostgreSQL gemeinsam.

```bash
docker compose down       # Container stoppen; Daten bleiben erhalten
docker compose down -v    # Nur lokale synthetische Beispieldaten löschen
```

## Images und Betriebsanleitungen

Der [CI-Workflow](.github/workflows/ci.yml) führt `scripts/verify` und den
vollständigen Compose-Durchlauf aus. Der [Image-Workflow](.github/workflows/image.yml)
veröffentlicht geprüfte API- und Workerimages nach GHCR mit `sha-<voller-commit>`.
API und Worker sind Build-Ziele desselben Dockerfiles und laufen als Benutzer
ohne Root-Rechte. Schema-Initialisierung verwendet das API-Image als einmaligen Job.

- [Staging: einzelne Coolify-Anwendungen](deploy/staging.md)
- [Produktion: Railway, Temporal Cloud und Neon](deploy/production.md)
- [Migrationen: Railway Pre-Deploy und Container-Tests](deploy/migrations.md)
- [Konfiguration und Betriebsprüfungen](deploy/operations.md)
- [Architekturentscheidung](docs/adr/0003-report-example.md)

Die bisherigen Entwicklungsskripte unter `scripts/git_*.py` bleiben unverändert.
