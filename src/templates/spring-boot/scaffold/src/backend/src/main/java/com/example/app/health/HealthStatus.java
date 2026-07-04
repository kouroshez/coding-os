package com.example.app.health;

// Response DTO — Spring serializes it to JSON; no envelope built by hand.
public record HealthStatus(String status) {}
