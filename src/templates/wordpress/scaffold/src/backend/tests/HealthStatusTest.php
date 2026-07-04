<?php

declare(strict_types=1);

use PHPUnit\Framework\TestCase;

require_once __DIR__ . '/../plugin/inc/health.php';

final class HealthStatusTest extends TestCase
{
    public function test_health_status_reports_ok(): void
    {
        self::assertSame('ok', cos_health_status()['status']);
    }
}
