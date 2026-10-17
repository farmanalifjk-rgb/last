export function ForgotPasswordPage() {
    return `
      <main class="flex min-h-screen items-center justify-center bg-slate-50 px-4 py-10">
        <section class="w-full max-w-md rounded-2xl border border-slate-200 bg-white p-7 shadow-xl shadow-slate-200/50 sm:p-9">
          <a href="#/login" class="text-sm font-semibold text-violet-700 hover:underline">← Back to login</a>
          <div class="mt-7 flex h-12 w-12 items-center justify-center rounded-xl bg-violet-100 text-violet-700"><i data-lucide="key-round" width="22" height="22"></i></div>
          <h1 class="mt-5 text-2xl font-extrabold tracking-tight text-slate-950">Reset your password</h1>
          <p class="mt-2 text-sm leading-6 text-slate-500">We’ll send a one-time code to your registered email address.</p>
          <form id="password-reset-form" class="mt-7 space-y-5">
            <div>
              <label for="reset-email" class="mb-2 block text-sm font-semibold text-slate-800">Email address</label>
              <input id="reset-email" name="email" type="email" autocomplete="email" required placeholder="you@company.com" class="h-12 w-full rounded-xl border border-slate-200 bg-slate-50 px-4 text-sm outline-none transition focus:border-violet-500 focus:bg-white focus:ring-4 focus:ring-violet-500/10" />
            </div>
            <div id="reset-confirm-fields" class="hidden space-y-5">
              <div>
                <label for="reset-code" class="mb-2 block text-sm font-semibold text-slate-800">6-digit verification code</label>
                <input id="reset-code" name="code" type="text" inputmode="numeric" autocomplete="one-time-code" pattern="[0-9]{6}" maxlength="6" placeholder="000000" class="h-12 w-full rounded-xl border border-slate-200 bg-slate-50 px-4 text-center text-lg font-bold tracking-[0.4em] outline-none focus:border-violet-500 focus:bg-white focus:ring-4 focus:ring-violet-500/10" />
              </div>
              <div>
                <label for="reset-new-password" class="mb-2 block text-sm font-semibold text-slate-800">New password</label>
                <input id="reset-new-password" name="new_password" type="password" autocomplete="new-password" minlength="8" placeholder="Enter a new password" class="h-12 w-full rounded-xl border border-slate-200 bg-slate-50 px-4 text-sm outline-none focus:border-violet-500 focus:bg-white focus:ring-4 focus:ring-violet-500/10" />
              </div>
              <button id="reset-resend" type="button" class="text-sm font-semibold text-violet-700 hover:underline">Send another code</button>
            </div>
            <p id="reset-message" role="status" aria-live="polite" class="min-h-5 text-sm"></p>
            <button id="reset-submit" type="submit" class="flex h-12 w-full items-center justify-center rounded-xl bg-slate-950 px-4 text-sm font-bold text-white transition hover:bg-violet-700 disabled:cursor-not-allowed disabled:opacity-60">Send reset code</button>
          </form>
        </section>
      </main>`;
}

export function initializeForgotPassword() {
    const form = document.getElementById("password-reset-form");
    const emailInput = document.getElementById("reset-email");
    const fields = document.getElementById("reset-confirm-fields");
    const codeInput = document.getElementById("reset-code");
    const passwordInput = document.getElementById("reset-new-password");
    const message = document.getElementById("reset-message");
    const submit = document.getElementById("reset-submit");
    const resend = document.getElementById("reset-resend");
    if (!form || !emailInput || !fields || !message || !submit) return;
    let stage = "request";

    async function sendCode() {
        const email = emailInput.value.trim();
        if (!email) throw new Error("Enter your registered email address.");
        const { requestPasswordReset } = await import("../services/auth.js");
        const result = await requestPasswordReset(email);
        stage = "confirm";
        fields.classList.remove("hidden");
        codeInput.required = true;
        passwordInput.required = true;
        submit.textContent = "Reset password";
        message.className = "min-h-5 text-sm text-emerald-700";
        message.textContent = result.message || "If an account with that email exists, a reset code has been sent.";
    }

    form.addEventListener("submit", async (event) => {
        event.preventDefault();
        message.textContent = "";
        submit.disabled = true;
        submit.textContent = stage === "request" ? "Sending code…" : "Resetting password…";
        try {
            const auth = await import("../services/auth.js");
            if (stage === "request") {
                await sendCode();
            } else {
                const email = emailInput.value.trim();
                const code = codeInput.value.trim();
                const newPassword = passwordInput.value;
                if (!/^[0-9]{6}$/.test(code)) throw new Error("Enter the 6-digit reset code.");
                if (!newPassword) throw new Error("Enter a new password.");
                const result = await auth.confirmPasswordReset({ email, code, newPassword });
                message.className = "min-h-5 text-sm text-emerald-700";
                message.textContent = result.message || "Password reset successfully. Please sign in.";
                submit.textContent = "Return to login";
                submit.type = "button";
                submit.onclick = () => { window.location.hash = "#/login"; };
                stage = "done";
            }
        } catch (error) {
            message.className = "min-h-5 text-sm text-rose-600";
            message.textContent = error.message || "Unable to reset the password. Try again.";
        } finally {
            submit.disabled = false;
            if (stage === "request") submit.textContent = "Send reset code";
            else if (stage === "confirm") submit.textContent = "Reset password";
        }
    });

    resend?.addEventListener("click", async () => {
        resend.disabled = true;
        message.textContent = "";
        try { await sendCode(); }
        catch (error) {
            message.className = "min-h-5 text-sm text-rose-600";
            message.textContent = error.message || "Unable to request another code.";
        } finally { resend.disabled = false; }
    });
}
