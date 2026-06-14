use axum::{routing::get, Router};
use tower_http::trace::TraceLayer;

use crate::routes::health;

// Single place that assembles routes + tower middleware layers.
// Handlers own no wiring; middleware lives here, never inside a handler.
pub fn router() -> Router {
    Router::new()
        .route("/health", get(health::check))
        .layer(TraceLayer::new_for_http())
}
