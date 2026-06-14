using System.Net.Mime;
using Microsoft.AspNetCore.Mvc;

namespace {{PROJECT_NAME}}.Common;

// The ONLY place that shapes an error response (RFC 9457 problem shape).
// Endpoints and services throw typed exceptions; this middleware maps them.
public sealed class ExceptionHandlingMiddleware(
    RequestDelegate next,
    ILogger<ExceptionHandlingMiddleware> logger)
{
    public async Task InvokeAsync(HttpContext context)
    {
        try
        {
            await next(context);
        }
        catch (Exception exception)
        {
            // Full detail to the logger only; never a stack trace to the client.
            logger.LogError(exception, "Unhandled exception shaping a 500 response");

            var problem = new ProblemDetails
            {
                Type = "about:blank",
                Title = "Internal Server Error",
                Status = StatusCodes.Status500InternalServerError,
            };

            context.Response.StatusCode = problem.Status.Value;
            context.Response.ContentType = MediaTypeNames.Application.ProblemJson;
            await context.Response.WriteAsJsonAsync(problem);
        }
    }
}
