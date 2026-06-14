class HealthController < ApplicationController
  # Thin: delegates to the model and renders its value.
  def show
    render json: Health.status
  end
end
