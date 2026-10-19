# Migration Notes

**Model self-assessed confidence:** 95% (not a measured result)  
**Build at time of writing:** passed  
**Target unit tests:** passed  
**Behavior compared with the original:** passed

The final recommendation is in the pull request description.

---

## What was migrated

- `src/main/java/com/smartContact/error/UserNotFoundException.java` → `app/errors.py` (90% confidence)
- `src/main/java/com/smartContact/model/User.java` → `app/models/user.py` (78% confidence) ⚠️ needs review
- `src/main/java/com/smartContact/model/ErrorMessage.java` → `app/schemas/error.py` (89% confidence)
- `src/main/java/com/smartContact/repository/UserDao.java` → `app/repositories/user_repository.py` (86% confidence)
- `src/main/java/com/smartContact/error/RestResponseEntityExceptionHandling.java` → `app/errors.py` (72% confidence) ⚠️ needs review
- `src/main/java/com/smartContact/service/UserServiceImp.java` → `app/services/user_service.py` (88% confidence)
- `src/main/java/com/smartContact/Controller/UserController.java` → `app/routers/users.py` (86% confidence)

## Skipped (empty or stub files)

- `src/main/java/com/smartContact/service/UserService.java`

## Components that could not be automatically migrated

These components require manual implementation. The migrated code contains
`MIGRATION_NOTE` comments at the relevant locations.

### `UserNotFoundException (protected 4-arg constructor)` in `src/main/java/com/smartContact/error/UserNotFoundException.java`
**Reason:** enableSuppression and writableStackTrace are JVM Throwable internals with no equivalent in most target runtimes.
**Suggestion:** Omit this constructor during migration unless a subclass depends on it. If stack-trace suppression was used for performance, rely on the target's lightweight error values (e.g. Go sentinel errors) instead.

### `User (@Entity schema auto-generation via Hibernate ddl-auto)` in `src/main/java/com/smartContact/model/User.java`
**Reason:** Hibernate builds the DDL implicitly from annotations at context startup. Most target stacks have no 1:1 equivalent, so schema creation must be made explicit.
**Suggestion:** Define the model in the target ORM (e.g. SQLAlchemy, Sequelize/TypeORM, GORM, EF Core) with the exact table and column names. Invoke schema creation on application boot (create_all / sync / AutoMigrate / EnsureCreated) or run an executed startup SQL script with CREATE TABLE IF NOT EXISTS "USER" (...).

### `Lombok annotations (@Data, @Builder, @NoArgsConstructor, @AllArgsConstructor)` in `src/main/java/com/smartContact/model/User.java`
**Reason:** These generate code at compile time through annotation processing, which has no direct equivalent outside Java.
**Suggestion:** Use idiomatic target constructs such as dataclasses/pydantic models, TypeScript classes/interfaces, or Go structs. Write constructors and builders explicitly where callers need them, and exclude the password from string representations.

### `UserDao (runtime-generated proxy implementation)` in `src/main/java/com/smartContact/repository/UserDao.java`
**Reason:** Spring Data creates the implementation at runtime from the interface signature and method names. Go has no reflection-based proxy generation for this.
**Suggestion:** Manually write a Go repository struct with explicit SQL (sqlx) or GORM calls for each method actually used. Optionally use sqlc to generate type-safe code from hand-written SQL.

### `JPA persistence context behaviors (dirty checking, lazy loading, cascade)` in `src/main/java/com/smartContact/repository/UserDao.java`
**Reason:** These implicit ORM behaviors have no direct counterpart in sqlx and only partial ones in GORM.
**Suggestion:** Make all writes explicit, load associations deliberately, and wrap multi-step operations in explicit transactions.

## Observer agent findings

The Observer agent monitored the migration and identified these patterns:

- **After 3 modules:** The Target Expert drops or defers validation behavior to files that don't exist instead of implementing it in place, and the Validator counts accepted, unavoidable language differences against confidence.
- **After 6 modules:** The target expert documents or defers source behaviour (validation constraints, error formats, return contracts) instead of implementing it in the module, which leaves real gaps such as the missing @NotBlank check that dangling docstring references then hide.

## Files requiring manual review

These files were migrated but scored below the confidence threshold.
Review them carefully before merging.

### `src/main/java/com/smartContact/model/User.java`
Confidence: 78%
Issues:
  - [warning] The docstring says the @NotBlank validation lives in app/schemas/user.py, but that file doesn't exist. Searching the whole target codebase finds no blank-name check and no 'please Add the department Name' message.

### `src/main/java/com/smartContact/error/RestResponseEntityExceptionHandling.java`
Confidence: 72%
Issues:
  - [info] Inherited Spring defaults return an empty body or a ProblemDetail body. The migration returns {error, details} bodies instead. The status codes are kept: 400 for validation errors and the HTTPException statuses pass through.
