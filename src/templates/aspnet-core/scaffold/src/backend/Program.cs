using {{PROJECT_NAME}}.Common;
using {{PROJECT_NAME}}.Features.Health;

// Exposed so integration tests build the app without binding a real port
// (WebApplicationFactory<Program> needs Program to be reachable).
var builder = WebApplication.CreateBuilder(args);

// DI registrations — services are resolved by the container, never `new`-ed.
builder.Services.AddScoped<HealthService>();

var app = builder.Build();

// The middleware runs first so it wraps every downstream handler; it is the
// ONLY place that shapes an error response.
app.UseMiddleware<ExceptionHandlingMiddleware>();

HealthEndpoints.Map(app);

app.Run();

// Marker class so WebApplicationFactory<Program> can reference the entry point.
public partial class Program;
