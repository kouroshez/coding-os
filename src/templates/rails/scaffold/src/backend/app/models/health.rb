# Plain model (no table) — business logic stays out of the controller.
class Health
  def self.status
    { status: "ok" }
  end
end
