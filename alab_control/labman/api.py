import requests
from typing import Literal


class LabmanAPI:
    def __init__(self, url: str, port: int):
        self.API_BASE = f"{url}:{port}"

    def get_status(self):
        url = f"{self.API_BASE}/GetStatus"
        return requests.get(url=url)

    def request_indexing_rack_control(self, index: Literal[1, 2, 3, 4]):
        url = f"{self.API_BASE}/RequestIndexingRackControl"
        return requests.post(url=url, json={"index": index})

    def release_indexing_rack_control(self):
        url = f"{self.API_BASE}/ReleaseIndexingRackControl"
        return requests.post(url)

    def submit_workflow(self, workflow_json: dict):
        url = f"{self.API_BASE}/PotsLoaded"
        return requests.post(url, json=workflow_json)

    def validate_workflow(self, workflow_json: dict):
        url = f"{self.API_BASE}/ValidateWorkflow"
        return requests.post(url, json=workflow_json)
