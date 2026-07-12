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
});
