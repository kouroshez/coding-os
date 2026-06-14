use axum::{
    http::StatusCode,
    response::{IntoResponse, Response},
    Json,
};
use serde_json::json;

// The ONE central error type. Handlers `?`-propagate into this; its
// IntoResponse impl is the only place an error body is shaped
// (RFC 9457 problem shape per docs/api-contracts/error-format.md).
#[derive(Debug, thiserror::Error)]
pub enum AppError {
    #[error("{0}")]
    NotFound(String),
    #[error("{0}")]
    BadRequest(String),
    #[error("internal error")]
    Internal(#[from] anyhow_like::Error),
}

// Minimal stand-in so the skeleton compiles without an extra crate;
// real services use anyhow / a domain error and a richer From chain.
pub mod anyhow_like {
    #[derive(Debug, thiserror::Error)]
    #[error("{0}")]
    pub struct Error(pub String);
}

impl IntoResponse for AppError {
    fn into_response(self) -> Response {
        let (status, title) = match &self {
            AppError::NotFound(msg) => (StatusCode::NOT_FOUND, msg.clone()),
            AppError::BadRequest(msg) => (StatusCode::BAD_REQUEST, msg.clone()),
            // Full detail to the log only; never internals to the client.
            AppError::Internal(err) => {
                tracing::error!(error = %err, "internal error");
                (StatusCode::INTERNAL_SERVER_ERROR, "Internal Server Error".to_string())
            }
        };

        let body = Json(json!({
            "type": "about:blank",
            "title": title,
            "status": status.as_u16(),
        }));
        (status, body).into_response()
    }
}
