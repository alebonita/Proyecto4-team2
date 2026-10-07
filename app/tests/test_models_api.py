"""APP-06: API de la pantalla Models (`training/models_view.py`, `ml-api`).

Lee el registro de OPS-06 (`reports/models/registry.json`, paquetes en `data/models`)
y la publicación en S3 de OPS-07 (`reports/models/s3_publications.json`).

TDD Requirement del issue #23: model version → artifact resolution. Agent Test: dos
versiones resuelven checkpoints (y sha256) distintos.

`published` exige además que S3 confirme cada objeto (head-object con su
ChecksumSHA256). Aquí S3 es `FakeS3`, una foto de lo que se subió; el verificador real
(`training.s3_verification`) tiene sus propias pruebas.
"""

import json
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from starlette.testclient import TestClient

from presentation.ml_contracts import ErrorResponse, ModelsResponse, RegisteredModelVersion
from tests._model_registry import BUCKET, MODEL, ROOT, Registry, make_checkpoint, sha256
from training.queue import TrainingJobQueue
from training.s3_verification import S3Head, S3Unverifiable
from training.server import create_app

RUN_A = "a" * 32
RUN_B = "b" * 32


class FakeS3:
    """S3 en memoria: (bucket, key, version_id) → sha256 que S3 devolvería."""

    def __init__(self, publications: list[dict] = ()):
        self.objects = {
            (record["bucket"], entry["key"], entry["version_id"]): entry["sha256"]
            for record in publications
            for entry in record["files"].values()
        }
        self.error: str | None = None
        self.calls: list[tuple] = []

    def head(self, *, bucket: str, region: str, key: str, version_id: str | None):
        self.calls.append((bucket, region, key, version_id))
        if self.error is not None:
            raise S3Unverifiable(self.error)
        checksum = self.objects.get((bucket, key, version_id))
        return None if checksum is None else S3Head(checksum_sha256=checksum)


@pytest.fixture(scope="module")
def checkpoints(tmp_path_factory) -> dict[str, Path]:
    folder = tmp_path_factory.mktemp("checkpoints")
    return {
        "a": make_checkpoint(folder / "a.pt", bias=(6.0, -6.0)),
        "b": make_checkpoint(folder / "b.pt", bias=(-6.0, 6.0)),
    }


@pytest.fixture
def registry(tmp_path, checkpoints) -> Registry:
    built = Registry(tmp_path / "repo")
    built.register("1.0.0", RUN_A, checkpoints["a"])
    built.register("1.1.0", RUN_B, checkpoints["b"])
    return built


_UPLOADED = object()


def client_for(tmp_path: Path, registry: Registry, s3=_UPLOADED) -> TestClient:
    """Por defecto S3 tiene exactamente lo que el registro de OPS-07 dice que se subió."""
    if s3 is _UPLOADED:
        s3 = FakeS3(json.loads(json.dumps(registry.publications)))
    queue = TrainingJobQueue(create_engine(f"sqlite:///{tmp_path / 'jobs.db'}"))
    queue.create_tables()
    reports = registry.root / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    return TestClient(
        create_app(queue=queue, reports_dir=reports, repo_root=registry.root, s3_verifier=s3)
    )


def models(client: TestClient) -> dict[str, RegisteredModelVersion]:
    response = client.get("/models")
    assert response.status_code == 200, response.text
    parsed = ModelsResponse.model_validate(response.json())
    return {model.model_version: model for model in parsed.models}


# --- Versiones del registro ----------------------------------------------------------


def test_every_registered_version_is_listed_with_its_traceability(tmp_path, registry, checkpoints):
    listed = models(client_for(tmp_path, registry))

    assert set(listed) == {"1.0.0", "1.1.0"}, "la versión anterior sigue disponible"
    model = listed["1.0.0"]
    entry = registry.packages[0]
    assert (model.model_name, model.run_id) == (MODEL, RUN_A)
    assert model.checkpoint == f"runs:/{RUN_A}/checkpoints/best.pt"
    assert model.checkpoint_sha256 == sha256(checkpoints["a"])
    assert (model.dataset_version, model.manifest_hash) == (
        entry["dataset_version"],
        entry["manifest_hash"],
    )
    assert (model.architecture, model.image_size) == ("resnet18", 64)
    assert model.test_metrics.accuracy_top1 == entry["metrics"]["accuracy_top1"]
    assert model.model_card.purpose == entry["model_card"]["purpose"]
    assert model.model_card.limitations == entry["model_card"]["limitations"]
    assert [f.name for f in model.files] == list(entry["files"])
    assert model.servable and all(f.available for f in model.files)


