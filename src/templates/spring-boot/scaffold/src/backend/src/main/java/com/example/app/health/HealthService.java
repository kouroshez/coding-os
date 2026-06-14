package com.example.app.health;

import org.springframework.stereotype.Service;

// Transport-free service — no HttpServletRequest, so it is unit-testable in isolation.
@Service
public class HealthService {

    public HealthStatus status() {
        return new HealthStatus("ok");
    }
}
