import argparse
from datetime import datetime
from typing import Dict, List
import requests
import os
import json
import logging
from dotenv import load_dotenv

file_timestamp = datetime.now().strftime("./logs/log_%Y-%m-%d_%H-%M-%S.log")
os.makedirs("./logs", exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.FileHandler(file_timestamp),
        logging.StreamHandler()
    ]
)

parser = argparse.ArgumentParser(description="Grafana Dashboard Importer")
parser.add_argument("-u", "--url", type=str, help="Grafana URL")
parser.add_argument("-t", "--token", type=str, help="Access Token")
parser.add_argument("-f", "--folder", type=str,
                    help="Folder path to Dashboards")
args = parser.parse_args()

load_dotenv()

GRAFANA_URL = args.url or os.getenv("GRAFANA_URL")
API_TOKEN = args.token or os.getenv("API_KEY")
DASHBOARD_FOLDER = args.folder or os.getenv("DASHBOARD_FOLDER")

missing_params = []
if not GRAFANA_URL:
    missing_params.append("Grafana URL (-u or GRAFANA_URL env var)")
if not API_TOKEN:
    missing_params.append("API Token (-t or API_KEY env var)")
if not DASHBOARD_FOLDER:
    missing_params.append("Dashboard Folder (-f or DASHBOARD_FOLDER env var)")

if missing_params:
    error_message = f"Missing required parameters: {', '.join(missing_params)}"
    logging.error(error_message)
    raise ValueError(error_message)

HEADERS = {
    "Authorization": f"Bearer {API_TOKEN}",
    "Content-Type": "application/json"
}


def json_dump(content, path):
    with open(path, "w", encoding="utf-8", newline="\n") as file:
        json.dump(content, file, ensure_ascii=False, indent=2)


def logged_request(url: str):
    try:
        response = requests.get(url, headers=HEADERS, verify=False)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.HTTPError as http_err:
        logging.error(
            "HTTP error occurred: %s [%s]", http_err, response.status_code)
    except requests.exceptions.ConnectionError:
        logging.error(
            "Failed to connect to %s. Please check your network.", url)
    except requests.exceptions.Timeout:
        logging.error("Request to %s timed out.", url)
    except requests.exceptions.RequestException as err:
        logging.error("An error occurred: %s", err)


def get_all_dashboards():
    """Fetches all dashboards from Grafana."""
    url = f"{GRAFANA_URL}/api/search"
    return logged_request(url)


def get_dashboard(uid):
    """Fetches a specific dashboard by UID."""
    url = f"{GRAFANA_URL}/api/dashboards/uid/{uid}"
    response = logged_request(url)
    if response:
        return response['dashboard']
    return None


def save_dashboard(dashboard, folder_path: str):
    """Saves the dashboard JSON to disk."""
    os.makedirs(folder_path, exist_ok=True)
    dashboard_title = dashboard['title'].replace(
        " ", "_").replace("/", "_").replace(",", "_").replace(".", "_")
    file_path = f"{folder_path}/{dashboard_title}.json"

    json_dump(dashboard, file_path)

    logging.info("Saved: %s", file_path)


def get_folder_path(folder_uid: str, folder_structure: Dict, recurse_depth: int = 0) -> str:
    if folder_uid is None:
        return ""
    MAX_RECURSE = 10  # safety measure to exit after 10 recursions
    if recurse_depth > MAX_RECURSE:
        return folder_uid

    for folder in folder_structure:
        if folder["uid"] == folder_uid:
            parent_path = get_folder_path(
                folder['parentUid'], folder_structure, recurse_depth + 1)
            return f"{parent_path + '/' if parent_path != "" else ''}{folder_uid}"
    return folder_uid


def extract_folders(dashboards: Dict):
    folder_structure = list()

    for item in dashboards:
        if item["type"] == "dash-folder":
            folder = {
                "uid": item["uid"],
                "title": item["title"].replace("/", "_"),
                "parentUid": item["folderUid"] if "folderUid" in item else None
            }
            folder_name = folder["uid"]
            folder_parent = get_folder_path(
                folder["parentUid"], folder_structure)
            folder_path = os.path.join(
                DASHBOARD_FOLDER, folder_parent, folder_name)
            os.makedirs(folder_path, exist_ok=True)
            folder_structure.append(folder)
    return folder_structure


def extract_dashboards(dashboards: Dict, folder_structure: List):
    for item in dashboards:
        if item["type"] == "dash-db":
            dashboard_data = get_dashboard(item["uid"])
            folder_path = DASHBOARD_FOLDER
            if "folderUid" in item:
                folder_path = f"{DASHBOARD_FOLDER}/{get_folder_path(item['folderUid'], folder_structure)}"
            save_dashboard(dashboard_data, folder_path)


def export_dashboards():
    """Exports all Grafana dashboards and saves them recursively in folders."""
    dashboards = get_all_dashboards()

    if not dashboards:
        logging.info("No dashboards found")
        return

    folder_structure = extract_folders(dashboards)
    extract_dashboards(dashboards, folder_structure)

    json_dump(folder_structure, f"{DASHBOARD_FOLDER}/folder_export.json")

    json_dump(dashboards, f"{DASHBOARD_FOLDER}/dashboard_export.json")


def get_all_datasources():
    url = f"{GRAFANA_URL}/api/datasources"
    response = logged_request(url)
    return response


def export_datasources():
    """Exports all Grafana datasources and allows UID matching"""
    data_sources = get_all_datasources()

    if not data_sources:
        logging.info("No datasources found")
        return

    json_dump(data_sources, f"{DASHBOARD_FOLDER}/datasource_export.json")


if __name__ == "__main__":
    export_dashboards()