def test_agent_test_each_version_resolves_its_own_checkpoint(tmp_path, registry, checkpoints):
    client = client_for(tmp_path, registry)

    first = RegisteredModelVersion.model_validate(client.get("/models/1.0.0").json())
    second = RegisteredModelVersion.model_validate(client.get("/models/1.1.0").json())

    assert (first.run_id, first.checkpoint_sha256) == (RUN_A, sha256(checkpoints["a"]))
    assert (second.run_id, second.checkpoint_sha256) == (RUN_B, sha256(checkpoints["b"]))


def test_unknown_version(tmp_path, registry):
    response = client_for(tmp_path, registry).get("/models/9.9.9")

    assert response.status_code == 404
    assert ErrorResponse.model_validate(response.json()).error.code == "model_not_found"


def test_without_registry_there_are_no_models(tmp_path):
    empty = Registry(tmp_path / "repo")

    assert models(client_for(tmp_path, empty)) == {}


def test_unreadable_registry(tmp_path, registry):
    registry.path.write_text("{no es json", encoding="utf-8")

    response = client_for(tmp_path, registry).get("/models")

    assert response.status_code == 503
    assert ErrorResponse.model_validate(response.json()).error.code == "registry_unavailable"


# --- Paquete en este servidor (servable) ---------------------------------------------


def test_package_not_pulled_is_not_servable(tmp_path, registry):
    registry.checkpoint("1.0.0").unlink()

    model = models(client_for(tmp_path, registry))["1.0.0"]

    assert not model.servable
    assert {f.name: f.available for f in model.files}["checkpoint/best.pt"] is False


def test_altered_package_file_is_not_available(tmp_path, registry):
    card = registry.root / registry.packages[0]["package_path"] / "model-card.md"
    card.write_text("otra tarjeta\n", encoding="utf-8")

    model = models(client_for(tmp_path, registry))["1.0.0"]

    assert not model.servable
    assert {f.name: f.available for f in model.files}["model-card.md"] is False


def test_version_with_metadata_only_is_listed_but_not_servable(tmp_path, registry):
    registry.register("0.9.0", "c" * 32, None, checkpoint_sha256="5" * 64)

    model = models(client_for(tmp_path, registry))["0.9.0"]

    assert not model.servable and model.files[0].name == "checkpoint/best.pt"


# --- Publicación en S3 ---------------------------------------------------------------


def test_published_version_shows_bucket_and_keys(tmp_path, registry):
    registry.publish("1.0.0")

    listed = models(client_for(tmp_path, registry))

    publication = listed["1.0.0"].publication
    assert (publication.status, publication.bucket, publication.region) == (
        "published",
        BUCKET,
        "us-east-1",
    )
    keys = {obj.name: obj.key for obj in publication.objects}
    assert keys["checkpoint/best.pt"] == f"models/{MODEL}/1.0.0/checkpoint/best.pt"
    assert "package.json" in keys
    assert listed["1.1.0"].publication.status == "not_published"


def _break_file(field: str, value: str):
    def mutate(record: dict) -> None:
        record["files"]["checkpoint/best.pt"][field] = value

    return mutate


@pytest.mark.parametrize(
    ("mutate", "fragment"),
    [
        (lambda r: r.update(checkpoint_sha256="0" * 64), "checkpoint"),
        (lambda r: r.update(run_id="f" * 32), "run"),
        (_break_file("s3_checksum_sha256", "0" * 64), "S3"),
        (_break_file("download_sha256", "0" * 64), "descarga"),
        (_break_file("sha256", "0" * 64), "registr"),
        (lambda r: r["files"].pop("model-card.md"), "model-card.md"),
        (lambda r: r.update(bucket=""), "bucket"),
    ],
    ids=[
        "other-checkpoint",
        "other-run",
        "s3-checksum",
        "download",
        "other-file-sha",
        "missing-file",
        "no-bucket",
    ],
)
def test_publication_that_does_not_match_is_never_shown_as_published(
    tmp_path, registry, mutate, fragment
):
    record = registry.publish("1.0.0")
    mutate(record)
    registry.save_publications()

    publication = models(client_for(tmp_path, registry))["1.0.0"].publication

    assert publication.status == "inconsistent"
    assert publication.objects == [] and publication.bucket is None
    assert fragment in publication.problem


def test_unreadable_publications_do_not_hide_the_models(tmp_path, registry):
    registry.publications_path.parent.mkdir(parents=True, exist_ok=True)
    registry.publications_path.write_text("{no es json", encoding="utf-8")

    publication = models(client_for(tmp_path, registry))["1.0.0"].publication

    assert publication.status == "inconsistent"
    assert "s3_publications.json" in publication.problem


# --- Lo que S3 dice de verdad (revisión del PR #63, rúbrica 6.4) ----------------------


