import {
  ArgumentsHost,
  Catch,
  ExceptionFilter,
  HttpException,
  HttpStatus,
  Logger,
} from "@nestjs/common";

// The ONLY place that shapes an error response (RFC 9457 problem shape).
// Controllers and providers throw typed errors; this filter maps them.
@Catch()
export class AllExceptionsFilter implements ExceptionFilter {
  private readonly logger = new Logger(AllExceptionsFilter.name);

  catch(exception: unknown, host: ArgumentsHost): void {
    const response = host.switchToHttp().getResponse();
    const status =
      exception instanceof HttpException
        ? exception.getStatus()
        : HttpStatus.INTERNAL_SERVER_ERROR;
    const title =
      exception instanceof HttpException ? exception.message : "Internal Server Error";

    // Full detail to the logger only; never a stack trace to the client.
    if (status >= HttpStatus.INTERNAL_SERVER_ERROR) {
      this.logger.error(exception);
    }

    response.status(status).type("application/problem+json").json({
      type: "about:blank",
      title,
      status,
    });
  }
}
