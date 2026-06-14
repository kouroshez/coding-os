import { Component, ChangeDetectionStrategy } from "@angular/core";
import { RouterOutlet } from "@angular/router";

// Root standalone component — shell only, no business logic.
@Component({
  selector: "app-root",
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterOutlet],
  template: `
    <main>
      <h1>{{ title }}</h1>
      <router-outlet />
    </main>
  `,
})
export class AppComponent {
  readonly title = "{{PROJECT_NAME}}";
}