def _uploaded(registry: Registry) -> FakeS3:
    return FakeS3(json.loads(json.dumps(registry.publications)))


def _assert_not_shown_as_published(publication, status: str, *fragments: str) -> None:
    assert publication.status == status
    assert publication.objects == [] and publication.bucket is None
    assert publication.region is None and publication.published_at is None
    for fragment in fragments:
        assert fragment in publication.problem
    assert "models/" not in publication.problem, "el problema no muestra keys"


def test_every_published_object_is_asked_to_s3_with_its_region_and_version(tmp_path, registry):
    record = registry.publish("1.0.0")
    record["files"]["checkpoint/best.pt"]["version_id"] = "v-checkpoint"
    registry.save_publications()
    s3 = _uploaded(registry)

    publication = models(client_for(tmp_path, registry, s3))["1.0.0"].publication

    assert publication.status == "published"
    asked = {(bucket, region, key, version) for bucket, region, key, version in s3.calls}
    expected = {
        (BUCKET, "us-east-1", entry["key"], entry["version_id"])
        for entry in record["files"].values()
    }
    assert asked == expected


def test_a_key_that_does_not_exist_in_s3_is_inconsistent(tmp_path, registry):
    """Regresión del revisor: otra key para model-card.md (404 en S3) seguía published."""
    record = registry.publish("1.0.0")
    s3 = _uploaded(registry)
    record["files"]["model-card.md"]["key"] = f"models/{MODEL}/1.0.0/no-existe.md"
    registry.save_publications()

    publication = models(client_for(tmp_path, registry, s3))["1.0.0"].publication

    _assert_not_shown_as_published(publication, "inconsistent", "model-card.md", "no existe en S3")


def test_an_object_deleted_from_s3_is_inconsistent(tmp_path, registry):
    registry.publish("1.0.0")
    s3 = _uploaded(registry)
    s3.objects.pop(next(key for key in s3.objects if key[1].endswith("checkpoint/best.pt")))

    publication = models(client_for(tmp_path, registry, s3))["1.0.0"].publication

    _assert_not_shown_as_published(publication, "inconsistent", "checkpoint/best.pt")


def test_another_version_id_of_the_object_is_not_the_published_one(tmp_path, registry):
    record = registry.publish("1.0.0")
    record["files"]["model-card.md"]["version_id"] = "v1"
    registry.save_publications()
    s3 = _uploaded(registry)
    record["files"]["model-card.md"]["version_id"] = "v2"
    registry.save_publications()

    publication = models(client_for(tmp_path, registry, s3))["1.0.0"].publication

    _assert_not_shown_as_published(publication, "inconsistent", "model-card.md")


def test_an_object_whose_s3_checksum_is_not_the_registered_sha256_is_inconsistent(
    tmp_path, registry
):
    registry.publish("1.0.0")
    s3 = _uploaded(registry)
    card = next(key for key in s3.objects if key[1].endswith("model-card.md"))
    s3.objects[card] = "0" * 64

    publication = models(client_for(tmp_path, registry, s3))["1.0.0"].publication

    _assert_not_shown_as_published(publication, "inconsistent", "model-card.md", "ChecksumSHA256")


def test_an_object_without_checksum_in_s3_is_not_published(tmp_path, registry):
    registry.publish("1.0.0")

    class NoChecksum(FakeS3):
        def head(self, **kwargs):
            found = super().head(**kwargs)
            return None if found is None else S3Head(checksum_sha256=None)

    s3 = NoChecksum(json.loads(json.dumps(registry.publications)))

    publication = models(client_for(tmp_path, registry, s3))["1.0.0"].publication

    _assert_not_shown_as_published(publication, "inconsistent", "ChecksumSHA256")


def test_without_aws_credentials_the_publication_is_unverifiable(tmp_path, registry):
    registry.publish("1.0.0")
    s3 = _uploaded(registry)
    s3.error = "ml-api no tiene credenciales de AWS."

    listed = models(client_for(tmp_path, registry, s3))

    _assert_not_shown_as_published(listed["1.0.0"].publication, "unverifiable", "credenciales")
    assert listed["1.1.0"].publication.status == "not_published", "sin registro no se consulta S3"


def test_without_a_verifier_nothing_is_shown_as_published(tmp_path, registry):
    registry.publish("1.0.0")

    publication = models(client_for(tmp_path, registry, None))["1.0.0"].publication

    _assert_not_shown_as_published(publication, "unverifiable", "S3")


def test_a_local_inconsistency_is_reported_before_asking_s3(tmp_path, registry):
    record = registry.publish("1.0.0", run_id="f" * 32)
    s3 = _uploaded(registry)
    s3.error = "sin credenciales"

    publication = models(client_for(tmp_path, registry, s3))["1.0.0"].publication

    assert publication.status == "inconsistent" and record["run_id"] in publication.problem
    assert s3.calls == []


