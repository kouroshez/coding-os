<?php

declare(strict_types=1);

namespace App\Support;

final class HealthStatus
{
    /** @return array{status: string} */
    public static function payload(): array
    {
        return ['status' => 'ok'];
    }
}
