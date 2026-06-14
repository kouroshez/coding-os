<?php

// Theme bootstrap — hooks + asset enqueue only. No business logic here
// (that belongs in the plugin so it survives a theme swap).

add_action('after_setup_theme', static function (): void {
    add_theme_support('title-tag');
    add_theme_support('post-thumbnails');
});

add_action('wp_enqueue_scripts', static function (): void {
    wp_enqueue_style(
        '{{PROJECT_NAME}}-style',
        get_stylesheet_uri(),
        [],
        wp_get_theme()->get('Version')
    );
});
