# Java CRUD API: Spring to FastAPI Migration

A user-management CRUD REST API, migrated from a Java/Spring codebase (`com.smartContact`) to Python/FastAPI. It exposes HTTP endpoints for creating, reading, updating and deleting `User` records stored in a relational database.

> **Migration status:** 7 of 8 modules migrated. The build passed, the target unit tests passed, and behavior was compared against the original Spring application and passed. The 95% confidence figure is the migration tool's own estimate, not a measured result. See [Known limitations](#known-limitations) and [Manual review required](#manual-review-required) before treating this as production-ready.

---

## Tech Stack

| Concern | Technology |
|---|---|
| Language | Python |
| Web framework | FastAPI |
| ASGI server | Uvicorn |
| Persistence | Database configured via `DATABASE_URL` and initialized from `app/db.py` |
| Dependencies | `requirements.txt` |
| Containerization | `Dockerfile`, `docker-compose.yml` |

Exact library versions are pinned in `requirements.txt`.

---

## Prerequisites

- Python 3 and `pip`. Use the Python version specified in the `Dockerfile` for parity with the container image.
- npm, which is required by one of the setup steps below. See the note in step 3.
- A reachable database that matches the `DATABASE_URL` you configure.
- Optional: Docker and Docker Compose, if you want to use the provided `Dockerfile` / `docker-compose.yml`.

---

## Getting Started

Run these steps in order, from a fresh clone.

### 1. Install Python dependencies

```bash
pip install --no-cache-dir -r requirements.txt
```

### 2. Configure environment variables

