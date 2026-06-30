using {{PROJECT_NAME}}.Features.Health;
using Xunit;

namespace {{PROJECT_NAME}}.Tests;

public sealed class HealthServiceTests
{
    [Fact]
    public void Status_ReportsOk()
    {
        var health = new HealthService();

        Assert.Equal("ok", health.Status().Status);
    }
}
