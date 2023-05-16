import logging
from typing import Dict, Optional

from googleapiclient import errors

from plugin import Plugin
from util.utils import log_time, timing


class CloudRun(Plugin):
    @staticmethod
    def _discovery_api():
        return "run", "v1"

    @staticmethod
    def method_names():
        return ["cloudrun.services.create"]

    @classmethod
    def _cloudclient(cls, _=None):
        logging.info("_cloudclient for %s", cls.__name__)
        raise NotImplementedError("There is no Cloud Client library for " + cls.__name__)

    @staticmethod
    def is_labeled_on_creation() -> bool:
        # As Labels não podem ser aplicados aos serviços do Cloud Run durante a criação.
        # Por que:
        #     O serviço Cloud Run é criado de forma assíncrona e pode não estar imediatamente disponível para atualizações de labels.
        # Como:
        #     Use uma solução alternativa para rotular o serviço depois que ele estiver totalmente implantado e disponível.
        return False

    def _gcp_name(self, gcp_object):
        return self._name_no_separator(gcp_object)

    def _gcp_region(self, gcp_object):
        try:
            return gcp_object["metadata"]["labels"]["region"].lower()
        except KeyError:
            logging.exception(f"Error getting region for {gcp_object['metadata']['name']} MARCOSx003")
            return None

    def _get_resource(self, project_id, name):
        try:
            result = (
                self._google_api_client()
                .namespaces()
                .services()
                .get(name=name, namespace="default")
                .execute()
            )
            return result
        except errors.HttpError:
            logging.exception(f"Error getting resource {name} in project {project_id} MARCOSx001")
            return None

    def get_gcp_object(self, log_data: Dict) -> Optional[Dict]:
        try:
            if "response" not in log_data["protoPayload"]:
                return None
            labels_ = log_data["resource"]["labels"]
            service = labels_["service_name"]
            service = self._get_resource(labels_["project_id"], service)
            return service
        except Exception:
            logging.exception(f"Error getting resource {log_data['resource']['name']} MARCOSx002")
            return None

    def label_all(self, project_id):
        with timing(f"label_all({type(self).__name__}) in {project_id}"):
            page_token = None
            while True:
                response = (
                    self._google_api_client()
                    .namespaces()
                    .services()
                    .list(namespace="default", filter=f"projectId:{project_id}", pageToken=page_token)
                    .execute()
                )

                if "items" not in response:
                    return
                for service in response["items"]:
                    try:
                        self.label_resource(service, project_id)
                    except Exception:
                        logging.exception("")
                if "nextPageToken" in response:
                    page_token = response["nextPageToken"]
                else:
                    return

    @log_time
    def label_resource(self, gcp_object, project_id):
        labels = self._build_labels(gcp_object, project_id)
        if labels is None:
            return
        try:
            service_name = gcp_object["metadata"]["name"]
            service_namespace = gcp_object["metadata"]["namespace"]
            service_body = {"metadata": {"labels": labels["labels"]}}

            self._google_api_client().namespaces().services().patch(
                name=f"{service_name}",
                namespace=service_namespace,
                body=service_body,
            ).execute()

        except errors.HttpError as e:
            if "SERVICE_STATUS_UNSPECIFIED" in gcp_object.get("status", {}):
                logging.exception("Cloud Run service is not fully deployed yet, which is why we do not label it on-demand in the usual way",)
        raise e