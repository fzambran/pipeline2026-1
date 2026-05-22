# Titanic Data Pipeline

Pipeline de datos reproducible que limpia, valida y carga el dataset del Titanic en PostgreSQL. Todos los servicios de infraestructura corren en contenedores Docker.

---

## Dataset

**Archivo:** `data/raw/train_and_test2.csv` — 1 309 registros del Titanic con las columnas originales codificadas:

| Columna original | Descripción | Codificación raw |
|---|---|---|
| `Passengerid` | ID único del pasajero | entero |
| `Age` | Edad en años | decimal |
| `Fare` | Precio del billete | decimal |
| `Sex` | Género | 0 = male, 1 = female |
| `sibsp` | Hermanos/cónyuge a bordo | entero |
| `Parch` | Padres/hijos a bordo | entero |
| `Pclass` | Clase del pasajero | 1, 2, 3 |
| `Embarked` | Puerto de embarque | 0=S, 1=C, 2=Q, vacío=desconocido |
| `2urvived` | Sobrevivió | 0 = no, 1 = sí |
| `zero` × 19 | Columnas de relleno (todo ceros) | se eliminan |

---

## Arquitectura del pipeline

```
data/raw/
  └── train_and_test2.csv
        │
        ▼  src/clean.py  (Stage 1)
data/processed/
  └── titanic_clean.csv
        │
        ▼  src/validate.py  (Stage 2)
data/validated/
  ├── titanic_validated.csv
  └── titanic_rejected.csv
data/reports/
  └── validation_report.txt
        │
        ▼  src/load.py  (Stage 3)
PostgreSQL  (contenedor Docker)
data/validated/
  ├── titanic_inserted.csv
  └── titanic_db_rejected.csv
logs/
  └── load.log
```

### Infraestructura Docker

```
pipeline_net (bridge)
  ├── postgres   — PostgreSQL 16-alpine, puerto 5432
  ├── pgadmin    — pgAdmin 4, puerto 8080
  └── pipeline   — contenedor Python que ejecuta main.py
```

---

## Requisitos previos

