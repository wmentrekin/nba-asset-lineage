import { describe, expect, it } from "vitest";

import { RESET_STATUS_CARDS } from "./foundation";

describe("RESET_STATUS_CARDS", () => {
  it("describes the reset scaffold", () => {
    expect(RESET_STATUS_CARDS).toHaveLength(3);
    expect(RESET_STATUS_CARDS[0]?.title).toBe("Base output");
  });
});
