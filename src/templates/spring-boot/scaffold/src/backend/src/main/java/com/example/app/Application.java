package com.example.app;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

// SpringApplication bootstrap — owns wiring only, no business logic.
// Component scanning discovers @RestController / @Service / @Repository beans
// in this package and below; the container injects them by constructor.
@SpringBootApplication
public class Application {

    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
        System.out.println("{{PROJECT_NAME}} backend started (spring-boot)");
    }
}
