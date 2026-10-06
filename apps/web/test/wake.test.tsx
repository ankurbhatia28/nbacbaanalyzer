import { act, cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { WAKE_AFTER_MS, WAKE_TEXT, WakeNote } from "@/components/WakeNote";

beforeEach(() => vi.useFakeTimers());
afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

describe("WakeNote", () => {
  it("says nothing while a warm server would still be answering", () => {
    render(<WakeNote />);
    act(() => vi.advanceTimersByTime(WAKE_AFTER_MS - 1));
    expect(screen.queryByRole("status")).toBeNull();
  });

  it("explains the wait once it is longer than a warm server takes", () => {
    render(<WakeNote />);
    act(() => vi.advanceTimersByTime(WAKE_AFTER_MS));
    expect(screen.getByRole("status").textContent).toBe(WAKE_TEXT);
  });

  it("starts over when the wait ends and another begins", () => {
    const { unmount } = render(<WakeNote />);
    act(() => vi.advanceTimersByTime(WAKE_AFTER_MS));
    unmount();
    render(<WakeNote />);
    expect(screen.queryByRole("status")).toBeNull();
  });
});
