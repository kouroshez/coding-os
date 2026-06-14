namespace {{PROJECT_NAME}}.Features.Health;

// Transport-free service — no HttpContext, so it is unit-testable in isolation.
public sealed class HealthService
{
    public HealthStatus Status() => new("ok");
}

public sealed record HealthStatus(string Status);
