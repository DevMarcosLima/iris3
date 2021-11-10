import logging
from abc import ABCMeta
from functools import lru_cache

from google.cloud import compute_v1

import util.gcp_utils
from gce_base.gce_base import GceBase
from util import gcp_utils


class GceZonalBase(GceBase, metaclass=ABCMeta):
    def _gcp_zone(self, gcp_object):
        """Method dynamically called in generating labels, so don't change name"""
        try:
            return gcp_object["zone"].split("/")[-1]
        except KeyError as e:
            logging.exception(e)
            return None

    def _gcp_region(self, gcp_object):
        """Method dynamically called in generating labels, so don't change name"""
        try:
            zone = self._gcp_zone(gcp_object)
            return util.gcp_utils.region_from_zone(zone)
        except KeyError as e:
            logging.exception(e)
            return None

    @lru_cache(maxsize=1)
    def _all_zones(self):
        """
        Get all available zones.
        NOTE! If different GCP Prpjects have different zones, this will break.
       But we assume that the zone list is the same for all as a performance boost

        """
        zones_client = compute_v1.ZonesClient()
        project_id = gcp_utils.current_project_id()
        request = compute_v1.ListZonesRequest(project=project_id)
        zones = zones_client.list(request)
        ret = [z.name for z in zones]
        return ret

    def should_block_labeling(self, gcp_object, original_labels):
        # We do not label GKE resources because labeling a Node causes it to be re-created.
        # Labeling a disk actually works OK, but we want to be consistent, and Google recommends against it.
        # Label goog-gke-node appears in Nodes (VMs) and Disks; and goog-gke-volume appears in Disks.
        # So you could refactor and split up this logic a bit.
        if "goog-gke-node" in original_labels or "goog-gke-volume" in original_labels:
            logging.info(
                f"{self.__class__.__name__}, skip labeling GKE object {gcp_object.get('name')}"
            )
            return True
        else:
            return False
