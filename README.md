# Portal de anotación de imágenes

Monolito para subir, anotar y exportar un dataset de detección de objetos.
Las imágenes se almacenan en MinIO; los metadatos y las anotaciones en MariaDB.

## Estructura

```text
backend/    API HTTP con Express (UI → Logic → Data)
frontend/   Interfaz React + Vite (upload, anotación, dashboard, búsqueda)
```

Cada carpeta es un paquete npm independiente con su propio `package.json`.

## Arquitectura

```text
frontend  →  backend
                ├── src/ui      Endpoints HTTP
                ├── src/logic   Reglas de negocio y validación con Zod
                └── src/data    Drizzle (MariaDB) y MinIO
                                    ├── MariaDB  metadatos y anotaciones
                                    └── MinIO    archivos binarios
```

La capa UI nunca accede a MariaDB ni a MinIO: solo invoca a `logic`. La capa
`logic` es la única que puede importar de `data`.

Todo dato que entra por HTTP se valida con Zod antes de llegar a la capa de
datos, y los tipos se infieren del esquema con `z.infer`. La capa Logic lanza
errores tipados que la UI mapea a códigos HTTP:

| Error             | HTTP | Cuándo                                       |
|-------------------|------|----------------------------------------------|
| `ValidationError` | 400  | Dato mal formado o regla de negocio violada  |
| `NotFoundError`   | 404  | El recurso no existe en la base de datos     |

## Contribuir

Convención de ramas, commits y PR, qué valida el CI y cómo correrlo en tu máquina:
[CONTRIBUTING.md](CONTRIBUTING.md).

## Onboarding de desarrollo

Sigue esta sección de arriba hacia abajo en un clon nuevo. El proyecto tiene
dos entornos Python separados: `app/.venv` para el pipeline y `.venv-dvc`
para DVC. No los mezcles.

### 1. Herramientas necesarias

Obligatorias para el trabajo habitual:

