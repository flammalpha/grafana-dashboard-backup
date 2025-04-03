# Grafana Dashboard Backup

A quick Grafana Dashboard backup script to automatically write all dashboards to disk and re-import them.

## Features

- Export Dashboards, Folders, Datasources
- Create Folder structure on import
- Map Datasources to matching alternative if different Grafana instance

## Usage

```bash
python -m venv .venv
. ./.venv/bin/activate
pip install -r requirements.txt
python export.py
python import.py
```

### Parameters

Either add a `.env` file according to the existing `.env.example` or specify the following parameters in CLI:

```plain
GRAFANA_URL         (-u / --url)
API_KEY             (-t / --token)
DASHBOARD_FOLDER    (-f / --folder)
```

Example:

```bash
python export.py -u "http://your-dashboard-url" -t "xxx" -f ./dashboards
python import.py -u "http://your-dashboard-url" -t "xxx" -f ./dashboards
```

## References

- [Grafana HTTP API Docs](https://grafana.com/docs/grafana/latest/developers/http_api/)
