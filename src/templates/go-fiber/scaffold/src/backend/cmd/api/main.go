package main

import (
	"log"

	"github.com/gofiber/fiber/v3"
)

func newApp() *fiber.App {
	app := fiber.New()
	app.Get("/health", func(c fiber.Ctx) error {
		return c.JSON(fiber.Map{"status": "ok"})
	})
	return app
}

func main() {
	if err := newApp().Listen(":8080"); err != nil {
		log.Fatal(err)
	}
}
