namespace {{PROJECT_NAME}}.Features.Health;

// Thin: maps the route and delegates to the service (the host serializes).
public static class HealthEndpoints
{
    public static void Map(IEndpointRouteBuilder routes)
    {
        routes.MapGet("/health", (HealthService health) => health.Status());
    }
}
