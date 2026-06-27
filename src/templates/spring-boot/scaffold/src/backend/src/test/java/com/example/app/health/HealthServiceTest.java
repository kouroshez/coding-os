package com.example.app.health;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;

class HealthServiceTest {

    @Test
    void statusReportsOk() {
        HealthStatus result = new HealthService().status();

        assertThat(result.status()).isEqualTo("ok");
    }
}
