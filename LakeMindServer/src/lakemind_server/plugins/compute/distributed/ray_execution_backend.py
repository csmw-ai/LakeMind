from __future__ import annotations
import os
import json
import shlex
from typing import Any

_RAY_AVAILABLE = False
try:
    from ray.job_submission import JobSubmissionClient
    _RAY_AVAILABLE = True
except ImportError:
    pass


_RAY_DASHBOARD = os.environ.get("LAKEMIND_RAY_DASHBOARD", "http://ray-head:8265")

_S3_ENDPOINT = os.environ.get("S3_ENDPOINT", "http://lakemind-seaweedfs:8333")
_S3_ACCESS_KEY = os.environ.get("S3_ACCESS_KEY", "admin")
_S3_SECRET_KEY = os.environ.get("S3_SECRET_KEY", "admin123456")

_STATUS_MAP = {
    "PENDING": "QUEUED",
    "RUNNING": "RUNNING",
    "SUCCEEDED": "SUCCEEDED",
    "FAILED": "FAILED",
    "STOPPED": "CANCELLED",
    "NOT_SUBMITTED": "QUEUED",
    "SUBMITTED": "QUEUED",
}

_BOOTSTRAP = """\
import boto3, io, zipfile, os, sys, json
from urllib.parse import urlparse
uri = os.environ["LAKEMIND_SKILL_PKG_URI"]
p = urlparse(uri)
bucket = p.netloc
key = p.path.lstrip("/")
s3 = boto3.client("s3", endpoint_url=os.environ.get("LAKEMIND_S3_ENDPOINT","http://lakemind-seaweedfs:8333"), aws_access_key_id=os.environ.get("LAKEMIND_S3_AK","admin"), aws_secret_access_key=os.environ.get("LAKEMIND_S3_SK","admin123456"), region_name="us-east-1")
resp = s3.get_object(Bucket=bucket, Key=key)
with zipfile.ZipFile(io.BytesIO(resp["Body"].read())) as zf:
    zf.extractall(".")
os.execv(sys.executable, [sys.executable] + json.loads(os.environ["LAKEMIND_ENTRYPOINT_ARGS"]))
"""


class RayExecutionBackend:

    def __init__(self, dashboard_url: str | None = None) -> None:
        self._dashboard = dashboard_url or _RAY_DASHBOARD
        self._client = None
        if _RAY_AVAILABLE:
            try:
                self._client = JobSubmissionClient(self._dashboard)
            except Exception:
                self._client = None

    def submit(
        self,
        job_id: str,
        skill_package_uri: str,
        entry_point: str,
        inputs: dict,
        params: dict,
        resources: dict,
        secrets: dict,
        model_binding: dict | None,
    ) -> str:
        if self._client is None:
            raise RuntimeError("Ray not available")

        env: dict[str, str] = {f"LAKEMIND_SECRET_{k}": v for k, v in secrets.items()}
        env["PYTHONPATH"] = "."
        env["LAKEMIND_JOB_ID"] = job_id
        if model_binding:
            env["LAKEMIND_MODEL_BINDING"] = str(model_binding)
        env["RAY_JOB_PARAMS"] = json.dumps(inputs)
        env["LAKEMIND_S3_ENDPOINT"] = _S3_ENDPOINT
        env["LAKEMIND_S3_AK"] = _S3_ACCESS_KEY
        env["LAKEMIND_S3_SK"] = _S3_SECRET_KEY
        env["MODEL_SERVING_URL"] = os.environ.get("MODEL_SERVING_URL", "http://lakemind-model-serving:10824")
        env["MODELSERVING_API_KEY"] = os.environ.get("MODELSERVING_API_KEY", "lakemind-modelserving-key")
        env["SERVER_API_URL"] = os.environ.get("SERVER_API_URL", "http://lakemind-server-api:10823")
        env["SERVER_API_KEY"] = os.environ.get("SERVER_API_KEY", "ljLH3bvzIFjG4r3zeCP6AsHsGEnbmAQY_Hi3dW7du5o")

        runtime_env: dict[str, Any] = {"env_vars": env}
        pip_deps = os.environ.get("LAKEMIND_RAY_PIP_DEPS", "")
        if pip_deps:
            runtime_env["pip"] = [d.strip() for d in pip_deps.split(",") if d.strip()]

        if skill_package_uri and skill_package_uri.startswith("s3://"):
            env["LAKEMIND_SKILL_PKG_URI"] = skill_package_uri
            env["LAKEMIND_ENTRYPOINT_ARGS"] = json.dumps([entry_point])
            entrypoint = "python -c " + shlex.quote(_BOOTSTRAP)
        else:
            if skill_package_uri:
                runtime_env["working_dir"] = skill_package_uri
            entrypoint = f"python {entry_point}"

        ray_job_id = self._client.submit_job(
            entrypoint=entrypoint,
            runtime_env=runtime_env,
            metadata={"lakemind_job_id": job_id},
            entrypoint_num_cpus=resources.get("cpu", 1),
            entrypoint_memory=resources.get("memory_gb", 1) * 1024 * 1024 * 1024,
        )
        return ray_job_id

    def cancel(self, backend_job_id: str) -> None:
        if self._client is None:
            return
        self._client.stop_job(backend_job_id)

    def get_status(self, backend_job_id: str) -> str:
        if self._client is None:
            return "LOST"
        status = self._client.get_job_status(backend_job_id)
        return _STATUS_MAP.get(str(status), "UNKNOWN")

    def get_logs(self, backend_job_id: str) -> str:
        if self._client is None:
            return ""
        return self._client.get_job_logs(backend_job_id)

    def get_result(self, backend_job_id: str) -> dict:
        if self._client is None:
            return {}
        logs = self.get_logs(backend_job_id)
        return {"logs": logs, "ray_job_id": backend_job_id}
