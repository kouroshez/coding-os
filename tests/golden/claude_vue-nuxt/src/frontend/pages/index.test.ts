// cos-golden-fixture — sample page test (scaffolded 2026-01-01); see docs/playbooks/nuxt-app.md.
import { describe, expect, it } from "vitest";
import { mount } from "@vue/test-utils";

import IndexPage from "./index.vue";

describe("pages/index.vue", () => {
  it("renders the project title in the page heading", () => {
    const wrapper = mount(IndexPage);

    expect(wrapper.find("h1").text()).toBe("cos-golden-fixture");
  });

  it("renders a single landing main region", () => {
    const wrapper = mount(IndexPage);

    expect(wrapper.findAll("main")).toHaveLength(1);
  });
});