### Opción A — Ejecución local (sin Docker para el pipeline)
- Python 3.13+ y [uv](https://docs.astral.sh/uv/)
- Docker y Docker Compose (para postgres + pgadmin)

### Opción B — Ejecución 100% en contenedores
- Docker y Docker Compose únicamente

---

## Puesta en marcha

### 1. Clonar y configurar variables de entorno

```bash
git clone <repo-url>
cd pipeline
cp .env .env.local  # ajustar credenciales si se desea
```

El archivo `.env` incluido tiene valores por defecto para desarrollo local:

```
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=titanic
POSTGRES_USER=pipeline
POSTGRES_PASSWORD=pipeline123
PGADMIN_DEFAULT_EMAIL=admin@pipeline.local
PGADMIN_DEFAULT_PASSWORD=admin123
```

### 2. Levantar la infraestructura de base de datos

```bash
docker compose up postgres pgadmin -d
```

Esperar a que postgres esté listo (el healthcheck lo indica):

```bash
docker compose ps          # postgres debe mostrar "healthy"
```

### 3. Opción A — Ejecutar el pipeline localmente

```bash
uv sync                    # instala dependencias
uv run python main.py      # ejecuta las 3 etapas
```

Ejecutar una sola etapa:

```bash
uv run python main.py --stage clean
uv run python main.py --stage validate
uv run python main.py --stage load
```

### 4. Opción B — Ejecutar el pipeline en contenedor

```bash
# Levanta todo: postgres, pgadmin y el pipeline
docker compose up --build

# O sólo el pipeline (asumiendo postgres ya está arriba)
docker compose run --rm pipeline
```

El contenedor `pipeline` monta `./data` y `./logs` como volúmenes, por lo que los archivos de salida quedan en el host.

---

## Etapas del pipeline

### Stage 1 — Limpieza (`src/clean.py`)

| Transformación | Detalle |
|---|---|
| Eliminar columnas `zero*` | 19 columnas de relleno (todo ceros) |
| Renombrar columnas | `2urvived` → `survived`, `Passengerid` → `passenger_id`, etc. |
| Decodificar `sex` | `0 → 'male'`, `1 → 'female'` |
| Decodificar `embarked` | `0 → 'S'`, `1 → 'C'`, `2 → 'Q'` |
| Eliminar duplicados | Por `passenger_id` |
| Imputar nulos — `age` | Mediana del dataset |
| Imputar nulos — `embarked` | Moda del dataset |
| Eliminar fuera de rango | `age ∈ [0,120]`, `fare ≥ 0`, `pclass ∈ {1,2,3}`, `survived ∈ {0,1}` |
| Columnas derivadas | Ver tabla siguiente |

**Columnas derivadas creadas:**

| Columna | Fórmula | Descripción |
|---|---|---|
| `family_size` | `sibsp + parch + 1` | Tamaño total del grupo familiar |
| `is_alone` | `family_size == 1` | 1 si viajaba solo |
| `fare_per_person` | `fare / family_size` | Tarifa por persona del grupo |
| `age_group` | rangos de edad | `child` (<12), `teenager` (12-18), `adult` (18-60), `senior` (>60) |

**Salida:** `data/processed/titanic_clean.csv` — 1 309 filas, 13 columnas.

---

### Stage 2 — Validación semántica (`src/validate.py`)

Se aplican 12 reglas de validación sobre el dataset limpio:

| Regla | Descripción |
|---|---|
| `not_null:passenger_id` | `passenger_id` no puede ser nulo |
| `domain:survived` | Debe ser 0 o 1 |
| `domain:pclass` | Debe ser 1, 2 o 3 |
| `domain:sex` | Debe ser `'male'` o `'female'` |
| `domain:embarked` | Debe ser `'S'`, `'C'` o `'Q'` |
| `range:age` | Edad entre 0 y 120 años |
| `range:fare` | Tarifa ≥ 0 |
| `range:sibsp` | sibsp ≥ 0 |
| `range:parch` | parch ≥ 0 |
| `range:family_size` | family_size ≥ 1 |
| `range:fare_per_person` | fare_per_person ≥ 0 |
| `unique:passenger_id` | Sin duplicados |
| `semantic:child_alone` | Niño (age < 12) no debería viajar solo |

**Salidas:**
- `data/validated/titanic_validated.csv` — registros que pasaron todas las reglas
- `data/validated/titanic_rejected.csv` — registros rechazados con columna `failed_rules`
- `data/reports/validation_report.txt` — reporte con conteo de errores por regla

**Resultado en este dataset:** 1 307 válidos, 2 rechazados (niños de 5 y 11 años marcados como viajando solos).

---

### Stage 3 — Carga a PostgreSQL (`src/load.py`)

#### Tabla en PostgreSQL

```sql
CREATE TABLE IF NOT EXISTS passengers (
    passenger_id    INTEGER      PRIMARY KEY,
    age             NUMERIC(5,2)  NOT NULL,
    fare            NUMERIC(10,4) NOT NULL,
    sex             VARCHAR(10)   NOT NULL,
    sibsp           SMALLINT      NOT NULL,
    parch           SMALLINT      NOT NULL,
    pclass          SMALLINT      NOT NULL,
    embarked        CHAR(1),
    survived        SMALLINT      NOT NULL,
    family_size     SMALLINT      NOT NULL,
    is_alone        SMALLINT      NOT NULL,
    fare_per_person NUMERIC(10,4),
    age_group       VARCHAR(10),
    loaded_at       TIMESTAMP     NOT NULL DEFAULT NOW(),

    CONSTRAINT chk_sex         CHECK (sex IN ('male', 'female')),
    CONSTRAINT chk_pclass      CHECK (pclass IN (1, 2, 3)),
    CONSTRAINT chk_survived    CHECK (survived IN (0, 1)),
    CONSTRAINT chk_embarked    CHECK (embarked IN ('S', 'C', 'Q')),
    CONSTRAINT chk_age         CHECK (age >= 0 AND age <= 120),
    CONSTRAINT chk_fare        CHECK (fare >= 0),
    CONSTRAINT chk_family_size CHECK (family_size >= 1),
    CONSTRAINT chk_is_alone    CHECK (is_alone IN (0, 1))
);
```

#### Proceso de carga

1. Conecta a PostgreSQL (configurado vía variables de entorno).
2. Crea la tabla `passengers` si no existe (idempotente).
3. Consulta los `passenger_id` ya presentes para evitar re-inserciones.
4. Inserta fila por fila con manejo de excepciones:
   - `UniqueViolation` → rechazado como duplicado
   - `CheckViolation` → rechazado por constraint
   - Cualquier otro error → rechazado con detalle del error
5. Cada operación se hace en su propio commit, sin afectar el resto.

**Salidas:**
- `data/validated/titanic_inserted.csv` — filas insertadas correctamente
- `data/validated/titanic_db_rejected.csv` — filas rechazadas con columna `rejection_reason`
- `logs/load.log` — log detallado de cada operación

---

## pgAdmin

Acceder en [http://localhost:8080](http://localhost:8080) con las credenciales del `.env`.

Agregar servidor desde pgAdmin:
- **Host:** `postgres` (nombre del servicio en la red Docker)
- **Port:** `5432`
- **Database:** `titanic`
- **Username / Password:** los del `.env`

---

## Estructura de archivos

```
pipeline/
├── data/
│   ├── raw/                        # datos originales (no modificar)
│   ├── processed/                  # salida Stage 1
│   ├── validated/                  # salida Stages 2 y 3
│   └── reports/                    # reportes de validación
├── logs/                           # logs de carga
├── sql/
│   └── create_table.sql            # DDL de la tabla passengers
├── src/
│   ├── clean.py                    # Stage 1
│   ├── validate.py                 # Stage 2
│   └── load.py                     # Stage 3
├── main.py                         # orquestador
├── Dockerfile                      # imagen del pipeline
├── docker-compose.yml              # postgres + pgadmin + pipeline
├── pyproject.toml
└── .env                            # variables de entorno (no commitear en producción)
```
