# frozen_string_literal: true

require "rails_helper"

# Request spec for the existing GET /health endpoint.
# Drives the Rack app through the request layer (never binds a real port),
# exercising HealthController#show -> Health.status, plus a direct model
# assertion on the existing Health.status method.
RSpec.describe "Health", type: :request do
  describe "GET /health" do
    it "returns 200 with the ok status body" do
      get "/health"

      expect(response).to have_http_status(:ok)
      expect(response.parsed_body).to eq("status" => "ok")
    end
  end

  describe "Health.status" do
    it "reports ok without touching HTTP" do
      expect(Health.status).to eq(status: "ok")
    end
  end
end
