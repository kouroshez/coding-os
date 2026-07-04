<?php

/**
 * Plugin Name: {{PROJECT_NAME}}
 * Description: {{PROJECT_NAME}} business logic — portable across themes.
 * Version: 0.1.0
 * Requires PHP: 8.2
 */

declare(strict_types=1);

if (!defined('ABSPATH')) {
    exit; // No direct access.
}

require_once __DIR__ . '/inc/health.php';

// Register a namespaced REST route. Sanitize on input, escape on output,
// and permission-check every callback (return true here = public read).
add_action('rest_api_init', static function (): void {
    register_rest_route('{{PROJECT_NAME}}/v1', '/health', [
        'methods' => 'GET',
        'permission_callback' => '__return_true',
        'callback' => static function (): WP_REST_Response {
            return new WP_REST_Response(cos_health_status(), 200);
        },
    ]);
});
