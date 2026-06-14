require_relative "boot"

require "rails"
require "action_controller/railtie"

# Rails app bootstrap — wires the framework, owns no business logic.
module Backend
  class Application < Rails::Application
    config.load_defaults 7.1
    config.api_only = true
  end
end
