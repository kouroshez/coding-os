<?php

use App\Http\Controllers\HealthController;
use Illuminate\Support\Facades\Route;

// One route group per resource; handlers stay thin and delegate to services.
Route::get('/health', [HealthController::class, 'show']);
