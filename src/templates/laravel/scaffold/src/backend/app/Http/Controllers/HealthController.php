<?php

namespace App\Http\Controllers;

use App\Support\HealthStatus;
use Illuminate\Http\JsonResponse;

// Thin controller — returns a value; Laravel serializes. No error shaping here.
class HealthController extends Controller
{
    public function show(): JsonResponse
    {
        return response()->json(HealthStatus::payload());
    }
}
