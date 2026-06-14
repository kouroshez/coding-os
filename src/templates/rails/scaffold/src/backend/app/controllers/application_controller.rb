class ApplicationController < ActionController::API
  # The ONLY place that shapes an error response (RFC 9457 problem shape).
  # Controllers and models raise typed errors; this chain maps them.
  rescue_from StandardError, with: :render_internal_error
  rescue_from ActiveRecord::RecordNotFound, with: :render_not_found

  private

  def render_not_found
    render_problem(status: :not_found, title: "Not Found")
  end

  def render_internal_error(exception)
    # Full detail to the logger only; never a backtrace to the client.
    logger.error(exception)
    render_problem(status: :internal_server_error, title: "Internal Server Error")
  end

  def render_problem(status:, title:)
    render(
      json: { type: "about:blank", title: title, status: Rack::Utils.status_code(status) },
      status: status,
      content_type: "application/problem+json",
    )
  end
end
