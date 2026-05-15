# Hexagonal Anti-Patterns — Field Guide

Twelve concrete failure modes seen across real codebases. For each: how to spot it, why it bites, the fix.

## 1. Anemic Domain Model

**Symptom**: `domain/` is a folder of dataclasses / structs / interfaces with public fields and zero methods. All the rules live in `OrderService.calculateTotal(...)` in the application layer.

**Why it bites**: the "domain" layer is now just DTOs. Business rules are scattered across services. Two teams write two different `calculateTotal` because there's no obvious place for it.

**Fix**: move behavior onto the entity. `order.addLineItem(item)` enforces the invariant; `OrderService` calls it. The entity is the single guardian of its invariants.

```
✗ if (order.status === 'paid') throw new Error('cannot edit');
   order.lineItems.push(item);

✓ order.addLineItem(item);  // raises CannotEditPaidOrder internally
```

## 2. Framework Types in Ports

**Symptom**: `UserRepository.save(req: HttpRequest)` or `PaymentGateway.charge(ctx: fiber.Ctx, ...)`. Outbound port returns `*sql.Rows` or `dict[str, Any]` to the use case.

**Why it bites**: the adapter is supposed to hide the framework. If the port leaks framework types, swapping the framework requires rewriting every use case.

**Fix**: ports speak in domain types and primitives only. Translation happens **at the adapter boundary**, not in the use case.

## 3. Port-as-DTO Confusion

**Symptom**: `ports/` directory contains both interface files AND DTO files. People start importing the DTO from the port file into screens "for convenience".

**Why it bites**: DTOs are now coupled to ports — changing one requires changing both. Screens import application-layer types they shouldn't see.

**Fix**: Ports = interfaces. DTOs = command/query data classes that travel through the port. Put DTOs next to the use case, not in `ports/`.

## 4. God Use Case

**Symptom**: `OrderService` with 20 public methods: `place`, `cancel`, `refund`, `addNote`, `splitShipment`, `markFraud`, ...

**Why it bites**: changing one rule risks 19 others. Tests are huge and slow. The "use case" is really a service — it has no single user-meaningful operation.

**Fix**: one class per use case. `PlaceOrder`, `CancelOrder`, `RefundOrder`. They can share helpers, but their public surface is one method.

## 5. Premature Port Extraction

**Symptom**: every concrete class wrapped in an interface "for testability". Two-line `EmailFormatter` class with a four-line `IEmailFormatter` interface.

**Why it bites**: pointless indirection. The interface and impl change together. Reading the code requires jumping files.

**Fix**: extract a port when:
- you need a fake/in-memory implementation for tests, OR
- you have (or genuinely anticipate) two implementations, OR
- you're crossing a process/network boundary.

A pure-function helper does not need an interface.

## 6. Reverse Dependency

**Symptom**: a file in `domain/` imports from `application/` or `adapter/`. Or `application/` imports from `adapter/`.

**Why it bites**: the dependency rule (inner layers know nothing of outer) is broken. The domain now depends on infrastructure. Tests for domain start needing a database.

**Fix**: if domain needs something from outside, you're missing a port. Add it to `application/ports/`, inject it where the domain operation runs.

Compiler enforcement: Go's `internal/` privacy + a `depguard` lint rule. Python's `import-linter`. TypeScript's `eslint-plugin-boundaries`.

## 7. Use Case Returns Framework Response

**Symptom**: `placeOrder.execute(...)` returns a `Response` / `JSONResponse` / `*fiber.Ctx` write.

**Why it bites**: the use case can no longer be called from a CLI, queue worker, or test without instantiating an HTTP framework.

**Fix**: use case returns a typed Output dataclass. The HTTP adapter maps Output → JSON response. The CLI adapter maps Output → text. The queue worker maps Output → ack/nack.

## 8. Sprinkling Transactions

**Symptom**: every repository starts/commits its own transaction. Multi-repo operations either don't get atomicity or get it via spaghetti `db.transaction { ... }` blocks in the controller.

**Why it bites**: you cannot reason about atomicity from one place. Adding a new step to a use case can silently break atomicity.

**Fix**: outbound port `UnitOfWork` (or `Transactor`). The use case wraps its multi-step block in `uow.run(() => {...})`. Postgres adapter implements `Run` with `BEGIN/COMMIT`. In-memory test adapter implements with a no-op or a list of pending mutations.

## 9. Adapter Owns the Port Interface

**Symptom**: `postgres/user_repository.go` defines `UserRepository` interface AND its impl. The application layer imports the interface from the adapter package.

**Why it bites**: dependency inversion is broken. The application now depends on the adapter package. Swapping Postgres for MongoDB requires changing the import path in every use case.

**Fix**: ports are owned by **the layer that uses them** (application). Adapters import the port and implement it. This is the "Dependency Inversion Principle" in action.

## 10. ORM Models = Domain Entities

**Symptom**: SQLAlchemy / GORM / Prisma model class is also the "domain entity" — same class, used everywhere.

**Why it bites**: domain entities now carry framework metadata, lazy loading, magic field access. Tests need a database to instantiate one. Refactoring the schema means refactoring the domain.

**Fix**: pay the mapping tax. ORM model lives in the adapter (`postgres/models.py` or `internal/adapter/postgres/models.go`). Repository converts row → domain entity on read, domain entity → row on write. Yes, it's more code. Yes, it's worth it.

## 11. Singleton Use Cases at Module Scope

**Symptom**: `export const placeOrder = new PlaceOrder(repo, gateway, clock);` at top of a module. Or `_instance = SendMessage(...)` at module load.

**Why it bites**: tests cannot swap dependencies. Composition is implicit and scattered. Order-of-import bugs appear at startup.

**Fix**: build everything once in the composition root (`main`, `App.tsx`, `lifespan`). Inject down. No module-scope `new`s.

## 12. "It's Just CRUD, We Don't Need a Use Case"

**Symptom**: HTTP handler calls repository directly. `GET /users/123` returns whatever the repository returns.

**Why it bites**: works fine until "users with subscription" needs an N+1 fix, or "soft-deleted users hidden from regular queries" creeps in. Now the handler has business logic; you can't tell where the rules live.

**Fix**: even for read-only operations, define a Query use case. `GetUserProfile(userId)` is a use case. It happens to call one repository method today. Tomorrow it composes three. Tests stay stable.

This is the **Query** side of CQRS, lite — separate from Command use cases that mutate.

---

## Diagnostic Questions

When reviewing a hexagonal codebase, ask these:

1. Can I run **all use case tests** without Docker, network, or a real database? *(If no → fakes are missing.)*
2. Can I `grep -r 'fiber\|gorm\|fastapi\|axios' internal/domain/` and get **zero hits**? *(If no → reverse dependency leaked in.)*
3. Pick a use case at random. Can I describe what it does in one sentence? *(If no → it's a god service, split it.)*
4. Pick an outbound port at random. Could I implement it in-memory in <50 lines? *(If no → port is too fat or leaks framework types.)*
5. If I deleted all of `cmd/api/` (Go) or `App.tsx` (RN) or `delivery/http/` (Python), would the rest of the code still compile? *(If yes ✓ — composition is properly isolated. If no → application leaks delivery details.)*

If you can answer "yes" to all five, the architecture is honest. If not, the failing answer points at the work to do.