Export the variables listed in [Environment Variables](#environment-variables):

```bash
export DATABASE_URL="<your database connection URL>"
export PORT="8080"
export SECRET_KEY="<a strong random secret>"
```

### 3. Resolve additional dependencies

```bash
npm install --package-lock-only
```

> **Note:** This command was run successfully during migration and is part of the recorded setup sequence. However, there is no npm manifest among the project files listed in this repository, so its purpose in a Python/FastAPI project is unclear. Keep it in the sequence for now. Then verify whether it is actually needed and remove it from this README if it is not. See [Manual review required](#manual-review-required).

### 4. Initialize the database schema

```bash
python -c "import asyncio; from app.db import init_db; asyncio.run(init_db())"
```

This creates the tables explicitly. The original Spring app relied on Hibernate `ddl-auto` to generate the schema implicitly at startup, so this step replaces that behavior. See [Migration Notes](#migration-notes).

### 5. Run the application

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8080
```

The API is served at `http://localhost:8080`. FastAPI's interactive docs are typically available at `/docs`, unless they have been disabled in `app/main.py`.

### Docker

A `Dockerfile` and `docker-compose.yml` are included. Their exact invocation was not part of the verified setup, so review both files before relying on them.

---

## Running Tests

```bash
python -m pytest -q
```

The target unit tests passed during migration.

---

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `DATABASE_URL` | Yes | Connection URL for the application database. It is consumed by the database layer (`app/db.py`, configured via `app/config.py`). |
| `PORT` | Yes | Port the application listens on. The documented run command passes `--port 8080` explicitly to Uvicorn, which takes precedence over this variable for that invocation. Check `app/config.py` and the `Dockerfile` to see where `PORT` is actually read. |
| `SECRET_KEY` | Yes | Application secret. Use a strong random value and never commit it. Check `app/config.py` for how it is used. |

---

## Architecture Overview

The application follows a layered structure: router, then service, then repository, then model. This mirrors the original Spring layout of controller, service, DAO and entity.

```
app/
├── __init__.py
├── main.py                        # FastAPI app creation, router registration, exception handler wiring
├── config.py                      # Settings loaded from environment variables
├── db.py                          # Database engine/session setup and init_db() schema creation
├── errors.py                      # Custom exceptions and HTTP error handlers
├── models/
│   └── user.py                    # User ORM model (database table definition)
├── schemas/
│   └── error.py                   # Error response schema
├── repositories/
│   └── user_repository.py         # Data access for User (explicit queries)
├── routers/
│   └── users.py                   # User CRUD HTTP endpoints
└── services/
    └── user_service.py            # Business logic between routers and repository
```

**Request flow:**

1. `app/routers/users.py` receives the HTTP request.
2. The router calls `app/services/user_service.py`.
3. The service calls `app/repositories/user_repository.py`.
4. The repository reads or writes the `User` model in `app/models/user.py`.

**Error handling:**

- Domain errors raised anywhere in this flow are defined in `app/errors.py`.
- They are translated into HTTP responses shaped by `app/schemas/error.py`.

---

## Migration Notes

These are the key differences from the original Spring codebase:

- **Schema creation is now explicit.** Hibernate's `ddl-auto` generated the schema from `@Entity` annotations at startup. In this project, the `User` table is defined in `app/models/user.py` and created by `init_db()` in `app/db.py` (setup step 4). The table and column names must match the original exactly for existing databases to remain compatible.
- **Lombok has been removed.** `@Data`, `@Builder`, `@NoArgsConstructor` and `@AllArgsConstructor` generated code at compile time. They have been replaced by explicit Python constructs. Callers that relied on the builder or on generated equals/hashCode/toString must use the Python equivalents. The password must not appear in string representations.
- **The repository is hand-written.** Spring Data generated the `UserDao` implementation at runtime from method names. `app/repositories/user_repository.py` now contains explicit implementations of the data-access methods.
- **There is no JPA persistence context.** Dirty checking, lazy loading and cascades no longer happen implicitly. All writes must be explicit, associations must be loaded deliberately, and multi-step operations must be wrapped in explicit transactions.
- **Exception handling has been reworked.**
  - The Spring `@ControllerAdvice`-style handler (`RestResponseEntityExceptionHandling`) is replaced by FastAPI exception handlers.
  - `UserNotFoundException` is represented in `app/errors.py`.
  - The error response body is defined in `app/schemas/error.py`.
- **One module was not migrated.** Only 7 of 8 modules were migrated, and the remaining module is not identified in the migration output. Compare the original source tree against `app/` to find it.

---

## Known Limitations

The following components from the original codebase have no direct equivalent and were not migrated 1:1:

| File | Component | Reason |
|---|---|---|
| `app/errors.py` | Protected 4-arg constructor (`enableSuppression`, `writableStackTrace`) | These are JVM `Throwable` internals with no Python equivalent. The constructor was omitted. This only matters if a subclass depended on it. |
| `app/models/user.py` | `@Entity` schema auto-generation via Hibernate `ddl-auto` | Hibernate builds DDL implicitly. In this project, schema creation is explicit via `init_db()`. Schema migrations or evolution, beyond initial creation, are not handled automatically. |
| `app/models/user.py` | Lombok annotations (`@Data`, `@Builder`, `@NoArgsConstructor`, `@AllArgsConstructor`) | Compile-time annotation processing has no Python equivalent. Constructors and builders are written explicitly where needed. |
| `app/repositories/user_repository.py` | Runtime-generated Spring Data proxy | The method implementations are derived from method names at runtime in Spring. They are written by hand in `app/repositories/user_repository.py`, and only the methods actually used were implemented. |
| `app/repositories/user_repository.py` | JPA persistence context (dirty checking, lazy loading, cascade) | These implicit ORM behaviors are not reproduced. Writes and transactions must be explicit. |

Additional limitations:

- **Missing module.** One of the 8 original modules was not migrated (see [Migration Notes](#migration-notes)).
- **Unexplained npm step.** The `npm install --package-lock-only` setup step has no corresponding npm manifest among the listed project files.

No setup commands failed during migration.

---

## Manual Review Required

Verify the following before relying on this code.

### 1. Low-confidence modules

- **`app/models/user.py`**
  - Confirm that the table name, column names, types, nullability, unique constraints and ID generation match the original schema exactly.
  - Confirm that the password is excluded from any string/repr output and from API responses.
- **`app/errors.py`**
  - Related files: `app/schemas/error.py` and handler registration in `app/main.py`.
  - Confirm that the HTTP status codes and error response bodies match the original for every handled exception, including not-found and validation errors.

### 2. Repository and transactions

- **`app/repositories/user_repository.py`:** check that every method `UserDao` exposed and that the original code actually called has an equivalent with the same semantics.
- **`app/services/user_service.py`:** check that any operation that relied on JPA dirty checking or cascades now persists changes explicitly and runs inside a transaction where needed.

### 3. Schema initialization

- **`app/db.py`:** confirm that `init_db()` is safe to run against an existing database and does not drop or alter existing tables unexpectedly.

### 4. Configuration

- **`app/config.py`:** confirm how `PORT` and `SECRET_KEY` are consumed, and whether `PORT` is honored given the hard-coded `--port 8080` in the run command.

### 5. The unmigrated module

- Identify which of the 8 original modules is missing, and decide whether it must be ported.

### 6. The `npm install --package-lock-only` step

- Determine why it is part of the setup sequence for a Python project.
- Remove it from the setup sequence if it is not needed.

### 7. Docker files

- **`Dockerfile` / `docker-compose.yml`:** confirm that they use the same install, DB setup and run commands as documented here, and that they pass `DATABASE_URL`, `PORT` and `SECRET_KEY` correctly.