def test_the_detail_endpoint_verifies_s3_too(tmp_path, registry):
    record = registry.publish("1.0.0")
    s3 = _uploaded(registry)
    record["files"]["model-card.md"]["key"] = f"models/{MODEL}/1.0.0/no-existe.md"
    registry.save_publications()

    response = client_for(tmp_path, registry, s3).get("/models/1.0.0")

    publication = RegisteredModelVersion.model_validate(response.json()).publication
    assert publication.status == "inconsistent"


# --- Descargas autorizadas -----------------------------------------------------------


@pytest.mark.parametrize("name", ["model-card.md", "dependencies.json", "checkpoint/best.pt"])
def test_package_files_can_be_downloaded(tmp_path, registry, name):
    path = registry.root / registry.packages[0]["package_path"] / name

    response = client_for(tmp_path, registry).get(f"/models/1.0.0/files/{name}")

    assert response.status_code == 200
    assert "attachment" in response.headers["content-disposition"]
    assert response.content == path.read_bytes()


@pytest.mark.parametrize(
    "name",
    ["package.json", "../../registry.json", "..%2F..%2F..%2Freports%2Fmodels%2Fregistry.json"],
    ids=["not-in-the-package", "traversal", "encoded-traversal"],
)
def test_only_registered_package_files_are_served(tmp_path, registry, name):
    response = client_for(tmp_path, registry).get(f"/models/1.0.0/files/{name}")

    assert response.status_code == 404
    # `../` sin codificar lo normaliza el cliente HTTP (llega a /models/registry.json).
    assert ErrorResponse.model_validate(response.json()).error.code in {
        "file_not_found",
        "model_not_found",
    }
    assert registry.path.read_text(encoding="utf-8") not in response.text


def test_encoded_traversal_reaches_the_whitelist(tmp_path, registry):
    response = client_for(tmp_path, registry).get(
        "/models/1.0.0/files/..%2F..%2F..%2Freports%2Fmodels%2Fregistry.json"
    )

    assert ErrorResponse.model_validate(response.json()).error.code == "file_not_found"


def test_altered_or_missing_file_is_not_served(tmp_path, registry, checkpoints):
    registry.checkpoint("1.0.0").write_bytes(checkpoints["b"].read_bytes())
    registry.checkpoint("1.1.0").unlink()
    client = client_for(tmp_path, registry)

    altered = client.get("/models/1.0.0/files/checkpoint/best.pt")
    missing = client.get("/models/1.1.0/files/checkpoint/best.pt")

    assert altered.status_code == 409
    assert ErrorResponse.model_validate(altered.json()).error.code == "file_not_servable"
    assert missing.status_code == 404
    assert ErrorResponse.model_validate(missing.json()).error.code == "file_not_available"


# --- Datos reales del repo (OPS-06 + OPS-07) -----------------------------------------


def _real_client(tmp_path: Path, s3) -> TestClient:
    queue = TrainingJobQueue(create_engine(f"sqlite:///{tmp_path / 'jobs.db'}"))
    queue.create_tables()
    return TestClient(
        create_app(queue=queue, reports_dir=ROOT / "reports", repo_root=ROOT, s3_verifier=s3)
    )


def _real_publications() -> list[dict]:
    path = ROOT / "reports" / "models" / "s3_publications.json"
    return json.loads(path.read_text("utf-8"))["publications"]


# AWS-3: la publicación vigente es la del bucket del equipo. La de OPS-07 (bucket de la
# cuenta anterior) sigue en s3_publications.json como histórico.
TEAM_BUCKET = "mlops-p4-equipo-452857281704"


def test_real_registry_and_s3_publication(tmp_path):
    """Con S3 confirmando cada objeto de la publicación real vigente → published."""
    registry = json.loads((ROOT / "reports" / "models" / "registry.json").read_text("utf-8"))

    listed = models(_real_client(tmp_path, FakeS3(_real_publications())))

    entry = registry["models"][0]
    model = listed[entry["model_version"]]
    assert (model.run_id, model.checkpoint_sha256) == (entry["run_id"], entry["checkpoint_sha256"])
    assert model.publication.status == "published"
    assert model.publication.bucket == TEAM_BUCKET
    assert {obj.name for obj in model.publication.objects} >= set(entry["files"])


def test_real_publication_without_aws_is_unverifiable(tmp_path):
    s3 = FakeS3(_real_publications())
    s3.error = "ml-api no tiene credenciales de AWS."

    for model in models(_real_client(tmp_path, s3)).values():
        assert model.publication.status != "published"
        assert model.publication.objects == []
