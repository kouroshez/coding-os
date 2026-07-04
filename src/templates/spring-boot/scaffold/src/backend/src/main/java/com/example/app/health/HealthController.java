package com.example.app.health;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

// Thin: maps the route and delegates to the service (Spring serializes the value).
@RestController
@RequestMapping("/health")
public class HealthController {

  private final HealthService health;

  public HealthController(HealthService health) {
    this.health = health;
  }

  @GetMapping
  public HealthStatus check() {
    return health.status();
  }
}
