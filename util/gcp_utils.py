import os
import re
import uuid
from typing import List, Dict, Any

from google.cloud import resourcemanager_v3
from googleapiclient import discovery
from oauth2client.client import GoogleCredentials

from util import localdev_config
from util.utils import timed_lru_cache, log_time

projects_client = resourcemanager_v3.ProjectsClient()
folders_client = resourcemanager_v3.FoldersClient()

resource_manager = discovery.build(
    "cloudresourcemanager",
    "v1",
    credentials=(GoogleCredentials.get_application_default()),
)


def detect_gae():
    gae_app = os.environ.get("GAE_APPLICATION", "")
    return "~" in gae_app


def current_project_id():
    """
    :return the project id on which we run AppEngine and PubSub
    """
    if detect_gae():
        return os.environ.get("GAE_APPLICATION", "").split("~")[1]
    else:
        return localdev_config.localdev_project_id()


def set_env():
    if not detect_gae():
        localdev_config.set_localdev_project_id_in_env()


def region_from_zone(zone):
    return zone[: len(zone) - 2].lower()


def generate_uuid() -> str:
    """
    :return a UUID as a string (and not an object or bytes);  this is required by the http API.
    """
    return str(uuid.uuid4())


def is_appscript_project(p) -> bool:
    """With the Google Cloud Libraries, we don't get these appscript sys- project, but the filtering won't hurt."""
    return bool(re.match(r"sys-\d{26}", p))


def all_projects() -> List[str]:
    current_proj_id = current_project_id()
    current_project = projects_client.get_project(
        None, name=f"projects/{current_proj_id}"
    )
    parent_name = current_project.name
    org_name = get_org(parent_name)

    projects = projects_client.list_projects(parent=org_name)
    all_proj = [p.project_id for p in projects]
    ret = sorted(all_proj)
    return ret


@log_time
@timed_lru_cache(seconds=600, maxsize=500)
def get_org(proj_name):
    assert proj_name.startswith(
        "projects/"
    ), f"Expect the form 'projects/123456789, was {proj_name}"
    parent_name = proj_name
    while True:
        if parent_name.startswith("projects/"):
            parent = projects_client.get_project(None, name=parent_name)
        elif parent_name.startswith("folders/"):
            parent = folders_client.get_folder(None, name=parent_name)
        elif parent_name.startswith("organizations/"):
            org_name = parent_name
            break
        else:
            raise Exception(
                f"expect projects/, folders/, or organizations/, was {parent_name}"
            )

        parent_name = parent.parent
    assert org_name.startswith(
        "organizations/"
    ), f"Expect the form 'organizations/123456789, was {org_name}"
    return org_name


def get_project(project_id: str) -> Dict[str, Any]:
    projects = resource_manager.projects()
    request = projects.get(projectId=project_id)
    proj: Dict = request.execute()
    return proj
