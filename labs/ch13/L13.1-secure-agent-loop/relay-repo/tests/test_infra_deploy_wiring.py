"""Deployment wiring (4.25.0, ADR-031), read from infra/compute.tf: every setting the code requires is supplied,
the worker runs escalation passes, migrations run as their own role, and images are referenced by digest.

These read the committed configuration; they do not plan or apply it. The environment carries no traffic until the
PostgreSQL store adapter exists (ADR-014), which is why the service refuses a database host and the desired counts
in nonprod.tfvars are zero.
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COMPUTE = (ROOT / "infra" / "compute.tf").read_text(encoding="utf-8")
IAM = (ROOT / "infra" / "iam.tf").read_text(encoding="utf-8")
TFVARS = (ROOT / "infra" / "nonprod.tfvars").read_text(encoding="utf-8")


def block(kind: str, name: str, text: str = COMPUTE) -> str:
    start = text.index(f'resource "{kind}" "{name}"')
    end = text.find("\nresource ", start + 1)
    return text[start:end if end > 0 else len(text)]


def env_names(text: str) -> set[str]:
    return set(re.findall(r'\{ name = "(RELAY_[A-Z_]+)", value', text))


def test_the_service_task_supplies_every_setting_the_wsgi_module_requires():
    sys.path.insert(0, str(ROOT / "src"))
    from relay.service.wsgi import REQUIRED
    service = block("aws_ecs_task_definition", "service")
    assert set(REQUIRED) <= env_names(service)


def db_paths(task: str) -> list[str]:
    """Every database path a task's containers are given, as a flag or a setting."""
    paths = re.findall(r'"--db",\s*([\w.]+|"[^"]+")', task)
    paths += re.findall(r'\{ name = "RELAY_DB_PATH", value = ([\w.]+|"[^"]+") \}', task)
    return [p.strip('"') for p in paths]


def test_every_database_path_is_on_a_writable_volume():
    """The root filesystem is read-only, so a SQLite file must sit on a writable mount (a placeholder until the
    PostgreSQL adapter: each task's volume is its own, so no two tasks share the file)."""
    db_path = re.search(r'db_path\s*=\s*"([^"]+)"', COMPUTE)[1]
    writable = re.findall(r'containerPath = "([^"]+)", readOnly = false', COMPUTE)
    assert any(db_path.startswith(m + "/") for m in writable)
    assert not any(db_path.startswith(m + "/") for m in re.findall(r'containerPath = "([^"]+)", readOnly = true',
                                                                    COMPUTE))
    for name in ("service", "worker", "migrate"):
        task = block("aws_ecs_task_definition", name)
        assert db_paths(task) == ["local.db_path"], name
        assert "local.data_volume" in task and ("local.read_config" in task or '"relay-data"' in task), name


def test_the_worker_runs_escalation_passes_with_the_directory_and_the_link_base():
    worker = block("aws_ecs_task_definition", "worker")
    entry = re.search(r"entryPoint = \[(.*?)\]", worker, re.S)[1]
    args = [a.strip().strip('"') for a in entry.replace("\n", " ").split(",")]
    assert args[:3] == ["python", "-m", "relay.worker"]
    assert args[args.index("--directory") + 1] == "/run/relay/directory.json"
    assert args[args.index("--link-base") + 1] == "var.link_base"


def test_the_directory_secret_reaches_only_the_init_container():
    assert COMPUTE.count("RELAY_DIRECTORY_JSON") == 2  # the init container's secret and its own command
    for name in ("service", "worker"):
        task = block("aws_ecs_task_definition", name)
        assert "local.write_config" in task and "local.read_config" in task and "volume {" in task
    assert 'condition = "SUCCESS"' in COMPUTE and "readOnly = true" in COMPUTE


def test_migrations_run_as_their_own_role_and_nothing_else_logs_in_as_it():
    migrate = block("aws_ecs_task_definition", "migrate")
    assert '"relay.service.migrate"' in migrate and '"relay_migrator"' in migrate
    assert "aws_iam_role.migrate_task.arn" in migrate
    assert COMPUTE.count('"relay_migrator"') == 1
    policy = block("aws_iam_role_policy", "migrate_task", IAM)
    assert "relay_migrator" in policy and policy.count("Action") == 1


def test_every_image_is_referenced_by_digest():
    assert re.findall(r'^\s*(?:image|proxy_image)\s*=\s*"(.*)"$', COMPUTE, re.M) == [
        "${aws_ecr_repository.relay.repository_url}@${var.image_digest}",
        "${aws_ecr_repository.egress_proxy.repository_url}@${var.proxy_image_digest}"]
    assert re.findall(r'^(?:proxy_)?image_digest\s*=\s*"(sha256:[0-9a-f]{64})"$', TFVARS, re.M).__len__() == 2


def test_no_traffic_until_the_store_adapter_exists():
    assert re.search(r"^service_desired_count = 0$", TFVARS, re.M)
    assert re.search(r"^worker_desired_count  = 0$", TFVARS, re.M)