- Git.
- Python 3.12.
- [`uv`](https://docs.astral.sh/uv/getting-started/installation/) para el
  entorno Python de `app/`.
- Docker Desktop y Docker Compose si vas a levantar los servicios locales.
- Node.js y npm si vas a desarrollar o probar `backend/` y `frontend/`.
- AWS CLI v2 si necesitas leer el dataset de producción desde S3.

Opcionales:

- Terraform CLI, únicamente para validar o trabajar en infraestructura con
  autorización explícita.
- MinIO local, únicamente para el remote DVC `dev`. No es necesario para
  recuperar el dataset de producción.

No necesitas access keys permanentes para el onboarding. El acceso de AWS de
este proyecto usa IAM Identity Center / SSO con tu propia identidad.

### 2. Clonar el repositorio

```bash
git clone https://github.com/White-eclipse1/Proyecto-03-team5.git
cd proyecto-fase2-MLOPS
git status
```

La comprobación inicial debe mostrar la rama y el estado del clon. No asumas
una ruta local concreta: trabaja desde la carpeta que acabas de clonar.

### 3. Preparar Python del pipeline

Desde `app/`, instala exactamente las dependencias fijadas por `uv.lock`:

```bash
cd app
uv sync --locked --no-build
uv run python --version
uv run pytest -q
cd ..
```

`uv` crea o utiliza `app/.venv`. Este entorno corresponde al pipeline,
quality gate, analyzers, tests y Copilot Python. No lo sustituyas por
`.venv-dvc`, que es exclusivo de DVC.

### 4. Preparar el entorno separado de DVC

Desde la raíz del repositorio:

```bash
python3.12 -m venv .venv-dvc
source .venv-dvc/bin/activate
python -m pip install 'dvc[s3]==3.67.1'
python --version
dvc --version
dvc remote list
```

En PowerShell, activa el mismo entorno con:

```powershell
py -3.12 -m venv .venv-dvc
.venv-dvc\Scripts\Activate.ps1
```

El repositorio ya está inicializado y ya contiene sus remotes. **No ejecutes
`dvc init`.**

### 5. Comprobar AWS CLI v2 (macOS)

Comprueba primero si ya está instalada:

```bash
aws --version
```

Si no aparece el comando, instala AWS CLI v2 siguiendo el instalador oficial
para macOS de [AWS](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html).
Por ejemplo, el instalador oficial puede ejecutarse así:

```bash
curl "https://awscli.amazonaws.com/AWSCLIV2.pkg" -o "/tmp/AWSCLIV2.pkg"
sudo installer -pkg "/tmp/AWSCLIV2.pkg" -target /
aws --version
```

### 6. Configurar IAM Identity Center / SSO

Cada integrante tiene su propio usuario de IAM Identity Center. No recibas ni
copies el password, la sesión SSO o las credenciales de otra persona.

Ejecuta:

```bash
aws configure sso --profile mlops-p2
```

Cuando la CLI lo solicite, responde:

| Pregunta | Valor |
|---|---|
| SSO session name | `mlops-p2` |
| SSO start URL | `https://d-906661837a.awsapps.com/start` |
| SSO region | `us-east-1` |
| Registration scopes | `sso:account:access` |

Se abrirá el navegador. Inicia sesión con **tu propio usuario** de IAM
Identity Center, selecciona la cuenta que te haya asignado el administrador y
elige el permission set que te haya autorizado. El README no fija nombres de
usuarios, contraseñas, cuentas ni identificadores personales.

Después inicia la sesión y comprueba la identidad efectiva:

```bash
aws sso login --profile mlops-p2
aws sts get-caller-identity --profile mlops-p2
```

La salida debe corresponder a tu sesión autorizada. Cuando expire, normalmente
basta con renovar la sesión:

```bash
aws sso login --profile mlops-p2
```

La configuración del perfil y la caché de la sesión se guardan fuera del
repositorio, en la configuración local de AWS CLI. No copies esos archivos al
proyecto ni los compartas.

### 7. Conectar DVC con el perfil local de AWS

Con `.venv-dvc` activado, configura el remote `prod` solo en tu máquina:

```bash
dvc remote modify --local prod profile mlops-p2
git check-ignore .dvc/config.local
dvc remote list
```

La opción `--local` es obligatoria: escribe el perfil en `.dvc/config.local`,
no en la configuración versionada de `.dvc/config`. Ese archivo local debe
permanecer ignorado y nunca subirse a Git.

### 8. Comprobar lectura del bucket de producción

Estas comprobaciones son de lectura y no modifican datos:

```bash
aws s3api head-bucket \
  --bucket mlops-p2-dvc-cache-280764207006 \
  --profile mlops-p2

aws s3api list-objects-v2 \
  --bucket mlops-p2-dvc-cache-280764207006 \
  --max-keys 1 \
  --query KeyCount \
  --profile mlops-p2
```

Si terminan correctamente, tu sesión puede alcanzar el bucket y tiene los
permisos requeridos para esas operaciones. Después puedes consultar el estado
de los metadatos DVC sin subir datos:

```bash
dvc status -r prod data/raw/images.dvc data/raw/annotations.dvc
```

Descarga el dataset únicamente cuando realmente lo necesites:

```bash
dvc pull -r prod data/raw/images.dvc data/raw/annotations.dvc
```

`dvc pull` materializa archivos en tu máquina, pero no sube nada a S3. No uses
`dvc push` como prueba de conectividad; publicar requiere autorización de
escritura y una tarea explícita.

### 9. Permisos y responsabilidades del administrador

Para que el flujo funcione, el administrador debe haber creado o asignado tu
usuario en IAM Identity Center, asignado la cuenta AWS correspondiente y
asignado un permission set con acceso S3. Para lectura del remote DVC se
necesitan conceptualmente permisos equivalentes a `s3:ListBucket` y
`s3:GetObject`. Publicar datasets requiere permisos adicionales de escritura
definidos por el administrador.

### 10. MinIO / `dev` (opcional)

Los remotes no son intercambiables:

- `prod` = AWS S3 del equipo, bucket `mlops-p4-equipo-452857281704` (us-east-2),
  remoto por defecto desde AWS-3. Ver [Datos del proyecto](#datos-del-proyecto).
- `p2-origen` = el remoto original de la cuenta anterior, bucket
  `mlops-p2-dvc-cache-280764207006` (solo lectura, con el perfil SSO `mlops-p2`
  de los pasos 6 a 8). Se conserva sin cambios.
- `dev` = MinIO local, bucket `dvc-cache`.

Si solo necesitas recuperar el dataset de producción, no levantes MinIO. El
flujo opcional completo está documentado en [P2-04 — MinIO local y remotes
DVC](#p2-04--minio-local-y-remotes-dvc). Sus credenciales son locales de
MinIO y no tienen relación con AWS SSO.

### 11. Terraform (opcional y autorizado)

Terraform local puede usar el perfil AWS `mlops-p2` mediante la cadena normal de
credenciales. GitHub Actions usa OIDC, que es un mecanismo distinto; OIDC de
GitHub no autentica automáticamente tu Mac. No ejecutes `terraform apply` ni
`terraform destroy` como parte del onboarding. Tampoco inicialices el backend
remoto hasta que el administrador proporcione y confirme el bucket de state.
Consulta [terraform/README.md](terraform/README.md) para la validación estática
y los límites operativos.

### 12. Variables locales y seguridad

El `.env` de la raíz es para configuración local de Compose/MinIO/Copilot. No
coloques credenciales AWS, passwords, sesiones SSO ni access keys en `.env`.
`ANTHROPIC_API_KEY` es opcional y solo se necesita para utilizar el chat
Copilot; nunca pongas una API key real en esta documentación.

Cada persona usa su propia identidad AWS, no comparte passwords, sesiones SSO
ni access keys, y mantiene `.dvc/config.local` fuera de Git.

## Datos del proyecto

El dataset y el modelo del Proyecto 3 están en el bucket de la **cuenta del
equipo** (AWS-3). La entrega ya no depende de la cuenta anterior.

| Remoto DVC | Bucket | Región | Uso |
|---|---|---|---|
| `prod` (por defecto) | `s3://mlops-p4-equipo-452857281704` | `us-east-2` | El que usa todo el equipo |
| `p2-origen` | `s3://mlops-p2-dvc-cache-280764207006` | `us-east-1` | Original de la cuenta anterior, solo lectura. No se modifica |

El bucket es privado: acceso público bloqueado, objetos con dueño único, cifrado
SSE-S3, versionado activo y política que rechaza conexiones sin HTTPS. Contiene:

| Prefijo | Qué hay | Quién escribe |
|---|---|---|
| `files/md5/...` | Caché de DVC: dataset, recortes, modelos y snapshot de MLflow | El equipo con `dvc push` |
| `models/dog-cat-resnet18/<versión>/` | Paquetes publicados del modelo (1.0.0 y 0.9.0), registrados en `reports/models/s3_publications.json` con `ChecksumSHA256` y `VersionId` | El equipo con `classification.publication publish` |
| `edge-captures/` | Capturas de Capturas Edge (AWS-1) | El servidor del portal, con su rol |

### Bajar los datos

Con tu propia identidad en el proyecto de AWS del equipo (no la de la cuenta
anterior). Las credenciales quedan en tu perfil de AWS y en `.dvc/config.local`,
nunca en archivos versionados:

```bash
aws login --profile <tu-perfil>          # región us-east-2
uv venv .venv-dvc --python 3.12
uv pip install --python .venv-dvc 'dvc[s3]==3.67.1' 'botocore[crt]'
source .venv-dvc/bin/activate             # Windows: .venv-dvc\Scripts\activate
dvc remote modify --local prod profile <tu-perfil>
dvc pull
```

`botocore[crt]` es obligatorio con perfiles de `aws login`. Sin él, DVC falla con
`Using the login credential provider requires an additional dependency`.

Los comandos de este README que dicen `dvc pull -r prod ...` ya apuntan al bucket
del equipo. El CI sigue leyendo `p2-origen`, porque su rol OIDC vive en la cuenta
anterior. Moverlo al bucket del equipo requiere crear un rol OIDC en la cuenta nueva.

### Cómo se copió (y cómo repetirlo)

El 2026-10-06 la copia se hizo desde una copia local del bucket original, que tiene
la misma estructura `files/md5/...` que el remoto de DVC:

```bash
aws s3 sync <copia-local>/files s3://mlops-p4-equipo-452857281704/files --profile <perfil-equipo>
```

Para repetirla directo de bucket a bucket con DVC, se usan dos perfiles: uno con
lectura del origen y otro con escritura en el destino:

```bash
dvc remote modify --local p2-origen profile mlops-p2       # lectura, cuenta anterior
dvc remote modify --local prod profile <perfil-equipo>      # escritura, cuenta del equipo
dvc pull -r p2-origen                                       # todo lo versionado
dvc push -r prod
dvc status -c -r prod                                       # "Cache and remote 'prod' are in sync."
```

El bucket se creó así (no hace falta repetirlo):

```bash
B=mlops-p4-equipo-452857281704; P="--profile <perfil-equipo> --region us-east-2"
aws s3api create-bucket --bucket $B --create-bucket-configuration LocationConstraint=us-east-2 $P
aws s3api put-public-access-block --bucket $B $P \
  --public-access-block-configuration BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true
aws s3api put-bucket-versioning --bucket $B --versioning-configuration Status=Enabled $P
# Más cifrado SSE-S3 por defecto y una bucket policy que niega `aws:SecureTransport = false`.
```

**Verificación (2026-10-06):** en un checkout limpio, fuera del repo de trabajo y
con una identidad del proyecto del equipo (sin la cuenta anterior), `dvc pull` bajó
600 imágenes, 10 anotaciones, 8 archivos de modelos, 52 del snapshot de MLflow y 668
recortes. `dvc status` respondió "Data and pipelines are up to date" y
`dvc status -c -r prod` "Cache and remote 'prod' are in sync". En el bucket hay
1367 objetos en `files/`, los mismos de la copia del original.

### Rol de IAM del servidor

La instancia del portal (ver [Despliegue en AWS](#despliegue-en-aws)) usa el rol
`portal-proyecto4-ec2`, mediante el perfil de instancia del mismo nombre, sin access
keys. Su política inline `s3-models-read-edge-captures-write` permite solo:

| Acción | Recurso |
|---|---|
| `s3:GetObject`, `s3:GetObjectVersion` | `models/*` |
| `s3:PutObject` | `edge-captures/*` |
| `s3:ListBucket` | El bucket, solo con prefijo `models/` o `edge-captures/` |

Probado desde el contenedor `ml-api`: escribir en `edge-captures/` y leer o listar
`models/` funciona. Escribir en `models/`, listar `files/` y borrar en
`edge-captures/` responde `AccessDenied`.

Para que los contenedores puedan usar el rol, la instancia tiene IMDSv2 obligatorio
con `HttpPutResponseHopLimit=2`, y `docker-compose.aws.yml` pone
`AWS_EC2_METADATA_DISABLED=false` en `ml-api`. `backend` no define esa variable.

## Requisitos

La lista completa y secuencial de instalación está en
[Onboarding de desarrollo](#onboarding-de-desarrollo). Para ejecutar la
aplicación local también se necesitan Docker y Docker Compose.

## Despliegue con un solo comando

> **¿Ya tenías el proyecto levantado antes del issue #36?** La imagen de MinIO
> cambió y tu volumen sigue funcionando. Si quieres un respaldo, hazlo después del
> `git pull` y antes del primer `docker compose up`: ver
> [Cambio de imagen de MinIO (issue #36)](#cambio-de-imagen-de-minio-issue-36).

Antes del primer arranque, crea el `.env` local para Compose y completa los
tres valores obligatorios (`MARIADB_ROOT_PASSWORD`, `MINIO_ROOT_USER` y
`MINIO_ROOT_PASSWORD`) con credenciales locales:

```bash
cp .env.example .env
chmod 600 .env
```

`ANTHROPIC_API_KEY` puede permanecer vacío si no vas a usar el chat Copilot.
No pongas credenciales AWS en este archivo.


Antes de levantar el stack, define `GIT_COMMIT` con el SHA real del commit
actual. El worker de entrenamiento lo usa para registrar la procedencia de
cada run y Compose rechaza valores ausentes.

En macOS/Linux:

    export GIT_COMMIT="$(git rev-parse HEAD)"
    docker compose config --quiet
    docker compose up --build

En PowerShell:

    $env:GIT_COMMIT = git rev-parse HEAD
    docker compose config --quiet
    docker compose up --build

`GIT_COMMIT` debe corresponder al SHA real mostrado por `git rev-parse HEAD`.


Este comando levanta los servicios de MariaDB, MinIO, MLflow, backend, frontend,
pipeline `app`, Copilot y la API de jobs de entrenamiento (`ml-api`). El backend espera a que MariaDB y MinIO estén listos, aplica las
migraciones y siembra únicamente las categorías `dog` y `cat` antes de
arrancar; no crea imágenes demo ni hace falta ejecutar otro paso manual.

### Proyecto 3 completo en un clon limpio (datos, modelo y corridas)

`docker compose up` levanta el portal, pero las pantallas del Proyecto 3 necesitan
datos que no viven en git: los recortes de ML-01, el paquete del modelo publicado
(OPS-06) y las corridas de MLflow (ML-07 a ML-09, con sus mismos run IDs). Después
de configurar DVC y AWS (pasos 4 a 7 del [onboarding](#onboarding-de-desarrollo)),
desde la raíz y **en la misma terminal** de principio a fin (el paso 4 usa el
`GIT_COMMIT` del paso 3):

```bash
# 1. Datos: el release P2 (lo exige el servicio `app`, la compuerta de calidad; sin él
#    `docker compose up --wait` falla) y los del Proyecto 3
dvc pull -r prod data/raw/images.dvc data/raw/annotations.dvc
dvc pull -r prod crops                       # data/crops (recortes de ML-01)
dvc pull -r prod data/models.dvc             # data/models (dog-cat-resnet18 1.0.0 y 0.9.0)
dvc pull -r prod data/mlflow-snapshot.dvc    # data/mlflow-snapshot (corridas de MLflow)

# 2. Credenciales de AWS para que Models verifique la publicación en S3 (opcional;
#    sin ellas Models muestra "No verificable"). No se escriben en ningún archivo.
eval "$(aws configure export-credentials --profile mlops-p2 --format env)"

# 3. Levantar el stack
export GIT_COMMIT="$(git rev-parse HEAD)"
docker compose up -d --build --wait

# 4. Cargar las corridas en el MLflow del stack (solo en un stack nuevo: reemplaza
#    la base `mlflow` local por la del snapshot)
cd app
MLFLOW_TRACKING_URI=http://localhost:5000 uv run python -m tracking.snapshot restore
```

En PowerShell, los pasos 2 y 3 son
`aws configure export-credentials --profile mlops-p2 --format powershell | Invoke-Expression`
y `$env:GIT_COMMIT = git rev-parse HEAD`, y el paso 4
`$env:MLFLOW_TRACKING_URI = "http://localhost:5000"; uv run python -m tracking.snapshot restore`.

Con eso, en `http://localhost:8080`:

| Pantalla | Qué se ve |
|---|---|
| Training | Release `v0.1.1` con su procedencia DVC y el manifiesto 70/20/10; lanza jobs reales |
| Experiments | Las 12 corridas de ML-07, entre ellas el candidato `ml07-v1-r03-sgd` |
| Evaluation | El candidato congelado y su evaluación final de test (68/71) |
| Models | `dog-cat-resnet18 1.0.0` (candidato, vigente) y `0.9.0` (versión anterior), cada una con su paquete y su publicación en S3; elegir otra versión cambia el checkpoint que usa Inference |
| Inference | Clasifica recortes e imágenes nuevas con la versión elegida y envía el resultado a la cola de anotación |

El recorrido completo, con la cadena de IDs de punta a punta, lo comprueba
`tests/test_app10_portal_smoke.py` contra el stack levantado:

```bash
cd app
APP10_PORTAL_URL=http://localhost:8080 uv run pytest tests/test_app10_portal_smoke.py -v
```

Detalles: snapshot de MLflow en
[`app/classification/README.md`](app/classification/README.md#compartir-las-corridas-snapshot-de-mlflow)
y credenciales de Models en [`app/training/README.md`](app/training/README.md#credenciales-de-aws-para-models).

### Smoke training corto de OPS-05

Antes del smoke, el checkout debe tener materializados los datos del release
y los crops de clasificación. En un clon limpio, después de completar la
configuración de DVC/AWS descrita arriba, ejecuta desde la raíz:

```bash
dvc pull -r prod data/raw/images.dvc data/raw/annotations.dvc
dvc repro crops manifest
```
Después levanta el stack completo:

```bash
docker compose up --build
```
Desde otra terminal ejecuta:

```bash
cd app
uv run python -m training.smoke
```

El smoke test utiliza el release `v0.1.1` y crea un job real con:

- `max_epochs = 1`
- `image_size = 32`
- `batch_size = 128`

La prueba verifica de extremo a extremo:

```text
portal /api/ml
→ cola persistente en MariaDB
→ training-worker
→ MLflow
→ checkpoint checkpoints/best.pt
```

El smoke no requiere GPU. El entrenamiento es compatible con CPU y no exige CUDA para ejecutarse.

Si el flujo termina correctamente, la salida incluye:

```text
OPS-05 SMOKE OK
job_id=...
run_id=...
checkpoint=runs:/<run_id>/checkpoints/best.pt
```

El comando falla con código distinto de cero si:

- el API no está disponible;
- el release requerido no existe;
- el job termina en estado `failed`;
- se supera el timeout;
- no se obtiene un `run_id`;
- el checkpoint no coincide con `checkpoints/best.pt`.



| Servicio        | URL                              |
|-----------------|-----------------------------------|
| Frontend        | http://localhost:8080            |
| Backend (API)   | http://localhost:3100            |
| Consola MinIO   | http://localhost:9001 (credenciales `MINIO_ROOT_*` de tu `.env`) |
| MLflow (UI/API) | http://localhost:5000 (solo loopback; ver [OPS-03](#ops-03--mlflow-persistente)) |
| API de entrenamiento | http://localhost:8080/api/ml/ (vía nginx; ver [APP-03](#app-03--jobs-de-entrenamiento)) |

Para apagar normalmente los servicios, sin borrar los datos persistidos:

```bash
docker compose down
```

`docker compose down -v` elimina también los volúmenes de MariaDB y MinIO
(y con ellos los runs y artefactos de MLflow).
Úsalo únicamente cuando quieras reiniciar desde cero los datos locales.

Las credenciales de MariaDB/MinIO usadas en `docker-compose.yml` son las de
desarrollo del proyecto; para un despliegue real, cámbialas ahí antes de
publicar los puertos a una red no confiable.

## Cambio de imagen de MinIO (issue #36)

Desde 2026, la imagen oficial de MinIO (`quay.io/minio/minio`, y `minio/minio` en
Docker Hub) ya no se puede descargar sin autenticación. Por eso un clon nuevo no
podía hacer `docker compose up`. `docker-compose.yml` ahora usa la build pública de
Chainguard, `cgr.dev/chainguard/minio:latest` (misma CLI `minio server`), con
`user: "0:0"`.

**Tus datos locales no cambian de lugar.** La imagen nueva lee el volumen
`minio_data` creado con la anterior: buckets y objetos siguen ahí. No hace falta
migrar ni borrar nada; basta con:

```bash
git pull
docker compose up -d --build
```

El dataset oficial (600 imágenes + COCO del release `v0.1.1`) tampoco depende de
MinIO: vive en el remote DVC `prod` (AWS S3) y se recupera con `dvc pull -r prod`.

### Respaldo opcional antes de actualizar

La imagen nueva trae una versión más reciente de MinIO, que podría actualizar el
formato del volumen al arrancar. Si quieres una copia por si acaso, haz el respaldo
**después del `git pull` y antes del primer `up`**. `git pull` solo cambia archivos
del repo (y trae el script); tu volumen no lo toca nadie hasta que arranca MinIO.

```bash
docker compose down                      # sin -v: quita los contenedores, conserva los volúmenes
git pull                                 # trae la imagen nueva y scripts/minio-backup.sh
bash scripts/minio-backup.sh inventory   # solo lectura: qué buckets y objetos tienes
bash scripts/minio-backup.sh backup      # copia exacta → volumen <proyecto>_minio_backup
docker compose up -d --build             # recién aquí la imagen nueva abre tu volumen
```

`backup` no arranca ningún MinIO: copia los archivos del volumen con un contenedor
`alpine` que monta el original **en solo lectura**, y compara el sha256 de cada
archivo del original y de la copia. Así la copia queda en el formato anterior (sirve
incluso para volver a la imagen vieja). Si algo no coincide, termina con error y
borra la copia incompleta.

Qué suele aparecer en `inventory`:

| Bucket | Qué es |
|--------|--------|
| `dvc-cache` | Remote DVC `dev`: copia del dataset que ya está en `prod` (S3). |
| `image-annotations` | Imágenes subidas al portal en local. `seed/sample-red.png` y `seed/sample-blue.png` son de prueba (las creaba una versión vieja del seeder). |
| `mlflow` | Artefactos de MLflow (OPS-03), si ya corriste experimentos. |

### Si algo salió mal: restaurar el respaldo

```bash
docker compose down                         # sin -v: el volumen debe quedar libre
docker volume rm <proyecto>_minio_data      # restore solo escribe en un volumen vacío
bash scripts/minio-backup.sh restore        # copia exacta del respaldo, verificada con sha256
docker compose up -d
```

Cuando todo esté bien: `docker volume rm <proyecto>_minio_backup`.

Usa `docker compose down` y no `stop`: un contenedor detenido sigue asociado al
volumen, y entonces `docker volume rm` falla. El script se niega a correr mientras
algún contenedor use el volumen. `<proyecto>` es el nombre de la carpeta del repo en
minúsculas (`docker volume ls | grep minio_data` te lo muestra), o
`COMPOSE_PROJECT_NAME` si lo defines.

## Desarrollo local sin Docker para las apps

Para iterar con hot reload en backend y frontend, puedes levantar solo la
infraestructura con Docker y correr los paquetes Node directamente en tu
máquina:

### 1. Infraestructura

```bash
docker run --name proyecto1-mariadb \
  -e MARIADB_ROOT_PASSWORD=password \
  -e MARIADB_DATABASE=image_repo \
  -p 3306:3306 -d mariadb:11

docker run --name proyecto1-minio --user 0:0 \
  -p 9000:9000 -p 9001:9001 \
  -e MINIO_ROOT_USER=minioadmin \
  -e MINIO_ROOT_PASSWORD=minioadmin \
  -d cgr.dev/chainguard/minio:latest server /data --console-address ":9001"
```

El bucket se crea automáticamente al arrancar el backend.

### 2. Backend

Antes de ejecutar esos comandos, crea `backend/.env` con la configuración de
desarrollo siguiente. Este archivo es distinto del `.env` de la raíz que usa
Docker Compose:

```dotenv
DATABASE_URL=mysql://root:password@localhost:3306/image_repo
MINIO_ENDPOINT=localhost
MINIO_PORT=9000
MINIO_USE_SSL=false
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin
MINIO_BUCKET=image-annotations
MAX_UPLOAD_SIZE_BYTES=10485760
```

No pongas credenciales AWS en `backend/.env` tampoco. Si cambias el puerto
publicado de MariaDB, ajusta `DATABASE_URL` en este archivo.

```bash
cd backend
npm ci
npm run db:migrate
npm run db:seed
npm run dev
```

Queda escuchando en `http://localhost:3000`.

Si el puerto 3306 ya está ocupado en tu máquina, publica MariaDB en otro
puerto (por ejemplo `-p 3307:3306`) y ajusta `DATABASE_URL` en `backend/.env`.
Nada está fijo en el código: puertos, credenciales y bucket salen del `.env`.

### 3. Frontend

```bash
cd frontend
npm ci
cp .env.example .env
npm run dev
```

Queda escuchando en `http://localhost:5173` y consume la API del backend a
través del proxy `/api` configurado en `vite.config.ts`.

### 4. Comprobación

```bash
curl http://localhost:3000/health
```

Respuesta esperada:

```json
{"status":"ok","database":"connected","timestamp":"..."}
```

## Producción

La forma recomendada de desplegar es `docker compose up --build` (ver
[Despliegue con un solo comando](#despliegue-con-un-solo-comando)): construye
las imágenes de backend y frontend y levanta MariaDB y MinIO junto con ellas.

Si necesitas correr el backend fuera de Docker contra tu propia
infraestructura:

```bash
cd backend
npm run build
npm run start:prod
```

El servidor de producción escucha en `http://localhost:3100`. El script usa
`cross-env`, por lo que funciona igual en Windows, macOS y Linux.

La plantilla `.env.production.example` contiene la configuración de
producción, con `PORT=3100`.

Para publicar el portal en un servidor de AWS, ver
[Despliegue en AWS](#despliegue-en-aws).

## Despliegue en AWS

El portal corre en **un solo servidor EC2 con IP pública** que ejecuta el mismo
`docker-compose.yml` del repo, más
[`docker-compose.aws.yml`](docker-compose.aws.yml). Ese archivo solo cambia dos
cosas: publica nginx en el puerto 80 (en local es el 8080) y deja los demás puertos
accesibles únicamente desde el propio servidor. No se usa Terraform ni RDS: MariaDB
y MinIO siguen en contenedores, con sus volúmenes en el disco de la instancia.

Todo se hace desde la consola web de AWS y una terminal SSH. Esta guía no contiene
claves ni contraseñas, y ninguna debe agregarse aquí.

> **Región: `us-east-2` (Ohio).** La cuenta nueva del equipo es un *proyecto* de la
> nueva experiencia de AWS: todos sus recursos van en la región del proyecto. Las
> políticas del proyecto bloquean `us-east-1` (una consulta de solo lectura a EC2 en
> esa región devuelve `explicit deny in a service control policy`). Para confirmar
> la región: AWS Settings > View all projects > Overview > Additional info > Region.
> Desde AWS-3, los datos y el modelo también están en un bucket del equipo en esta
> misma región (ver [Datos del proyecto](#datos-del-proyecto)).

### Datos del despliegue

Actualiza esta tabla cuando cambie algo del servidor (sin secretos):

| Dato | Valor |
|---|---|
| Estado | Encendida desde el 2026-10-06. Para no consumir créditos: EC2 > Instances > *Instance state* > **Stop**; para volver a usarla, **Start** |
| URL del portal | **http://18.216.36.30**. Es una Elastic IP (`eipalloc-06bfd73237d154119`, asignada el 2026-10-07): no cambia aunque la instancia se detenga y se vuelva a iniciar |
| Región | `us-east-2` (zona `us-east-2a`) |
| Instancia | `portal-proyecto4` (`i-02234c3f51db2446e`), `m7i-flex.large`, Ubuntu Server 24.04 LTS, 30 GiB gp3 cifrado |
| Security group | `portal-proyecto4-sg`: 80 abierto, 22 solo desde la IP de quien administra |
| Llave SSH | Key pair `portal-proyecto4` (ED25519); la `.pem` la guarda Angel |
| Rol de IAM | `portal-proyecto4-ec2` (perfil de instancia del mismo nombre): lee `models/` y escribe en `edge-captures/` del bucket del equipo. IMDSv2 con *hop limit* 2. Ver [Rol de IAM del servidor](#rol-de-iam-del-servidor) |
| Bucket del equipo | `mlops-p4-equipo-452857281704` (`us-east-2`) |
| Commit desplegado | `git rev-parse --short HEAD` en el servidor |

### 1. Tipo de instancia y disco

La cuenta está en el plan gratuito, que solo permite tipos elegibles para la capa
gratuita. Estos son los de `us-east-2` (consultado el 2026-10-06):

| Tipo | vCPU | Memoria | ¿Alcanza para este stack? |
|---|---|---|---|
| **`m7i-flex.large`** | 2 | 8 GiB | **Sí, recomendado.** Corre todos los servicios, incluido el entrenamiento |
| `c7i-flex.large` | 2 | 4 GiB | Solo con los servicios indispensables y swap (ver paso 8) |
| `t3.small`, `t4g.small`, `t8i.small` | 2 | 2 GiB | No: compilar las imágenes y los procesos Python con PyTorch no caben |
| `t3.micro`, `t4g.micro`, `t8i.micro` | 2 | 1 GiB | No |

- **Disco:** 30 GiB `gp3`. Las imágenes de Python con PyTorch, MLflow y Node, más la
  caché de compilación, ocupan varios GB, y los volúmenes de MariaDB y MinIO crecen
  con las imágenes que se suban.
- **Costo:** la instancia consume créditos del plan por cada hora encendida, aunque
  nadie la use. Revisa el saldo en AWS Settings > Billing y apágala al terminar
  (paso 12).

### 2. Lanzar la instancia (consola web)

1. Entra a la consola de AWS y, arriba a la derecha, elige la región
   **US East (Ohio) `us-east-2`**.
2. Ve a **EC2 > Instances > Launch instances**.
3. **Name:** `portal-proyecto4`.
4. **Application and OS Images:** *Ubuntu Server 24.04 LTS (HVM), SSD Volume Type*,
   arquitectura **64-bit (x86)**. Debe decir *Free tier eligible*.
5. **Instance type:** `m7i-flex.large`.
6. **Key pair:** *Create new key pair*. Nombre `portal-proyecto4`, tipo **ED25519**,
   formato **.pem**. El archivo se descarga una sola vez. Guárdalo fuera del repo y no
   lo compartas por chat ni lo subas a git.
7. **Network settings > Edit:**
   - VPC por defecto y cualquier subred; **Auto-assign public IP: Enable**.
   - **Firewall:** *Create security group*, nombre `portal-proyecto4-sg`.
   - Regla 1: **SSH**, TCP 22, *Source type* **My IP**.
   - *Add security group rule*: **HTTP**, TCP 80, *Source type* **Anywhere**
     (`0.0.0.0/0`).
   - No abras 3100, 3306, 5000, 9000 ni 9001: esos servicios no tienen autenticación
     pensada para internet.
8. **Configure storage:** `30` GiB, `gp3`.
9. **Advanced details:** deja *Metadata version* en **V2 only (token required)** y
   pon *Metadata response hop limit* en **2**, para que los contenedores lleguen al
   metadata service. En *IAM instance profile* elige `portal-proyecto4-ec2`; ese
   perfil se creó en AWS-3, ver [Rol de IAM del servidor](#rol-de-iam-del-servidor).
10. **Launch instance.** En el detalle de la instancia, copia la
    **Public IPv4 address**.

Notas:

- *My IP* es la IP de la red desde la que estás. Si cambias de red (casa,
  universidad), SSH dará *timeout*. Edita la regla 22 del security group y vuelve a
  elegir *My IP*. Si otra persona del equipo necesita entrar por SSH, agrega su IP
  como otra regla 22.
- El botón **Connect > EC2 Instance Connect** de la consola no funciona con SSH
  restringido a tu IP. Usa la terminal (paso 3).
- Sin Elastic IP, la IP pública **cambia si detienes e inicias** la instancia. Para
  una URL fija: **EC2 > Elastic IPs > Allocate Elastic IP address**, luego **Actions >
  Associate** con la instancia. La de este servidor ya está asignada (ver
  [Datos del despliegue](#datos-del-despliegue)). Cuesta lo mismo que la IP pública
  normal (0.005 USD/hora), pero **también cobra con la instancia detenida**, así que
  libérala al terminar.

### 3. Conectarse por SSH

macOS / Linux:

```bash
chmod 400 ~/Downloads/portal-proyecto4.pem
ssh -i ~/Downloads/portal-proyecto4.pem ubuntu@<IP-pública>
```

Windows (PowerShell). El `icacls` evita el error *UNPROTECTED PRIVATE KEY FILE*:

```powershell
icacls "$HOME\Downloads\portal-proyecto4.pem" /inheritance:r /grant:r "$($env:USERNAME):R"
ssh -i "$HOME\Downloads\portal-proyecto4.pem" ubuntu@<IP-pública>
```

### 4. Swap, Docker y Docker Compose

Todo esto se ejecuta en el servidor. Primero, 4 GiB de swap como margen para la
compilación de las imágenes:

```bash
sudo fallocate -l 4G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

Docker Engine con los plugins de Compose y Buildx, desde el repositorio oficial de
Docker para Ubuntu. Los Dockerfiles usan `RUN --mount`, que requiere BuildKit/Buildx:

```bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "${UBUNTU_CODENAME:-$VERSION_CODENAME}") stable" \
  | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo usermod -aG docker ubuntu
exit
```

Vuelve a entrar por SSH para que el grupo `docker` aplique, y comprueba:

```bash
docker compose version     # 2.24.4 o más nuevo (docker-compose.aws.yml usa !override)
docker run --rm hello-world
```

### 5. Clonar el repo

El repo es público, así que no hace falta ninguna credencial de GitHub en el
servidor:

```bash
git clone https://github.com/alebonita/Proyecto4-team2.git
cd Proyecto4-team2
```

### 6. Crear el `.env` sin exponer secretos

Las contraseñas se generan **en el servidor** y nunca salen de él. No las imprimas,
no las copies a un chat y no las pongas en este README.

```bash
cp .env.example .env
chmod 600 .env
sed -i "s/^MARIADB_ROOT_PASSWORD=.*/MARIADB_ROOT_PASSWORD=$(openssl rand -hex 32)/" .env
sed -i "s/^MINIO_ROOT_USER=.*/MINIO_ROOT_USER=portal-admin/" .env
sed -i "s/^MINIO_ROOT_PASSWORD=.*/MINIO_ROOT_PASSWORD=$(openssl rand -hex 32)/" .env
# Que todos los `docker compose` del servidor usen también docker-compose.aws.yml:
echo 'COMPOSE_FILE=docker-compose.yml:docker-compose.aws.yml' >> .env
```

Copilot (opcional). `read -s` no muestra la key ni la guarda en el historial:

```bash
read -rsp "ANTHROPIC_API_KEY: " KEY && echo
sed -i "s|^ANTHROPIC_API_KEY=.*|ANTHROPIC_API_KEY=$KEY|" .env && unset KEY
```

Para comprobar qué variables quedaron definidas sin ver sus valores:

```bash
awk -F= '/^[A-Z_]+=/{print $1, ($2=="" ? "(vacía)" : "(definida)")}' .env
```

- **No cambies `MARIADB_ROOT_PASSWORD` después del primer arranque.** MariaDB la
  guarda en su volumen al inicializarse. Si la cambias en `.env`, el backend ya no
  podrá conectarse.
- No pongas credenciales de AWS en `.env`.

Todos los comandos `docker compose` (incluso `ps` y `logs`) exigen `GIT_COMMIT`.
Para que cada sesión SSH lo tenga definido:

```bash
echo 'export GIT_COMMIT="$(git -C ~/Proyecto4-team2 rev-parse HEAD 2>/dev/null)"' >> ~/.bashrc
```

Después de un `git pull` en la misma sesión, vuelve a exportarlo (paso 11).

En Linux, el servicio `app` escribe en `./reports` con el usuario `appuser` del
contenedor, no con `ubuntu`. Sin este permiso, la compuerta de calidad se reinicia
con `PermissionError`. En Docker Desktop (macOS/Windows) no pasa. Git no registra ese
permiso, así que no ensucia el repo:

```bash
chmod -R a+rwX reports
```

### 7. Datos del Proyecto 3 (opcional; antes del primer arranque)

El portal funciona sin estos datos, pero entonces Models, Evaluation, Experiments e
Inference salen vacíos. Los datos están en el remoto DVC `prod`, el bucket del equipo
(ver [Datos del proyecto](#datos-del-proyecto)). El rol del servidor no lee `files/`
a propósito: solo necesita `models/` y `edge-captures/`. Por eso los datos se suben al
servidor desde una máquina que ya los tenga (opciones A y B), o con `dvc pull` en el
servidor usando credenciales temporales tuyas, solo para ese comando (opción C). El
2026-10-06 se usó la opción A:

**Opción A (la que se usó): copia local del caché DVC.** Sirve una copia de la
carpeta del bucket `mlops-p2-dvc-cache` (con `files/md5/...`, unos 700 MB). En tu
máquina, desde la carpeta que contiene esa copia (el `.tar` queda fuera del repo):

```bash
tar cf dvc-cache.tar -C mlops-p2-dvc-cache files
scp -i <ruta-a>/portal-proyecto4.pem dvc-cache.tar ubuntu@<IP-pública>:~/
```

En Git Bash de Windows, usa rutas `/c/...` en lugar de `C:\...`: con `C:` el `tar`
cree que es un servidor remoto.

En el servidor, `dvc pull` lee esa copia como remote local. No toca S3 ni necesita
credenciales, y el remote se agrega solo en `.dvc/config.local`, que está ignorado
por git:

```bash
mkdir -p ~/dvc-cache && tar xf ~/dvc-cache.tar -C ~/dvc-cache && rm ~/dvc-cache.tar
curl -LsSf https://astral.sh/uv/install.sh | sh && source "$HOME/.local/bin/env"
cd ~/Proyecto4-team2
DVC="uvx --from dvc==3.67.1 dvc"
$DVC remote add --local -f localcache /home/ubuntu/dvc-cache
$DVC pull -r localcache data/raw/images.dvc data/raw/annotations.dvc data/models.dvc data/mlflow-snapshot.dvc crops
$DVC status data/raw/images.dvc data/raw/annotations.dvc data/models.dvc data/mlflow-snapshot.dvc crops
$DVC remote remove --local localcache
rm -rf ~/dvc-cache .dvc/cache          # libera ~1.4 GB; los datos ya están en data/
```

Resultado esperado: `data/raw/images` 600 archivos, `data/raw/annotations` 10,
`data/models` 8, `data/mlflow-snapshot` 52 y `data/crops` 668.

**Opción B: datos ya materializados en una laptop** (que hizo `dvc pull`, ver
[Proyecto 3 completo en un clon limpio](#proyecto-3-completo-en-un-clon-limpio-datos-modelo-y-corridas)).
Desde la raíz del repo en la laptop:

```bash
tar czf ../p3-data.tgz data/raw/images data/raw/annotations data/crops data/models data/mlflow-snapshot
scp -i <ruta-a>/portal-proyecto4.pem ../p3-data.tgz ubuntu@<IP-pública>:~/Proyecto4-team2/
# En el servidor:
cd ~/Proyecto4-team2 && tar xzf p3-data.tgz && rm p3-data.tgz
```

**Opción C: `dvc pull` en el servidor con tus credenciales temporales.** Desde tu
máquina, con tu perfil del proyecto. Las credenciales viajan por la entrada de SSH y
no se escriben en el servidor. `tr -d ''` hace falta si lo corres desde Windows:

```bash
{ aws configure export-credentials --profile <tu-perfil> --format env
  echo 'cd ~/Proyecto4-team2 && uvx --from "dvc[s3]==3.67.1" dvc pull'
} | tr -d '' | ssh -i <ruta-a>/portal-proyecto4.pem ubuntu@<IP-pública> 'bash -s'
```

Hazlo **antes** del paso 8. Si Docker arranca primero, crea `data/crops` y
`data/models` vacías y con dueño `root`, y la copia falla con *Permission denied*.
En ese caso, corre `sudo chown -R ubuntu:ubuntu data` y repite la copia.

### 8. Arrancar

```bash
cd ~/Proyecto4-team2
export GIT_COMMIT="$(git rev-parse HEAD)"
docker compose config --quiet      # valida que no falte ninguna variable
docker compose up -d --build
docker compose ps
```

En `m7i-flex.large`, la compilación de todas las imágenes tardó unos 3 minutos y
el arranque con `--wait` unos 5, la primera vez porque descarga MariaDB y MinIO.
Si copiaste los datos del paso 7, carga después las corridas de MLflow. Hazlo solo
en un stack nuevo, porque reemplaza la base `mlflow`. Termina listando los 12 run IDs
con `OK`:

```bash
cd ~/Proyecto4-team2/app      # uv ya quedó instalado en el paso 7
MLFLOW_TRACKING_URI=http://localhost:5000 uv run python -m tracking.snapshot restore
```

Memoria medida con todo el stack arriba (2026-10-06): unos 4.1 de 7.6 GiB. `mlflow`
usa unos 2.3 GiB por sí solo; `ml-api` y `training-worker` en reposo, unos 340 MiB
cada uno; los demás, menos de 120 MiB cada uno.

**Qué servicios son indispensables:**

| Servicio | ¿Indispensable? | Por qué |
|---|---|---|
| `frontend` (nginx) | Sí | Sirve el portal y reenvía `/api`, `/api/ml` y `/copilot-api` |
| `backend` | Sí | API del portal (imágenes, anotaciones, búsqueda) |
| `mariadb` | Sí | Metadatos, anotaciones y cola de jobs |
| `minio` | Sí | Archivos de las imágenes |
| `ml-api` | Sí | nginx espera a que esté *healthy*. Atiende Training, Models e Inference |
| `copilot` | Sí, aunque no tenga key | nginx no arranca si no existe el host `copilot`. Sin `ANTHROPIC_API_KEY` el chat responde 503 |
| `mlflow` | No | Experiments y "Abrir en MLflow". Sin él, `ml-api` responde 503 en esas vistas. Es el que más memoria usa en reposo (~2.3 GiB): el primero a apagar si falta memoria |
| `training-worker` | No | Ejecuta los jobs de entrenamiento. Es el que más memoria usa mientras entrena |
| `app` | No | Compuerta de calidad. Necesita `data/raw` del paso 7: sin esos datos falla 5 veces y se detiene, sin afectar al portal |

Si la memoria no alcanza (por ejemplo en `c7i-flex.large`), levanta solo lo
indispensable. `frontend` arrastra a sus dependencias:

```bash
docker compose up -d --build frontend
docker compose stop training-worker mlflow app   # si ya estaban corriendo
free -h && docker stats --no-stream               # memoria por contenedor
```

### 9. Frontend apuntando a la IP pública

**No hay que cambiar código.** El frontend se compila con `VITE_API_BASE_URL=/api`,
una ruta relativa. El navegador llama a `/api/...` en el mismo host desde el que cargó
la página (`http://<IP-pública>`), y nginx lo reenvía dentro de la red de Docker a
`backend`, `ml-api` y `copilot`. El único cambio es el puerto (8080 → 80), y ya está
en `docker-compose.aws.yml`.

No pongas `VITE_API_BASE_URL=http://<IP>:3100`. Habría que abrir el 3100 a internet
y recompilar cada vez que cambie la IP.

La excepción es el enlace **"Abrir en MLflow"**, que usa `VITE_MLFLOW_UI_URL` (por
defecto `http://localhost:5000`). MLflow no tiene autenticación y no se publica. Para
verlo, abre un túnel SSH desde tu máquina y el enlace funcionará tal cual:

```bash
ssh -i <ruta-a>/portal-proyecto4.pem -L 5000:127.0.0.1:5000 -L 9001:127.0.0.1:9001 ubuntu@<IP-pública>
# Con el túnel abierto: MLflow en http://localhost:5000 y consola de MinIO en http://localhost:9001
```

### 10. Lista de verificación

En el servidor:

- [ ] `docker compose ps`: `mariadb`, `minio`, `backend`, `ml-api`, `copilot` y
      `frontend` en `running`, y `ml-api` en `healthy`.
- [ ] `curl -fsS http://localhost/api/health` responde
      `{"status":"ok","database":"connected",...}`.
- [ ] `curl -fsS http://localhost/api/ml/health` responde 200.
- [ ] `df -h /` por debajo de 80 % y `free -h` con memoria disponible.

Desde tu máquina, idealmente desde otra red (por ejemplo, datos del celular):

- [ ] `http://<IP-pública>` abre el portal.
- [ ] Subir una imagen y verla en el listado. Eso prueba backend, MariaDB y MinIO.
- [ ] Los puertos internos no responden: `curl -m 5 http://<IP-pública>:3100/health`
      y `curl -m 5 http://<IP-pública>:9001` deben terminar en *timeout*.
- [ ] Después de `sudo reboot` (o *Stop*/*Start*), el portal vuelve solo. En la
      prueba, la página cargó a los ~10 s y `/api` dio `502` unos 40 s más, mientras
      arrancaban `backend` y `ml-api`.
- [ ] La tabla [Datos del despliegue](#datos-del-despliegue) está llena.
- [ ] Opcional, con los datos del paso 7, el smoke test del portal:
      `cd app && APP10_PORTAL_URL=http://<IP-pública> uv run pytest tests/test_app10_portal_smoke.py -v`.
      Desde AWS-3 pasa completo: Models confirma la publicación en el bucket del
      equipo con el rol del servidor. Evidencia:
      [aws-3-smoke-test-ec2.md](app/tests/evidence/aws-3-smoke-test-ec2.md).

Resultado de la prueba del 2026-10-06 (todo el stack, con los datos del paso 7):
todos los servicios arriba, `/api/health` y `/api/ml/health` en 200 desde internet,
3100, 3306, 5000, 9000 y 9001 en *timeout* desde fuera, una imagen subida por la IP
pública llegó a MinIO y se borró (204), la compuerta de calidad terminó en
`status=warning` y las 12 corridas de MLflow quedaron restauradas. Ese día el smoke
test falló en el paso 5 (Models: `'unverifiable' == 'published'`), porque el modelo
solo estaba publicado en el S3 de la cuenta anterior y los pasos 6 y 7 no llegaron a
correr. Con AWS-3 (bucket del equipo y rol del servidor) **pasa completo**.

### 11. Actualizar el servidor después de un cambio en el código

```bash
ssh -i <ruta-a>/portal-proyecto4.pem ubuntu@<IP-pública>
cd ~/Proyecto4-team2
git pull
export GIT_COMMIT="$(git rev-parse HEAD)"
docker compose up -d --build          # o con la lista mínima del paso 8: ... --build frontend
docker compose restart frontend        # nginx vuelve a resolver backend/ml-api/copilot
docker compose ps
docker image prune -f                  # libera disco de imágenes viejas
```

- Solo se reconstruyen las imágenes cuyo código cambió. Para un cambio solo de
  frontend: `docker compose up -d --build frontend`.
- Las migraciones nuevas de la base se aplican solas al reiniciar `backend` (ver
  [Producción](#producción)).
- Logs de un servicio: `docker compose logs -f --tail=100 backend`.

### 12. Apagar y limpiar al terminar la entrega

- **Pausa:** EC2 > Instances > *Instance state* > **Stop**. La instancia deja de
  consumir créditos; el disco (unos 0.08 USD/día) y la Elastic IP (unos 0.12 USD/día)
  siguen consumiendo. Al volver a iniciarla, la dirección sigue siendo la misma
  gracias a la Elastic IP.
- **Final:** **Terminate instance**. Eso borra el disco con los datos de MariaDB y
  MinIO, así que respalda antes lo que necesites. Después: **EC2 > Elastic IPs >
  Release** de `eipalloc-06bfd73237d154119`, y borrar el security group
  `portal-proyecto4-sg` y el key pair.
- Revisa el saldo de créditos en AWS Settings > Billing.

### Problemas comunes

| Síntoma | Causa probable | Solución |
|---|---|---|
| SSH da *Connection timed out* | Tu IP cambió | Edita la regla 22 del security group con *My IP* |
| *UNPROTECTED PRIVATE KEY FILE* | Permisos de la `.pem` | `chmod 400` (macOS/Linux) o el `icacls` del paso 3 |
| *UnauthorizedOperation* o *explicit deny* al lanzar | Región equivocada | Usa `us-east-2` |
| No se puede elegir el tipo de instancia | El plan gratuito solo permite tipos elegibles | Usa uno de la tabla del paso 1 |
| Accesos que funcionaban empiezan a dar *Access Denied* | Créditos agotados o límite de gasto | Revisa AWS Settings > Billing |
| El portal no abre | Falta la regla 80, o `frontend` no arrancó | Revisa el security group, `docker compose ps` y `docker compose logs frontend` |
| `502 Bad Gateway` en `/api` | `backend` caído o migrando | `docker compose logs backend` |
| `502` en `/api` o `/api/ml` justo después de actualizar | Se recreó `backend` o `ml-api` con otra IP interna y nginx guarda la anterior (resuelve los nombres al arrancar) | `docker compose restart frontend` |
| Models dice "No verificable" en el servidor | `ml-api` no obtiene credenciales del rol | Comprueba el perfil de instancia `portal-proyecto4-ec2`, el *hop limit* 2 y que `docker compose exec ml-api printenv AWS_EC2_METADATA_DISABLED` diga `false` |
| La compilación muere con *exit code 137* o *Killed* | Falta memoria | Confirma el swap (`free -h`), levanta solo lo indispensable o usa `m7i-flex.large` |
| *unknown tag !override* | Compose anterior a 2.24.4 | `sudo apt-get install --only-upgrade docker-compose-plugin` |
| *Define GIT_COMMIT…*, incluso en `docker compose ps` o `logs` | Falta la variable en esa terminal | `export GIT_COMMIT="$(git rev-parse HEAD)"`, o la línea de `~/.bashrc` del paso 6 |
| `app` se reinicia con `PermissionError: '/app/reports/quality.json'` | `./reports` no es escribible por el usuario del contenedor (solo en Linux) | `chmod -R a+rwX reports` y `docker compose up -d --force-recreate app` |
| `tar: Cannot connect to C: resolve failed` | `tar` de Git Bash con una ruta `C:\...` | Usa `/c/...` |

## Variables de entorno

Se copian de `.env.example`. Ningún valor real se versiona: `.gitignore`
ignora todo `.env*` salvo las plantillas de ejemplo.

| Variable                | Propósito                                      |
|-------------------------|------------------------------------------------|
| `PORT`                  | Puerto HTTP (3000 desarrollo, 3100 producción) |
| `DATABASE_URL`          | Cadena de conexión a MariaDB                   |
| `MINIO_ENDPOINT`        | Host de MinIO                                  |
| `MINIO_PORT`            | Puerto de la API de MinIO                      |
| `MINIO_USE_SSL`         | `true` o `false`                               |
| `MINIO_ACCESS_KEY`      | Credencial de acceso                           |
| `MINIO_SECRET_KEY`      | Credencial secreta                             |
| `MINIO_BUCKET`          | Bucket donde se guardan las imágenes           |
| `MAX_UPLOAD_SIZE_BYTES` | Tamaño máximo por imagen (10 MiB por defecto)   |
| `MLFLOW_TRACKING_URI`   | Servidor MLflow (`http://mlflow:5000` dentro de Compose, `http://localhost:5000` desde el host) |
| `MLFLOW_PORT`           | Puerto del host para la UI de MLflow (opcional, 5000 por defecto) |

Los `.env` son configuración local de Compose/backend/MinIO/Copilot. Las
credenciales AWS se obtienen mediante el perfil SSO `mlops-p2`; nunca las
copies a un `.env`.

## API

| Método | Ruta                        | Descripción                                 |
|--------|-----------------------------|---------------------------------------------|
| GET    | `/health`                   | Estado del servicio y de la base de datos   |
| POST   | `/images`                   | Sube una imagen (`multipart/form-data`)     |
| GET    | `/images/search`            | Búsqueda con filtros y paginación           |
| DELETE | `/images/:id`               | Elimina imagen, binario y anotaciones       |
| GET    | `/images/:id/file`          | Sirve el binario desde MinIO                |
| PATCH  | `/images/:id/status`        | Transiciona el estado de anotación          |
| GET    | `/images/:id/annotations`   | Cajas de una imagen, con su categoría       |
| POST   | `/images/:id/annotations`   | Crea una bounding box                       |
| PATCH  | `/annotations/:id`          | Mueve, redimensiona o reclasifica una caja  |
| DELETE | `/annotations/:id`          | Elimina una caja                            |
| GET    | `/categories`               | Categorías disponibles con su color         |
| GET    | `/dashboard/summary`        | Métricas calculadas en SQL                  |
| GET    | `/export/coco`              | Descarga el dataset en formato COCO         |

### Búsqueda

`GET /images/search` acepta:

| Query param         | Descripción                                                |
|---------------------|------------------------------------------------------------|
| `q`                 | Clases con operadores, ej. `car AND person`, `car OR dog`   |
| `categories`        | Ids de categoría separados por coma                        |
| `status`            | `pending`, `in_progress`, `completed` (separados por coma)  |
| `dateFrom`/`dateTo` | Rango sobre la fecha de subida                             |
| `page`/`pageSize`   | Paginación                                                 |

Los operadores se resuelven con subconsultas `EXISTS` en SQL, nunca filtrando
en memoria. Con `AND` la imagen debe contener todas las clases; con `OR`, al
menos una. Mezclar `AND` con `OR` devuelve `400`, porque la precedencia
sería ambigua.

```bash
curl "http://localhost:3000/images/search?q=car%20AND%20person&status=pending&page=1&pageSize=24"
```

### Exportación COCO

```bash
curl -O -J http://localhost:3000/export/coco
```

```json
{
  "images":      [{ "id", "file_name", "width", "height" }],
  "annotations": [{ "id", "image_id", "category_id",
                    "bbox": [x, y, width, height],
                    "area", "iscrowd", "segmentation" }],
  "categories":  [{ "id", "name" }]
}
```

El `bbox` va en píxeles absolutos, `area` es coherente con `width × height`,
e `iscrowd` siempre está presente. Los `id` son consistentes entre las tres
secciones.

## Calidad

Desde `backend/`:

```bash
npm run typecheck   # TypeScript en modo strict
npm run lint        # Biome: cero errores y cero advertencias
npm test            # Vitest
npm run build       # Compilación a dist/
```

Desde `frontend/`:

```bash
npm run typecheck
npm run lint        # Biome: cero errores y cero advertencias
npm run build
```

## Especificaciones y pruebas

Cada regla crítica está trazada de la especificación al escenario Gherkin y
de ahí a la prueba automatizada.

| SPEC            | Regla                                   | Implementación               |
|-----------------|-----------------------------------------|------------------------------|
| SPEC-UPLOAD-001 | Tipo y tamaño de la imagen subida       | `image-upload.validation.ts` |
| SPEC-ANNOT-001  | Geometría y categoría de las cajas      | `annotation.validation.ts`   |
| SPEC-COCO-001   | Estructura y consistencia del JSON COCO | `coco-export.builder.ts`     |
| SPEC-SEARCH-001 | Operadores `AND` / `OR` de búsqueda     | `search-query.parser.ts`     |
| SPEC-VALID-001  | Validación de la frontera HTTP con Zod  | `annotation.validation.ts`   |
| SPEC-DASH-001   | Métricas del dashboard desde SQL        | `dashboard.builder.ts`       |

```text
backend/specs/<nombre>.spec.md
        ↓
backend/features/<nombre>.feature    (Given / When / Then)
        ↓
backend/tests/<nombre>.test.ts       (Vitest)
        ↓
backend/src/logic/<nombre>.ts        (implementación)
```

Las pruebas están diseñadas para fallar si la lógica se rompe: invertir
`width` y `height` en la exportación COCO, permitir un `categoryId` no
positivo o dejar de validar `imageId` hace fallar la suite.

## Fuera de alcance

El entrenamiento del modelo y MLOps corresponden a una fase posterior.

## Etapas del proyecto

El proyecto se construyó por etapas, cada una sobre la anterior:

| Etapa | Qué aportó                                                                 |
|-------|----------------------------------------------------------------------------|
| 1     | Esqueleto: TypeScript, Biome, arquitectura UI/Logic/Data, esquema Drizzle. |
| 2     | Persistencia: MariaDB, MinIO, migraciones, upload de imágenes, seeder.     |
| 3     | Frontend React: portal de anotación, canvas, dashboard y búsqueda.         |
| 4     | Integración final: lógica de negocio, COCO, dashboard y validación Zod.    |

### Qué agrega la etapa final (integración)

Esta etapa conecta el frontend con el backend y completa lo que faltaba para
que el portal funcione de punta a punta:

- **Exportación COCO** (`GET /export/coco`): documento JSON descargable con
  `images`, `annotations` y `categories`, con ids consistentes entre
  secciones (SPEC-COCO-001).
- **Métricas del dashboard** (`GET /dashboard/summary`): totales, objetos por
  clase y progreso de anotación, todo calculado en SQL (SPEC-DASH-001).
- **Búsqueda por clases con operadores** en `GET /images/search`: `AND` / `OR`
  resueltos con subconsultas `EXISTS` en SQL, más filtros por categoría,
  estado y rango de fechas (SPEC-SEARCH-001).
- **Validación de la frontera HTTP con Zod**: todo body, query param y route
  param se valida antes de llegar a la base de datos, con errores tipados que
  la UI mapea a códigos HTTP (SPEC-VALID-001).
- **Reglas de anotación**: la caja debe caber dentro de la imagen, el área la
  calcula el backend, y una imagen sin cajas no puede quedar como completada
  (SPEC-ANNOT-001).

### Notas de puesta en marcha

- Usa `npm install` la primera vez en cada paquete (`backend/` y `frontend/`).
  `node_modules` no se versiona: se reconstruye desde `package-lock.json`.
- El backend valida sus variables de entorno al arrancar (fail-fast con Zod).
  Si falta `backend/.env` o alguna variable, el proceso termina indicando
  cuáles faltan; usa el bloque de variables de backend documentado arriba.
- Si publicaste MariaDB en un puerto distinto al 3306 (por ejemplo 3307
  porque el 3306 ya estaba ocupado), ajusta `DATABASE_URL` en `backend/.env`
  para que coincida.
- El frontend habla con el backend a través del proxy `/api` de Vite en
  desarrollo. `VITE_API_BASE_URL` puede dejarse en `/api`; en producción se
  apunta a la URL real del backend.

## P2-04 — MinIO local y remotes DVC

Esta sección contiene los detalles del remote DVC opcional de desarrollo. Para
el onboarding completo, empieza por [Onboarding de desarrollo](#onboarding-de-desarrollo).

> **Desde AWS-3**, `prod` apunta al bucket del equipo
> (`mlops-p4-equipo-452857281704`, `us-east-2`) y el bucket original de esta sección
> se conserva como el remoto `p2-origen`. Ver [Datos del proyecto](#datos-del-proyecto).
No necesitas MinIO para leer el dataset compartido de producción.

- `dev` usa `s3://dvc-cache` con endpoint `http://localhost:9000` (MinIO local).
- `prod` usa `mlops-p2-dvc-cache-280764207006` en AWS S3.
- `mlops-p2-dataset-releases-280764207006` se reserva para releases finales del dataset; no es un remote DVC.

### Resumen rápido

- `dev` → MinIO local, bucket `dvc-cache`.
- `prod` → AWS S3, bucket `mlops-p2-dvc-cache-280764207006`.
- `mlops-p2-dataset-releases-280764207006` → releases finales del dataset.
- Git versiona la configuración y los archivos `.dvc`; los binarios se guardan en los remotes.
- Las credenciales de MinIO son locales de cada integrante; no son credenciales
  de AWS ni se usan para `prod`.
- Cada integrante necesita su propio acceso SSO a AWS para `prod`.
- No se comparten contraseñas, sesiones SSO, access keys, secret keys ni tokens.

### Flujo opcional: preparar MinIO local

Solo realiza estos pasos si necesitas usar el remote `dev`. Desde la raíz del
proyecto, crea tu archivo `.env` local a partir de la plantilla:

```bash
test -e .env || cp .env.example .env
chmod 600 .env
```

Completa:

```text
MINIO_ROOT_USER=
MINIO_ROOT_PASSWORD=
```

con valores locales propios.

Puedes generar una contraseña con:

```bash
openssl rand -hex 32
```

No uses claves AWS en `.env`. La autenticación de AWS se configura con IAM
Identity Center / SSO y el perfil local `mlops-p2`.

`frontend/.env.example` es independiente y no cambia para este ticket.

Levanta MinIO:

```bash
docker compose up -d --no-deps minio
```

### Instalar DVC

Instala DVC con soporte S3 en un entorno Python separado del entorno de `app/`:

```bash
python3.12 -m venv .venv-dvc
. .venv-dvc/bin/activate
python -m pip install 'dvc[s3]==3.67.1'
python --version
dvc --version
dvc remote list
```

El repositorio ya contiene la inicialización de DVC y la configuración de los
remotes. **No ejecutes `dvc init`.**

### Configurar `dev` con MinIO local

Carga las variables de tu `.env`:

```bash
set -a
. ./.env
set +a
```

Configura las credenciales de MinIO únicamente de forma local y solo para
`dev`:

```bash
dvc remote modify --local dev access_key_id "$MINIO_ROOT_USER"
dvc remote modify --local dev secret_access_key "$MINIO_ROOT_PASSWORD"
chmod 600 .dvc/config.local
```

No omitas `--local`: `.dvc/config.local` es local, está ignorado por Git y no
debe subirse al repositorio. No mezcles estas credenciales con el perfil SSO
de AWS usado por `prod`.

No agregues `.env` ni `.dvc/config.local` a Git.

### Crear el bucket local `dvc-cache`

Si el bucket `dvc-cache` todavía no existe en MinIO, créalo con:

```bash
python - <<'PY'
import os
from botocore.session import get_session
from botocore.exceptions import ClientError

client = get_session().create_client(
    's3',
    endpoint_url='http://localhost:9000',
    region_name='us-east-1',
    aws_access_key_id=os.environ['MINIO_ROOT_USER'],
    aws_secret_access_key=os.environ['MINIO_ROOT_PASSWORD'],
)

try:
    client.head_bucket(Bucket='dvc-cache')
except ClientError as error:
    if error.response['ResponseMetadata']['HTTPStatusCode'] != 404:
        raise
    client.create_bucket(Bucket='dvc-cache')

print('Bucket local dvc-cache disponible')
PY
```

Este paso solo opera contra MinIO local en `localhost:9000`.

No modifica el bucket `image-annotations` usado por el portal.

### Verificar los remotes

Ejecuta:

```bash
dvc remote list -v
```

La salida debe incluir:

```text
dev     s3://dvc-cache
prod    s3://mlops-p2-dvc-cache-280764207006
```

### Subir y bajar archivos con `dev`

Primero registra el archivo o directorio con DVC:

```bash
dvc add ruta/al/dataset
```

Para subirlo a MinIO:

```bash
dvc push -r dev
```

Para recuperarlo:

```bash
dvc pull -r dev
```

Los archivos `.dvc` generados se comparten mediante Git.

Los binarios se guardan en MinIO, no directamente en GitHub.

### AWS S3 y remote `prod`

La configuración completa de AWS CLI, IAM Identity Center / SSO, el perfil
`mlops-p2`, las comprobaciones de lectura y la conexión local de DVC está en
[Onboarding de desarrollo](#onboarding-de-desarrollo). `prod` usa AWS S3 real,
sin endpoint personalizado, en `us-east-1`:

| Bucket | Uso |
|---|---|
| `mlops-p2-dvc-cache-280764207006` | Remote DVC `prod`. |
| `mlops-p2-dataset-releases-280764207006` | Releases finales del dataset. |

Para lectura del remote DVC, el permission set debe tener permisos
conceptualmente equivalentes a `s3:ListBucket` y `s3:GetObject`. Si además
publicas datasets, el administrador debe asignarte permisos de escritura. No
uses `dvc push` como prueba de conexión.

### Flujo recomendado para el equipo

1. Hacer `git pull` para obtener los metadatos `.dvc` más recientes.
2. Activar el entorno de DVC.
3. Iniciar sesión con AWS SSO si se va a usar `prod`.
4. Ejecutar `dvc status -r prod data/raw/images.dvc data/raw/annotations.dvc`
   para consultar el estado sin subir datos.
5. Ejecutar `dvc pull -r prod data/raw/images.dvc data/raw/annotations.dvc`
   solo si necesitas materializar el dataset localmente.
6. Si eres una persona mantenedora autorizada, agregar o actualizar datos,
   ejecutar `dvc add <ruta>` y publicar con `dvc push -r prod` como una
   operación explícita, no como prueba de conexión.
7. Versionar con Git los archivos `.dvc` y los cambios de código
   correspondientes.

No subas los binarios grandes directamente al repositorio de GitHub.

### Seguridad y validación

Los siguientes archivos o datos no deben versionarse:

- `.env`
- `.dvc/config.local`
- credenciales AWS, incluidas access keys y secret keys
- sesiones y tokens SSO
- credenciales reales de MinIO

Cada persona debe usar su propia identidad AWS. No compartas passwords,
sesiones SSO, access keys ni tokens, y no pongas credenciales AWS en ningún
`.env`.

Comprueba que los archivos privados estén ignorados:

```bash
git check-ignore .env .dvc/config.local
```

La salida debe incluir:

```text
.env
.dvc/config.local
```

Comprueba que `.env.example` sí pueda versionarse:

```bash
git check-ignore .env.example
```

Ese comando no debe mostrar salida.

Comprueba que no existan access keys AWS con prefijo `AKIA` en el historial:

```bash
git log --all -p -S 'AKIA'
```

La salida debe estar vacía.

P2-04 externaliza las credenciales MinIO usadas por Docker Compose y evita agregar secretos AWS al repositorio.

No se reescribe el historial de Git ni se modifica la configuración heredada de MariaDB.

### Criterios de aceptación

Antes de cerrar P2-04, verificar:

- `docker compose up -d --no-deps minio` levanta MinIO.
- `.env.example` existe y no contiene credenciales reales.
- `dvc remote list -v` muestra `dev` y `prod`.
- `dvc push -r dev` funciona para una persona autorizada que use MinIO local.
- `aws s3api head-bucket`, `aws s3api list-objects-v2` y `dvc status -r prod`
  funcionan con el perfil SSO autorizado; `dvc pull` se usa solo cuando se
  necesita materializar el dataset.
- `dvc push -r prod` se prueba únicamente con autorización explícita de
  escritura; no es una prueba de conectividad.
- `git log --all -p -S 'AKIA'` no devuelve resultados.
- `.env` y `.dvc/config.local` permanecen fuera de Git.
- Los buckets `mlops-p2-dvc-cache-280764207006` y `mlops-p2-dataset-releases-280764207006` existen en AWS.

## P2-42 — Pipeline DVC completo (`dvc.yaml`)

Hasta este ticket, el dataset se manejaba con `dvc add` suelto: reproducible
como almacenamiento de archivos, pero sin un pipeline declarado con
dependencias/salidas. `dvc.yaml` separa el cálculo del reporte (`quality_report`)
de la decisión de la compuerta (`quality_gate`) y agrega `split` como etapa
posterior. Un reporte `failed` hace que DVC termine con código distinto de cero
y evita ejecutar las etapas dependientes.

```bash
dvc repro
```

- **`app/dvc_quality_report_stage.py`** calcula `reports/quality.json` sin
  decidir si el dataset puede avanzar. **`app/dvc_gate_stage.py`** lee ese
  reporte y devuelve `exit 1` cuando `status: failed`; solo en caso aprobado
  escribe `reports/.quality_gate.passed`, que es la dependencia explícita de
  `split`.
- **`reports/quality.json` es un `metrics`, no un `outs`**, con
  `cache: false`: es un reporte chico y legible, pensado para diffs de PR y
  `dvc metrics diff`, no un artefacto binario que amerite el object store
  de DVC.
- El pipeline no usa `always_changed`: una segunda ejecución de `dvc repro`
  puede reutilizar el run-cache y no rehacer etapas cuando sus entradas no
  cambiaron.
- Los remotes `dev`/`prod` de P2-04 ya existían; lo que faltaba en un
  checkout nuevo era el paso local `dvc remote modify --local dev
  access_key_id/secret_access_key` (con `$MINIO_ROOT_USER`/
  `$MINIO_ROOT_PASSWORD`) y crear el bucket `dvc-cache` si no existía —
  ambos ya documentados arriba en P2-04, solo faltaba ejecutarlos en este
  checkout.

### Criterios de aceptación

- `dvc.yaml` define `quality_report`, `quality_gate` y `split` con dependencias
  y salidas reales; un `failed` bloquea el downstream.
- `dvc.lock` y `dvc.yaml` versionados en Git; los datos siguen fuera de Git.
- `dvc repro` regenera `reports/quality.json`; si el reporte queda `failed`,
  termina con código distinto de cero y no ejecuta `split`.
- `dvc push`/`dvc pull` funcionan contra `dev` y `prod` (verificado: 612
  archivos sincronizados en `dev`, `prod` ya en uso durante todo el proyecto).

## P2-45 — Versionado semántico y diff entre releases

Depende de P2-42. Un release congela `dataset_version` (formato
`vMAJOR.MINOR.PATCH`) junto con su `quality.json` y `splits.json` bajo
`reports/releases/<version>/`, y agrega la entrada al catálogo
`reports/versions.json` (`VersionsReport`, contrato v1.0 de P2-12).

```bash
# Desde app/, con las mismas variables placeholder que P2-42 (ver dvc_gate_stage.py):
uv run python -m presentation.release cut v0.1.0
uv run python -m presentation.release diff v0.1.0 v0.2.0
```

- **Content hash DEV/PROD**: el hash del dataset ya es el md5 en
  `data/raw/annotations.dvc`/`data/raw/images.dvc` — el mismo valor sin
  importar el remote, por construcción de DVC. Verificar que ambos
  remotes lo tengan de verdad es `dvc status -r dev` y `dvc status -r
  prod`, ambos reportando "Cache and remote 'X' are in sync." — no hace
  falta recalcular nada; reimplementarlo sería redundante con lo que DVC
  ya garantiza.
- **`splits.json` nunca se había escrito a disco**: P2-32 dejó
  `split_dataset()`/`build_splits_report()` puros a propósito (ver
  `app/splits/README.md`, "antes de persistir artefactos hay que acordar
  su ubicación/ignore o seguimiento DVC"), porque `DatasetRelease` exige
  `quality_file` y `splits_file`, este ticket fue quien tuvo que decidirlo:
  `reports/releases/<version>/splits.json`, escrito por `cut_release()`.
- **El release respeta la compuerta**: el catálogo histórico `v0.1.0` puede
  conservar un reporte `failed`, pero `cut_release()` rechaza cualquier nuevo
  corte cuyo reporte esté en `status: failed`.
- **Un release es inmutable**: `cut_release()` rechaza un `version` que ya
  existe en el catálogo en vez de sobreescribirlo.
- **`diff_releases()` no vuelve a correr el gate**: lee los dos
  `quality.json` ya congelados — un diff no debe poder ver un dataset
  distinto al que el release realmente describió en su momento.

### Criterios de aceptación

- `dvc status -r dev` y `dvc status -r prod` reportan "in sync" (content
  hash idéntico, verificado).
- `reports/versions.json` sigue el contrato `VersionsReport` v1.0 y usa
  versionado semántico (`v0.1.0` histórico y `v0.1.1` válido, ver
  `reports/releases/`).
- `presentation.release diff <a> <b>` genera un diff real entre dos
  releases (conteo por categoría y status de cada check).

## Frente 1 — Arquitectura y entorno del pipeline de calidad

El portal de anotación (arriba) ya no es el entregable de la Fase 2: es la
fuente del COCO crudo. El entregable es un pipeline en Python que mide la
calidad de ese COCO, decide si se libera y versiona el resultado con DVC.

Este frente deja listo el esqueleto; la lógica de cada tier la completan los
frentes 2 a 6.

### Capas (`app/`)

El pipeline vive en `app/`, como paquete Python independiente (hermano de
`backend/` y `frontend/`), con una carpeta por capa:

```text
app/
  ingestion/      Tier 1 — COCO crudo del Proyecto 1
  analyzers/      Tier 2 — 5 analizadores de calidad (objetos pequeños,
                  desbalance, duplicados, cajas inválidas, sesgo espacial)
  policies/       Tier 3 — compuerta de calidad (policies/quality.yaml)
  splits/         Tier 4 — split estratificado train/val/test
  storage/        Tier 5 — MariaDB y MinIO/S3 (DVC)
  presentation/   Expone los resultados a la app web y al Dataset Copilot
```

**Regla de la compuerta de acoplamiento:** solo `storage/` importa `os`
(para leer variables de entorno), crea clientes `boto3`/`Minio(` o abre un
`create_engine`/`pymysql.connect`. Todas las demás capas son funciones puras
que reciben los datos ya cargados como argumento — así se pueden probar con
`pytest` sin levantar MariaDB/MinIO reales. Se verifica con:

```bash
grep -rn "os\.environ\|os\.getenv\|boto3\.client\|Minio(\|create_engine\|pymysql\.connect" app/analyzers/
```

(sin resultados) y con `app/tests/test_architecture.py`, que corre lo mismo
en CI.

### Levantar todo

```bash
docker compose up
```

Además de `mariadb`, `minio`, `backend` y `frontend` (portal P1, se mantiene
porque la cola de re-anotación —cuando la compuerta bloquea el release—
ocurre ahí), se agrega el servicio `app`: el pipeline Python, que reutiliza
el mismo MariaDB y el mismo MinIO del portal (mismas credenciales de
`.env`, sin variables nuevas). Al arrancar, `app` valida que puede
conectarse a ambos, ejecuta el quality gate y puede regenerar
`reports/quality.json`. Un estado `failed` queda registrado en los logs y debe
revisarse antes de promover o publicar el dataset; levantar `app` no sustituye
la compuerta de DVC.

El servicio `copilot` (P2-52) usa la misma imagen que `app` y atiende el chat
de la pantalla Copilot a través de nginx (`/copilot-api/`), sin publicar
puertos. Necesita `ANTHROPIC_API_KEY` en `.env` (opcional: sin ella todo
arranca y el chat explica qué falta). Detalles en `app/copilot/README.md`.

### Python y lockfile

`app/pyproject.toml` fija `requires-python = "==3.12.*"` y `app/Dockerfile`
usa `python:3.12-slim` — misma versión en ambos lados. Las dependencias
quedan resueltas y pineadas en `app/uv.lock` (generado con `uv lock`, no a
mano); el `Dockerfile` instala desde ese lockfile con
`uv sync --locked`, así que build local y build en CI siempre resuelven
exactamente las mismas versiones.

Para trabajar en `app/` localmente con [uv](https://docs.astral.sh/uv/):

```bash
cd app
uv sync            # crea .venv con dependencias + grupo dev (ruff, pytest)
uv run pytest -q
uv run ruff check .
```

### Supuestos de este frente pendientes de confirmar con Karen/Heri

Lo siguiente se infirió a partir del diagrama de tiers y los mockups del
profe, y del trabajo ya mergeado de DVC (P2-04); si Karen decide otra cosa,
son fáciles de mover porque todo el pipeline está aislado en `app/`:

- El portal Node (`backend`/`frontend`) se queda corriendo junto al pipeline
  en el mismo `docker-compose.yml`, en vez de retirarse porque "el portal ya
  no es el entregable".
- El pipeline reutiliza el MariaDB/MinIO del portal (misma base
  `image_repo`, mismo bucket `image-annotations`) en vez de tener su propia
  infraestructura de datos en dev.
- Quién es responsable del frente 4 (compuerta) no estaba claro en el
  reparto compartido — confirmar con Karen.

## P2-36 — Settings persistente

`/pipeline/settings` tiene dos formularios independientes. La API Node
existente ofrece `GET /settings`, `PUT /settings/quality` y
`PUT /settings/splits` (desde el navegador, `/api/settings/...`).

- Quality permite editar threshold/action de los siete checks reales y
  width_px/height_px de objetos pequeños. La similitud pHash es un umbral de
  detección; el cumplimiento sigue exigiendo cero pares.
- Splits permite editar train/val/test (fracciones estrictamente entre 0 y 1,
  suma 1 con tolerancia 1e-6) y seed (entero seguro de JavaScript).
- `cross_split_leakage` se preserva sin exponerlo. No se publican credenciales,
  rutas, variables de infraestructura ni una supuesta versión activa.
- GET devuelve `{quality, splits}`. Cada PUT recibe directamente su sección
  completa y devuelve esa sección validada. Campos desconocidos o valores
  inválidos producen 400; los errores internos producen 500.
- Persisten en `app/policies/quality.yaml` y `app/splits/splits.yaml`. Se
  conservan comentarios y campos no editables; el backend escribe un temporal,
  sincroniza/cierra y renombra en el mismo directorio. Serializa escrituras
  dentro de su proceso. No hay transacción entre ambos archivos ni control de
  edición obsoleta: la última escritura válida gana.

Guardar **no ejecuta el pipeline**, no crea releases y no cambia reportes
existentes. Los valores afectan la siguiente ejecución de quality/release.
El contenedor Python ejecuta el gate al arrancar, no observa archivos para
recalcular automáticamente. Los comandos de pipeline/release existentes
siguen siendo operaciones explícitas.

Compose comparte los directorios de políticas y splits: backend RW bajo
`/pipeline`, Python RO bajo `/app`. No se publican mediante Nginx. Se montan
directorios para que los reemplazos atómicos sean visibles. En desarrollo,
el backend resuelve el directorio `app/` hermano; `PIPELINE_CONFIG_ROOT` es
una opción de despliegue confiable, nunca un parámetro HTTP.

Python carga la política YAML al construir Settings. `QUALITY` del entorno
o de `.env` se ignora, incluso si contiene JSON inválido: no puede sustituir
silenciosamente la política gestionada por UI. El resto de variables de
infraestructura conserva su semántica. Una política inyectada explícitamente
por código sigue siendo válida para tests/operaciones explícitas.
Cada release recibe una política para quality y pHash, y una SplitsConfig
cargada una vez; ya no recarga otra política para agrupar duplicados.

Estos YAML siguen siendo configuración versionada en Git; guardar puede
dejar cambios locales que deben revisarse. DVC observa `policies/` y
`splits/splits.yaml` desde `quality_report`/`split`. Desde P2-53, quality_gate
también registra ratios y seed de splits. Cambiarlos
afecta la próxima evaluación de leakage y el próximo corte de release,
sin reescribir los splits congelados.

Se añadió `yaml` como dependencia directa del backend para leer/escribir
YAML sin un parser artesanal. El backend actual no tiene autenticación ni
autorización: esta edición está destinada al despliegue controlado existente,
no constituye un panel administrativo protegido para exposición pública.

## OPS-03 — MLflow persistente

El servicio `mlflow` de `docker-compose.yml` es el Tracking Server del Proyecto 3
(imagen en [`mlflow-server/`](mlflow-server/README.md), MLflow 3.16.1 con versiones
fijas). No guarda estado en su contenedor:

| Qué | Dónde | Volumen |
|-----|-------|---------|
| Experimentos, runs, parámetros, métricas por época, tags | Base `mlflow` en MariaDB | `mariadb_data` |
| Artefactos (checkpoints, curvas) | Bucket `mlflow` en MinIO | `minio_data` |

Por eso los runs sobreviven a `docker compose restart`, a `docker compose down`
(sin `-v`) y a recrear los contenedores. La base y el bucket se crean solos al
arrancar, también sobre volúmenes que ya existían.

### Conectarse (worker, entrenamiento, scripts)

La única configuración del cliente es `MLFLOW_TRACKING_URI`:

- Dentro de Compose (`app`, `copilot` y el futuro worker la reciben de
  `x-pipeline-env`): `http://mlflow:5000`.
- Desde el host: `http://localhost:5000`.

Los artefactos se suben y se descargan **a través del servidor**
(`mlflow-artifacts:`), así que los clientes no necesitan credenciales de MinIO.
En Python, usa el cliente del proyecto, que lee la URI con `TrackingSettings` y
fuerza ese modo:

```python
from tracking.client import tracking_client

client = tracking_client()  # también configura mlflow.set_tracking_uri(...)
```

Para comprobar la conexión desde un contenedor:

```bash
docker compose run --rm app python -m tracking.check
```

La UI está en http://localhost:5000 y solo escucha en loopback porque no tiene
autenticación. MLflow 3 rechaza (403) cualquier `Host` que no esté en
`MLFLOW_ALLOWED_HOSTS`; la lista ya incluye `mlflow` y `localhost`.

### Verificar la persistencia

`app/tests/test_mlflow_persistence.py` crea un run con parámetros, métricas por
época, un checkpoint y una curva; recrea los contenedores de MariaDB, MinIO y
MLflow, y recupera el mismo `run_id` por API comparando todo (hash del checkpoint
incluido). Se omite por defecto; para correrla con el stack levantado:

```bash
docker compose up -d --build --wait mariadb minio mlflow
cd app
MLFLOW_INTEGRATION=1 MLFLOW_TRACKING_URI=http://localhost:5000   uv run pytest -v tests/test_mlflow_persistence.py
```

En CI la corre el job **MLflow persistente (OPS-03)**.

### Restaurar las corridas de ML-07 en un clon limpio

MLflow guarda los runs en los volúmenes Docker de cada máquina, así que un clon
nuevo arranca con MLflow vacío. Las 12 corridas de la matriz de ML-07 (#26) están
versionadas como snapshot DVC en `data/mlflow-snapshot` (volcado de la base
`mlflow` + checkpoints y curvas, con sha256). Para cargarlas con **los mismos
run IDs** que lista `reports/experiments/ml07_runs.json`, desde la raíz:

```bash
docker compose up -d --wait mlflow
dvc pull -r prod data/mlflow-snapshot.dvc
cd app
MLFLOW_TRACKING_URI=http://localhost:5000 uv run python -m tracking.snapshot restore
MLFLOW_TRACKING_URI=http://localhost:5000 uv run python -m classification.experiments report \
  --matrix classification/ml07_matrix.yaml
```

`restore` carga el volcado en MariaDB (reemplaza la base `mlflow` local),
reinicia MLflow, sube los artefactos a los mismos runs por la API y verifica
tamaño y sha256 de cada uno. `report` comprueba por la API los criterios de ML-07
y termina con código ≠ 0 si alguno falla. Detalle:
[`app/classification/README.md`](app/classification/README.md#ml-07--matriz-de-experimentos-y-10-corridas-en-mlflow).

## APP-03 — Jobs de entrenamiento

La pantalla **Training** (`/ml/training`) crea jobs con `POST /api/ml/training/jobs`.
nginx manda `/api/ml/` al servicio `ml-api` (Python, `app/training/server.py`), que
valida el request y las reglas del release (Quality Gate, `provenance.json`,
`manifest.json` y `manifest_hash`) y **solo encola** el job en MariaDB. El
entrenamiento lo corre el worker de OPS-04 en otro proceso, nunca dentro del
request HTTP.

Como el estado vive en MariaDB, refrescar la página o reiniciar los contenedores
(`docker compose down` sin `-v`) no pierde los jobs, su progreso, sus logs ni sus
errores. Mientras haya jobs `queued` o `running`, la pantalla se actualiza cada 3 s.
"Ver logs" deja el job en la URL (`?job=<id>`).

Detalle de la API, de la cola y de la interfaz para el worker en
[`app/training/README.md`](app/training/README.md).

 -> MariaDB queue -> training-worker -> run_training() -> MLflow

## APP-04 — Experiments

La pantalla **Experiments** (`/ml/experiments`) muestra los runs de entrenamiento
reales de MLflow, leídos por `ml-api` en cada consulta (`GET /api/ml/runs`):
`run_id`, estado, release DVC, `manifest_hash`, commit, los 7 hiperparámetros y
una columna ordenable por cada métrica de validación. Se puede buscar, filtrar
por estado y dataset, y abrir el mismo run en la UI de MLflow
(`VITE_MLFLOW_UI_URL`, por defecto `http://localhost:5000`).

Marcando hasta 3 runs se comparan sus parámetros y métricas ("Distinto" en lo que
cambia) y sus curvas reales de train/validation (`GET /api/ml/runs/{id}/curves`),
cada una con su tabla "Ver datos". La comparación queda en la URL (`?runs=`).
Mientras haya runs en curso, la pantalla se actualiza cada 5 s.

Lo que cada run debe registrar en MLflow para aparecer aquí está en
[`app/training/README.md`](app/training/README.md#qué-debe-registrar-cada-run-de-entrenamiento-ml-04--ops-04).
