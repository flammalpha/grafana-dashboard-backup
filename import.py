import argparse
from datetime import datetime
from typing import Dict, List, Tuple
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


def json_load(path) -> json:
    with open(path, "r", encoding="utf-8") as file:
        return json.load(file)


def logged_request_get(url: str):
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


def logged_request_post(url, data):
    try:
        response = requests.post(url, headers=HEADERS, json=data, verify=False)
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


def get_folder_uid(folder_name):
    """Gets the ID of a folder by name, creates it if it doesn't exist."""
    url = f"{
        GRAFANA_URL}/api/search?query={folder_name}&type=dash-folder"

    folders = logged_request_get(url)

    if folders:
        for folder in folders:
            if folder["title"] == folder_name:
                return folder["uid"]

    # Create folder if it doesn't exist
    create_folder_url = f"{GRAFANA_URL}/api/folders"
    folder_data = {"title": folder_name,
                   "uid": folder_name.replace(" ", "_").lower()}
    response = logged_request_post(create_folder_url, folder_data)
    if response:
        return response["uid"]
    return None


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
            folder_structure.append(folder)
    return folder_structure


def ensure_folders(folder_structure: List[Dict]):
    url = f"{
        GRAFANA_URL}/api/folders"
    existing = logged_request_get(url)
    existing_list = list()
    for folder in existing:
        existing_list.append(folder["uid"])

    missing_folders = folder_structure[:]
    last_remaining = -1
    while missing_folders:
        remaining = []
        for folder in missing_folders:
            if folder["uid"] in existing_list:
                continue
            parent_uid = folder["parentUid"]
            if parent_uid is None or parent_uid in existing_list:
                logged_request_post(url, folder)
                existing_list.append(folder["uid"])
            else:
                remaining.append(folder)

        if len(remaining) == last_remaining:
            logging.error(f"")
            raise Exception(
                "Some folders could not be created due to missing parents")
        last_remaining = len(remaining)
        missing_folders = remaining


def import_dashboard(dashboard_data, folder_uid, overwrite):
    """Loads a dashboard JSON from file system."""

    dashboard_data = {
        "dashboard": dashboard_data,
        "folderUid": folder_uid,
        "message": "Automated Import",
        "overwrite": overwrite
    }

    import_url = f"{GRAFANA_URL}/api/dashboards/db"
    if logged_request_post(import_url, dashboard_data):
        logging.info("Imported: %s", dashboard_data["dashboard"]["title"])


def load_datasource_export():
    """Loads datasource export file from disk"""
    data_sources = json_load(f"{DASHBOARD_FOLDER}/datasource_export.json")
    if data_sources is None:
        raise ValueError("No Datasources found")
    return data_sources


def load_dashboard_export():
    """Loads dashboard export file from disk"""
    dashboards = json_load(f"{DASHBOARD_FOLDER}/dashboard_export.json")
    if dashboards is None:
        raise ValueError("No Dashboards found")
    return dashboards


def match_datasources(datasources_old: List[Dict], datasources_new: List[Dict]):
    uid_matching = dict()
    for datasource_old in datasources_old:
        for datasource_new in datasources_new:
            if datasource_old["type"] == datasource_new["type"]:
                uid_matching[datasource_old["uid"]] = {
                    "uid": datasource_new["uid"],
                    "name_old": datasource_old["name"],
                    "name_new": datasource_new["name"]
                }

    return uid_matching


def get_all_datasources():
    url = f"{GRAFANA_URL}/api/datasources"
    response = logged_request_get(url)
    return response


def get_all_dashboards_uid():
    url = f"{GRAFANA_URL}/api/search?query=&type=dash-db"
    response = logged_request_get(url)
    existing_list = list()
    for dashboard in response:
        if "uid" in dashboard:
            existing_list.append(dashboard["uid"])
    return existing_list


def replace_datasource(dashboard_data, replace_rules):
    if isinstance(dashboard_data, dict):
        if "datasource" in dashboard_data:
            uid = dashboard_data["datasource"]["uid"]
            if uid in replace_rules:
                replace_rule = replace_rules[uid]
                dashboard_data["datasource"]["uid"] = replace_rule["uid"]
                logging.info(
                    f"Replaced Datasource {replace_rule['name_old']} to {replace_rule['name_new']}")
            else:
                logging.warning(
                    f"Cannot find replacement datasource for UID {uid}")
        # Recurse through all values
        for key, value in dashboard_data.items():
            replace_datasource(value, replace_rules)
    elif isinstance(dashboard_data, list):
        for item in dashboard_data:
            replace_datasource(item, replace_rules)
    return dashboard_data


if __name__ == "__main__":
    data_sources = load_datasource_export()
    new_data_sources = get_all_datasources()

    datasource_replace_rules = match_datasources(
        data_sources, new_data_sources)

    dashboards = load_dashboard_export()
    existing_dashboards_list = get_all_dashboards_uid()

    folder_structure = extract_folders(dashboards)

    ensure_folders(folder_structure)

    for dashboard in dashboards:
        if dashboard["type"] == "dash-db":
            folder_path = DASHBOARD_FOLDER
            folder_uid = None
            if "folderUid" in dashboard:
                folder_uid = dashboard["folderUid"]
                folder_path = f"{DASHBOARD_FOLDER}/{get_folder_path(folder_uid, folder_structure)}"

            dashboard_title = dashboard['title'].replace(
                " ", "_").replace("/", "_").replace(",", "_").replace(".", "_")
            file_path = f"{folder_path}/{dashboard_title}.json"

            dashboard_data = json_load(file_path)
            new_dashboard_data = replace_datasource(
                dashboard_data, datasource_replace_rules)
            dashboard_uid = new_dashboard_data["uid"]
            exists = dashboard_uid in existing_dashboards_list
            import_dashboard(new_dashboard_data, folder_uid, exists)

    logging.info("DONE")
