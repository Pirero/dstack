from typing import Optional, List

from botocore.client import BaseClient

from dstack import random_name
from dstack.aws import run_names, logs, jobs, runners
from dstack.backend import Run, AppHead, ArtifactHead
from dstack.jobs import JobHead, Job


def create_run(s3_client: BaseClient, logs_client: BaseClient, bucket_name: str, repo_user_name: str,
               repo_name: str) -> str:
    name = random_name.next_name()
    run_name_index = run_names.next_run_name_index(s3_client, bucket_name, name)
    run_name = f"{name}-{run_name_index}"
    log_group_name = f"/dstack/jobs/{bucket_name}/{repo_user_name}/{repo_name}"
    logs.create_log_group_if_not_exists(logs_client, bucket_name, log_group_name)
    logs.create_log_stream(logs_client, log_group_name, run_name)
    return run_name


def _create_run(ec2_client: BaseClient, repo_user_name, repo_name, job: Job, include_request_heads: bool) -> Run:
    app_heads = list(map(lambda a: AppHead(job.job_id, a.app_name), job.app_specs)) if job.app_specs else None
    artifact_heads = list(
        map(lambda a: ArtifactHead(job.job_id, a.artifact_path), job.artifact_specs)) if job.artifact_specs else None
    request_heads = None
    if include_request_heads and job.status.is_unfinished():
        if request_heads is None:
            request_heads = []
        request_heads.append(runners.request_head(ec2_client, job))
    run = Run(repo_user_name, repo_name, job.run_name, job.workflow_name, job.provider_name,
              artifact_heads or None, job.status, job.submitted_at, job.tag_name,
              app_heads, request_heads)
    return run


def _update_run(ec2_client: BaseClient, run: Run, job: Job, include_request_heads: bool):
    run.submitted_at = min(run.submitted_at, job.submitted_at)
    if job.artifact_specs:
        if run.artifact_heads is None:
            run.artifact_heads = []
        run.artifact_heads.extend(list(map(lambda a: ArtifactHead(job.job_id, a.artifact_path), job.artifact_specs)))
    if job.app_specs:
        if run.app_heads is None:
            run.app_heads = []
        run.app_heads.extend(list(map(lambda a: AppHead(job.job_id, a.app_name), job.app_specs)))
    if job.status.is_unfinished():
        run.status = job.status
        if include_request_heads:
            if run.request_heads is None:
                run.request_heads = []
            run.request_heads.append(runners.request_head(ec2_client, job))


def get_runs(ec2_client: BaseClient, s3_client: BaseClient, bucket_name: str, repo_user_name, repo_name,
             job_heads: List[JobHead], include_request_heads: bool) -> List[Run]:
    runs_by_id = {}
    for job_head in job_heads:
        job = jobs.get_job(s3_client, bucket_name, repo_user_name, repo_name, job_head.job_id)
        if job:
            run_id = ','.join([job.run_name, job.workflow_name or ''])
            if run_id not in runs_by_id:
                runs_by_id[run_id] = _create_run(ec2_client, repo_user_name, repo_name, job, include_request_heads)
            else:
                run = runs_by_id[run_id]
                _update_run(ec2_client, run, job, include_request_heads)
    return sorted(list(runs_by_id.values()), key=lambda r: r.submitted_at, reverse=True)


def list_runs(ec2_client: BaseClient, s3_client: BaseClient, bucket_name: str, repo_user_name, repo_name,
              run_name: Optional[str], include_request_heads: bool) -> List[Run]:
    job_heads = jobs.list_job_heads(s3_client, bucket_name, repo_user_name, repo_name, run_name)
    return get_runs(ec2_client, s3_client, bucket_name, repo_user_name, repo_name, job_heads, include_request_heads)
