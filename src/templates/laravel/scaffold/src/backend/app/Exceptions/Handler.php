<?php

namespace App\Exceptions;

use Illuminate\Foundation\Exceptions\Handler as ExceptionHandler;
use Illuminate\Http\JsonResponse;
use Throwable;

// The ONLY place that shapes an error response (RFC 9457 problem shape).
class Handler extends ExceptionHandler
{
    public function render($request, Throwable $e): JsonResponse
    {
        $status = method_exists($e, 'getStatusCode') ? $e->getStatusCode() : 500;

        // Full detail to the logger only; never a stack trace to the client.
        if ($status >= 500) {
            $this->report($e);
        }

        return response()->json([
            'type' => 'about:blank',
            'title' => $status >= 500 ? 'Internal Server Error' : $e->getMessage(),
            'status' => $status,
        ], $status, ['Content-Type' => 'application/problem+json']);
    }
}
