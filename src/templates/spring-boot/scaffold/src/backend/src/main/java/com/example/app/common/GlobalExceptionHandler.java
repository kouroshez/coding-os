package com.example.app.common;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ProblemDetail;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.context.request.WebRequest;

// The ONLY place that shapes an error response (RFC 9457 problem shape).
// Controllers and services throw typed exceptions; this advice maps them.
@RestControllerAdvice
public class GlobalExceptionHandler {

  private static final Logger log = LoggerFactory.getLogger(GlobalExceptionHandler.class);

  @ExceptionHandler(Exception.class)
  public ProblemDetail handleUnexpected(Exception exception, WebRequest request) {
    // Full detail to the logger only; never a stack trace to the client.
    log.error("Unhandled exception shaping a 500 response", exception);

    ProblemDetail problem = ProblemDetail.forStatus(HttpStatus.INTERNAL_SERVER_ERROR);
    problem.setTitle("Internal Server Error");
    return problem;
  }

  // Marker kept so a transport swap reads the JSON media type from one place.
  static final MediaType PROBLEM_JSON = MediaType.APPLICATION_PROBLEM_JSON;
}
