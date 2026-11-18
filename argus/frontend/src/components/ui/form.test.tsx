import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { Field, Input, TagInput } from "./form";

afterEach(cleanup);

describe("Field", () => {
  it("links its label and hint to the control inside it", () => {
    render(
      <Field label="Full name" hint="As on your resume">
        <Input defaultValue="Alex" />
      </Field>,
    );
    const input = screen.getByLabelText("Full name") as HTMLInputElement;
    expect(input.value).toBe("Alex");
    expect(input.getAttribute("aria-describedby")).toBe(screen.getByText("As on your resume").id);
  });

  it("labels the text box of a TagInput, not its chip buttons", () => {
    render(
      <Field label="Skills">
        <TagInput value={["python"]} onChange={() => {}} />
      </Field>,
    );
    expect(screen.getByLabelText("Skills").tagName).toBe("INPUT");
    expect(screen.getByRole("button", { name: "Remove python" })).toBeTruthy();
  });
});
