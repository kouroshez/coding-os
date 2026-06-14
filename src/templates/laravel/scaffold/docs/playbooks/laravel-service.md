<!-- domain:BACKEND | layer:playbook | ssot:true | updated:{{DATE}} -->
# Laravel Service Playbook

Purpose: The end-to-end recipe for adding or changing a Laravel endpoint in {{PROJECT_NAME}}.
Read when: Any task that adds a route, controller, service, Eloquent model, or Form Request.
Skip when: Pure infra/devops work — see the deployment docs.
Read next: [Laravel Engineering Rules](../engineering/laravel-rules.md), [Error Format](../api-contracts/error-format.md)

> Nav: [Master Index](../00-index.md)

## Add an endpoint (the only sanctioned path)

1. **Contract first** — define request/response shapes; error cases use the
   shared problem format ([error-format](../api-contracts/error-format.md)).
2. **Route** — `routes/api.php`: one line mapping the path to a controller method.
3. **Form Request** — validate input fail-closed in a `FormRequest`; the
   controller receives validated data, never raw `$request->all()`.
4. **Controller** — thin: call one service method, return the value.
5. **Service** — `app/Services/`: business logic only, no `Request`/`Response`.
6. **Model** — `app/Models/`: Eloquent; services own queries, controllers never do.
7. **Test** — unit-test the service + a feature test for the route (happy + error).
8. **Verify** — `cd src/backend && composer lint && composer test`.

## Anti-patterns

- Error JSON built inside a controller — the `Handler` owns the shape.
- A service importing `Request`/`Response` — that layer stays framework-light.
- Business logic in a route closure — move it to a service.
