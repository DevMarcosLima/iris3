import logging
from typing import List, Dict, Optional

from google.cloud import compute_v1
from google.cloud.compute_v1.types.compute import Instance
from googleapiclient import errors

from gce_base.gce_zonal_base import GceZonalBase
from util import gcp_utils
from util.utils import log_time
from util.utils import timing

instances_client = compute_v1.InstancesClient()


class Instances(GceZonalBase):
    def _gcp_instance_type(self, gcp_object: dict):
        """Method dynamically called in generating labels, so don't change name"""
        try:
            machine_type = gcp_object["machineType"]
            ind = machine_type.rfind("/")
            machine_type = machine_type[ind + 1 :]
            return machine_type
        except KeyError as e:
            logging.exception(e)
            return None

    def method_names(self):
        return ["compute.instances.insert", "compute.instances.start"]

    def __list_instances(self, project_id: str, zone: str):
        request = compute_v1.ListInstancesRequest(project=project_id, zone=zone)
        instances = list(instances_client.list(request))
        assert all(isinstance(i, Instance) for i in instances), [
            i.__class__ for i in instances
        ]
        instances_as_dicts: List[Dict] = [self.__instance_to_dict(i) for i in instances]
        return instances_as_dicts

    def __get_instance(self, project_id, zone, name) -> Optional[Dict]:
        try:
            request = compute_v1.GetInstanceRequest(
                project=project_id, zone=zone, instance=name
            )
            inst = instances_client.get(request)
            isinstance(inst, Instance)
            return self.__instance_to_dict(inst)
        except errors.HttpError as e:
            logging.exception(e)
            return None

    def label_all(self, project_id):
        with timing(f"label_all(Instance) in {project_id}"):
            zones = self._all_zones(project_id)
            with timing(f" label instances in {len(zones)} zones"):
                for zone in zones:
                    instances = self.__list_instances(project_id, zone)
                    for instance in instances:
                        try:
                            self.label_resource(instance, project_id)
                        except Exception as e:
                            logging.exception(e)
            if self.counter > 0:
                self.do_batch()

    def get_gcp_object(self, log_data):
        try:
            inst = log_data["protoPayload"]["resourceName"]
            ind = inst.rfind("/")
            inst = inst[ind + 1 :]
            labels = log_data["resource"]["labels"]["project_id"]
            zone = log_data["resource"]["labels"]["zone"]
            instance = self.__get_instance(labels, zone, inst)
            return instance
        except Exception as e:
            logging.exception(e)
            return None

    @log_time
    def label_resource(self, gcp_object, project_id):
        labels = self._build_labels(gcp_object, project_id)
        if labels is None:
            return

        zone = self._gcp_zone(gcp_object)

        name = gcp_object["name"]
        self._batch.add(
            self._google_client.instances().setLabels(
                project=project_id,
                zone=zone,
                instance=name,
                body=labels,
            ),
            request_id=gcp_utils.generate_uuid(),
        )
        # Could do this, but that apparently that does not support batching
        #  compute_v1.SetLabelsInstanceRequest(project=project_id, zone=zone, instance=name, labels=labels)

        self.counter += 1
        if self.counter >= self._BATCH_SIZE:
            self.do_batch()

    def __instance_to_dict(self, inst: Instance) -> Dict:
        return {  # could copy more information into this dict. As-is, we copy only the fields that are later used.
            "name": inst.name,
            "zone": inst.zone,
            "machineType": inst.machine_type,
            "labels": inst.labels,
        }
