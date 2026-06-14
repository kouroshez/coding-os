Rails.application.routes.draw do
  # The routing table — one place every URL lives.
  get "health", to: "health#show"
end
