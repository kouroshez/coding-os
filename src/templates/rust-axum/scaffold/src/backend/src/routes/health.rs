use axum::Json;
use serde::Serialize;

use crate::error::AppError;

#[derive(Serialize)]
pub struct Health {
    status: &'static str,
}

// Thin handler: no logic, returns Result so the error path flows through
// the central AppError shaper like every other route.
pub async fn check() -> Result<Json<Health>, AppError> {
    Ok(Json(Health { status: "ok" }))
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::app;
    use axum::body::Body;
    use axum::http::{Request, StatusCode};
    use http_body_util::BodyExt;
    use tower::ServiceExt;

    #[tokio::test]
    async fn health_returns_ok() {
        let response = app::router()
            .oneshot(Request::builder().uri("/health").body(Body::empty()).unwrap())
            .await
            .unwrap();

        assert_eq!(response.status(), StatusCode::OK);
        let bytes = response.into_body().collect().await.unwrap().to_bytes();
        assert_eq!(&bytes[..], br#"{"status":"ok"}"#);
    }
}
