<?php

declare(strict_types=1);

use App\Support\HealthStatus;
use PHPUnit\Framework\TestCase;

require_once __DIR__ . '/../../app/Support/HealthStatus.php';

final class HealthStatusTest extends TestCase
{
    public function test_payload_reports_ok_status(): void
    {
        self::assertSame('ok', HealthStatus::payload()['status']);
    }
}
