import { describe, it, expect, vi, afterEach } from "vitest";
import {
  renderComponent,
  screen,
  fireEvent,
  cleanup,
  waitFor,
} from "$lib/test-utils";
import ChangePasswordForm from "../ChangePasswordForm.svelte";

const changePassword = vi.fn((_current: string, _next: string) =>
  Promise.resolve({}),
);
vi.mock("$lib/api/auth", () => ({
  changePassword: (current: string, next: string) =>
    changePassword(current, next),
}));

afterEach(() => {
  cleanup();
  changePassword.mockClear();
});

async function fill(current: string, next: string, confirm: string) {
  await fireEvent.input(screen.getByLabelText(/current password/i), {
    target: { value: current },
  });
  await fireEvent.input(screen.getByLabelText(/^new password$/i), {
    target: { value: next },
  });
  await fireEvent.input(screen.getByLabelText(/confirm new password/i), {
    target: { value: confirm },
  });
  await fireEvent.click(
    screen.getByRole("button", { name: /set new password/i }),
  );
}

describe("ChangePasswordForm", () => {
  it("renders current, new, and confirm password fields", () => {
    renderComponent(ChangePasswordForm, { props: { onsuccess: vi.fn() } });
    expect(screen.getByLabelText(/current password/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/^new password$/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/confirm new password/i)).toBeInTheDocument();
  });

  it("shows an error without calling the API when confirm does not match", async () => {
    renderComponent(ChangePasswordForm, { props: { onsuccess: vi.fn() } });
    await fireEvent.input(screen.getByLabelText(/current password/i), {
      target: { value: "oldpass1" },
    });
    await fireEvent.input(screen.getByLabelText(/^new password$/i), {
      target: { value: "newpassword1" },
    });
    await fireEvent.input(screen.getByLabelText(/confirm new password/i), {
      target: { value: "newpassword2" },
    });
    await fireEvent.click(
      screen.getByRole("button", { name: /set new password/i }),
    );
    expect(
      await screen.findByText(/passwords do not match/i),
    ).toBeInTheDocument();
    expect(changePassword).not.toHaveBeenCalled();
  });

  it("calls changePassword then onsuccess on a valid submit", async () => {
    const onsuccess = vi.fn();
    renderComponent(ChangePasswordForm, { props: { onsuccess } });
    await fireEvent.input(screen.getByLabelText(/current password/i), {
      target: { value: "oldpass1" },
    });
    await fireEvent.input(screen.getByLabelText(/^new password$/i), {
      target: { value: "newpassword1" },
    });
    await fireEvent.input(screen.getByLabelText(/confirm new password/i), {
      target: { value: "newpassword1" },
    });
    await fireEvent.click(
      screen.getByRole("button", { name: /set new password/i }),
    );
    await waitFor(() =>
      expect(changePassword).toHaveBeenCalledWith("oldpass1", "newpassword1"),
    );
    await waitFor(() => expect(onsuccess).toHaveBeenCalled());
  });

  it("rejects a new password identical to the current one", async () => {
    renderComponent(ChangePasswordForm, { props: { onsuccess: vi.fn() } });
    await fill("samepassword1", "samepassword1", "samepassword1");
    expect(
      await screen.findByText(/must differ from the current password/i),
    ).toBeInTheDocument();
    expect(changePassword).not.toHaveBeenCalled();
  });

  it("rejects a new password shorter than 8 characters", async () => {
    renderComponent(ChangePasswordForm, { props: { onsuccess: vi.fn() } });
    await fill("oldpass1", "short7", "short7");
    expect(
      await screen.findByText(/at least 8 characters/i),
    ).toBeInTheDocument();
    expect(changePassword).not.toHaveBeenCalled();
  });

  it("surfaces the API error message and does not call onsuccess", async () => {
    const onsuccess = vi.fn();
    changePassword.mockRejectedValueOnce(new Error("current password is wrong"));
    renderComponent(ChangePasswordForm, { props: { onsuccess } });
    await fill("wrongpass1", "newpassword1", "newpassword1");
    expect(
      await screen.findByText(/current password is wrong/i),
    ).toBeInTheDocument();
    expect(onsuccess).not.toHaveBeenCalled();
  });

  it("falls back to a generic message when the rejection is not an Error", async () => {
    const onsuccess = vi.fn();
    changePassword.mockRejectedValueOnce("boom");
    renderComponent(ChangePasswordForm, { props: { onsuccess } });
    await fill("oldpass1", "newpassword1", "newpassword1");
    expect(
      await screen.findByText(/password change failed/i),
    ).toBeInTheDocument();
    expect(onsuccess).not.toHaveBeenCalled();
  });

  it("ignores a second submit while the first is still in flight", async () => {
    let release: () => void = () => {};
    changePassword.mockImplementationOnce(
      () => new Promise<object>((resolve) => (release = () => resolve({}))),
    );
    renderComponent(ChangePasswordForm, { props: { onsuccess: vi.fn() } });
    await fill("oldpass1", "newpassword1", "newpassword1");

    // The submit button is disabled while in flight, so a click can't reach
    // the guard — dispatch on the form to prove the re-entrancy check itself
    // holds, not just the disabled attribute in front of it.
    const form = screen.getByRole("button", { name: /saving/i }).closest("form")!;
    await fireEvent.submit(form);
    expect(changePassword).toHaveBeenCalledTimes(1);

    release();
  });
});
