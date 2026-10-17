export function LoginPage() {
    return `
        <div class="min-h-screen w-full bg-white lg:grid lg:grid-cols-[54%_46%]">

            <!-- =====================================================
                 LEFT BRAND / BUSINESS PANEL
                 ===================================================== -->
            <section
                class="relative hidden min-h-screen overflow-hidden bg-gradient-to-br from-[#3820c9] via-[#5334e8] to-[#211c45] text-white lg:flex"
            >

                <!-- Decorative circles -->
                <div class="pointer-events-none absolute -left-40 -top-48 h-[520px] w-[520px] rounded-full border border-white/10"></div>

                <div class="pointer-events-none absolute -bottom-[400px] -right-[250px] h-[650px] w-[650px] rounded-full border border-white/10"></div>

                <div class="pointer-events-none absolute left-0 top-0 h-full w-full bg-[radial-gradient(circle_at_20%_20%,rgba(130,92,255,0.45),transparent_35%)]"></div>


                <div class="relative z-10 flex min-h-screen w-full flex-col px-10 py-10 xl:px-14">

                    <!-- Brand -->
                    <div class="flex items-center gap-3">

                        <div
                            class="flex h-11 w-11 items-center justify-center rounded-xl border border-white/20 bg-white/15 text-xs font-black backdrop-blur"
                        >
                            POS
                        </div>

                        <span class="text-sm font-extrabold tracking-[0.12em]">
                            POS SYSTEM
                        </span>

                    </div>


                    <!-- Dashboard Preview -->
                    <div
                        class="my-auto mb-8 mt-12 w-full max-w-[760px] overflow-hidden rounded-xl border border-white/15 bg-[#111117] shadow-2xl"
                    >

                        <!-- Preview top bar -->
                        <div class="flex h-9 items-center gap-1.5 bg-[#1d1d27] px-3">

                            <span class="h-1.5 w-1.5 rounded-full bg-[#686875]"></span>
                            <span class="h-1.5 w-1.5 rounded-full bg-[#686875]"></span>
                            <span class="h-1.5 w-1.5 rounded-full bg-[#686875]"></span>

                            <div class="ml-auto h-2 w-20 rounded-full bg-[#32323e]"></div>

                        </div>


                        <div class="grid min-h-[310px] grid-cols-[70px_1fr]">

                            <!-- Mini sidebar -->
                            <div class="border-r border-[#292933] bg-[#181820] p-3">

                                <div class="mx-auto mb-7 h-3 w-8 rounded bg-[#6547e8]"></div>

                                <div class="mb-2 h-6 rounded bg-[#6547e8]"></div>
                                <div class="mb-2 h-6 rounded bg-[#292934]"></div>
                                <div class="mb-2 h-6 rounded bg-[#292934]"></div>
                                <div class="mb-2 h-6 rounded bg-[#292934]"></div>
                                <div class="mb-2 h-6 rounded bg-[#292934]"></div>

                            </div>


                            <!-- Mini dashboard -->
                            <div class="bg-[#111117] p-5">

                                <div class="mb-5">

                                    <div class="h-2.5 w-28 rounded bg-gray-200"></div>

                                    <div class="mt-2 h-1.5 w-44 rounded bg-[#35353f]"></div>

                                </div>


                                <!-- Cards -->
                                <div class="grid grid-cols-3 gap-3">

                                    <div class="rounded-lg border border-[#292934] bg-[#1c1c25] p-3">

                                        <div class="h-5 w-5 rounded-md bg-[#6547e8]"></div>

                                        <div class="mt-3 h-2 w-14 rounded bg-gray-200"></div>

                                        <div class="mt-2 h-1.5 w-20 rounded bg-[#3b3b46]"></div>

                                    </div>


                                    <div class="rounded-lg border border-[#292934] bg-[#1c1c25] p-3">

                                        <div class="h-5 w-5 rounded-md bg-[#6547e8]"></div>

                                        <div class="mt-3 h-2 w-14 rounded bg-gray-200"></div>

                                        <div class="mt-2 h-1.5 w-20 rounded bg-[#3b3b46]"></div>

                                    </div>


                                    <div class="rounded-lg border border-[#292934] bg-[#1c1c25] p-3">

                                        <div class="h-5 w-5 rounded-md bg-[#6547e8]"></div>

                                        <div class="mt-3 h-2 w-14 rounded bg-gray-200"></div>

                                        <div class="mt-2 h-1.5 w-20 rounded bg-[#3b3b46]"></div>

                                    </div>

                                </div>


                                <!-- Chart -->
                                <div class="mt-4 h-[145px] rounded-lg border border-[#292934] bg-[#1b1b23] p-4">

                                    <div class="mb-5 h-1.5 w-16 rounded bg-[#777783]"></div>

                                    <div class="flex h-20 items-end gap-2">

                                        <div class="h-[35%] flex-1 rounded-t bg-gradient-to-t from-[#5132db] to-[#8b70ff]"></div>

                                        <div class="h-[55%] flex-1 rounded-t bg-gradient-to-t from-[#5132db] to-[#8b70ff]"></div>

                                        <div class="h-[42%] flex-1 rounded-t bg-gradient-to-t from-[#5132db] to-[#8b70ff]"></div>

                                        <div class="h-[72%] flex-1 rounded-t bg-gradient-to-t from-[#5132db] to-[#8b70ff]"></div>

                                        <div class="h-[58%] flex-1 rounded-t bg-gradient-to-t from-[#5132db] to-[#8b70ff]"></div>

                                        <div class="h-[82%] flex-1 rounded-t bg-gradient-to-t from-[#5132db] to-[#8b70ff]"></div>

                                        <div class="h-[65%] flex-1 rounded-t bg-gradient-to-t from-[#5132db] to-[#8b70ff]"></div>

                                    </div>

                                </div>

                            </div>

                        </div>

                    </div>


                    <!-- Brand message -->
                    <div class="max-w-[620px]">

                        <h1 class="text-4xl font-extrabold leading-[1.08] tracking-tight xl:text-5xl">

                            Manage your business

                            <br />

                            <span class="text-[#c6b8ff]">
                                with confidence.
                            </span>

                        </h1>


                        <p class="mt-5 max-w-[560px] text-sm leading-7 text-white/75 xl:text-base">

                            One powerful POS platform for sales,
                            inventory, customers, payments and
                            day-to-day business operations.

                        </p>

                    </div>

                </div>

            </section>


            <!-- =====================================================
                 RIGHT LOGIN PANEL
                 ===================================================== -->
            <section
                class="flex min-h-screen items-center justify-center bg-white px-5 py-8 sm:px-10 lg:px-14 xl:px-20"
            >

                <div class="w-full max-w-[470px]">


                    <!-- Mobile logo -->
                    <div class="mb-12 flex items-center justify-center gap-3 lg:hidden">

                        <div
                            class="flex h-11 w-11 items-center justify-center rounded-xl bg-gradient-to-br from-[#5635df] to-[#7658ef] text-xs font-black text-white"
                        >
                            POS
                        </div>

                        <span class="text-sm font-extrabold tracking-[0.12em] text-[#18181d]">
                            POS SYSTEM
                        </span>

                    </div>


                    <!-- Heading -->
                    <div class="mb-9">

                        <h2 class="text-3xl font-extrabold tracking-tight text-[#111116] sm:text-[35px]">
                            Login to your account
                        </h2>

                        <p class="mt-3 text-sm leading-6 text-[#777781]">
                            Enter your credentials to access your POS terminal.
                        </p>

                    </div>


                    <!-- Login form -->
                    <form id="pos-login-form" class="space-y-6">


                        <!-- Username -->
                        <div>

                            <label
                                for="login-username"
                                class="mb-2 block text-[13px] font-bold text-[#1c1c21]"
                            >
                                Username
                                <span class="text-red-500">*</span>
                            </label>

                            <input
                                id="login-username"
                                name="username"
                                type="text"
                                autocomplete="username"
                                placeholder="Enter your username"
                                required
                                class="h-[50px] w-full rounded-[10px] border border-[#e3e3e6] bg-[#f0f0f2] px-4 text-sm text-[#17171b] outline-none transition placeholder:text-[#96969f] focus:border-[#6747e9] focus:bg-white focus:ring-4 focus:ring-[#6747e9]/10"
                            />

                        </div>


                        <!-- Password -->
                        <div>

                            <div class="mb-2 flex items-center justify-between">

                                <label
                                    for="login-password"
                                    class="text-[13px] font-bold text-[#1c1c21]"
                                >
                                    Password
                                    <span class="text-red-500">*</span>
                                </label>


                                <a
                                    href="#/forgot-password"
                                    class="text-xs font-bold text-[#1685d7] hover:underline"
                                >
                                    Forgot Password?
                                </a>

                            </div>


                            <div class="relative">

                                <input
                                    id="login-password"
                                    name="password"
                                    type="password"
                                    autocomplete="current-password"
                                    placeholder="Enter your password"
                                    required
                                    class="h-[50px] w-full rounded-[10px] border border-[#e3e3e6] bg-[#f0f0f2] px-4 pr-14 text-sm text-[#17171b] outline-none transition placeholder:text-[#96969f] focus:border-[#6747e9] focus:bg-white focus:ring-4 focus:ring-[#6747e9]/10"
                                />


                                <button
                                    type="button"
                                    id="toggle-login-password"
                                    aria-label="Show password"
                                    class="absolute right-2.5 top-1/2 flex h-9 w-9 -translate-y-1/2 items-center justify-center rounded-lg text-[#66666f] transition hover:bg-[#e5e5e8]"
                                >

                                    <svg
                                        width="19"
                                        height="19"
                                        viewBox="0 0 24 24"
                                        fill="none"
                                        stroke="currentColor"
                                        stroke-width="2"
                                        stroke-linecap="round"
                                        stroke-linejoin="round"
                                    >
                                        <path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12Z"></path>
                                        <circle cx="12" cy="12" r="3"></circle>
                                    </svg>

                                </button>

                            </div>

                        </div>


                        <!-- Error -->
                        <div
                            id="login-error"
                            class="min-h-5 text-sm font-semibold text-red-500"
                            role="alert"
                        ></div>


                        <!-- Login button -->
                        <button
                            type="submit"
                            id="login-submit"
                            class="group h-[51px] w-full rounded-[11px] bg-gradient-to-r from-[#17151e] to-[#08070b] text-sm font-bold text-white shadow-lg shadow-black/15 transition hover:-translate-y-[1px] hover:shadow-xl hover:shadow-black/20 disabled:cursor-not-allowed disabled:opacity-60 disabled:hover:translate-y-0"
                        >

                            <span id="login-submit-text">
                                Log in
                            </span>

                            <span
                                id="login-submit-loading"
                                class="hidden"
                            >
                                Signing in...
                            </span>

                        </button>

                    </form>


                    <!-- Security notice -->
                    <div
                        class="mt-6 flex items-start gap-2.5 rounded-[9px] bg-[#f7f7f9] px-3.5 py-3 text-[11px] leading-5 text-[#777781]"
                    >

                        <svg
                            class="mt-0.5 shrink-0 text-[#6747e9]"
                            width="17"
                            height="17"
                            viewBox="0 0 24 24"
                            fill="none"
                            stroke="currentColor"
                            stroke-width="2"
                            stroke-linecap="round"
                            stroke-linejoin="round"
                        >
                            <rect
                                width="18"
                                height="11"
                                x="3"
                                y="11"
                                rx="2"
                            ></rect>

                            <path d="M7 11V7a5 5 0 0 1 10 0v4"></path>
                        </svg>


                        <span>
                            Secure POS access. Your session is protected
                            by your organization's security policy.
                        </span>

                    </div>


                    <!-- Footer -->
                    <div class="mt-12 text-center text-[11px] text-[#9a9aa2]">

                        <p>
                            Authorized personnel only.
                        </p>

                        <div class="mt-2 flex justify-center gap-2">
                            <span>Privacy</span>
                            <span>•</span>
                            <span>Terms</span>
                        </div>

                    </div>

                </div>

            </section>

        </div>
    `;
}

export function initializeLogin() {
    const form = document.getElementById("pos-login-form");
    const usernameInput = document.getElementById("login-username");
    const passwordInput = document.getElementById("login-password");
    const togglePassword = document.getElementById("toggle-login-password");
    const errorElement = document.getElementById("login-error");
    const submitButton = document.getElementById("login-submit");
    const submitText = document.getElementById("login-submit-text");
    const loadingText = document.getElementById("login-submit-loading");
    if (!form || !usernameInput || !passwordInput || !errorElement || !submitButton) return;

    let challenge = null;
    let challengePanel = null;
    let passwordChangeMode = false;
    let expiredAccount = "";
    const usernameField = usernameInput.parentElement;
    const passwordField = passwordInput.closest(".relative")?.parentElement;

    const setBusy = (busy, label = "Signing in...") => {
        submitButton.disabled = busy;
        if (submitText) {
            submitText.textContent = label;
            submitText.classList.toggle("hidden", busy);
        }
        if (loadingText) {
            loadingText.textContent = busy ? label : "Signing in...";
            loadingText.classList.toggle("hidden", !busy);
        }
    };

    const showChallenge = (data) => {
        challenge = data;
        if (usernameField) usernameField.classList.add("hidden");
        if (passwordField) passwordField.classList.add("hidden");
        usernameInput.disabled = true;
        passwordInput.disabled = true;
        passwordInput.required = false;
        if (togglePassword) togglePassword.classList.add("hidden");
        if (challengePanel) challengePanel.remove();
        challengePanel = document.createElement("div");
        challengePanel.id = "login-otp-panel";
        challengePanel.className = "space-y-4 rounded-xl border border-[#e8e4fb] bg-[#faf9ff] p-4";
        const title = data.requires_device_authorization ? "Authorize this device" : "Two-factor verification";
        const detail = data.message || "Enter the verification code sent to your registered contact method.";
        challengePanel.innerHTML = `
            <div>
                <h3 class="text-base font-extrabold text-[#17151e]">${title}</h3>
                <p id="otp-challenge-message" class="mt-1 text-sm leading-6 text-[#777781]"></p>
            </div>
            <label for="login-otp-code" class="block text-[13px] font-bold text-[#1c1c21]">6-digit verification code</label>
            <input id="login-otp-code" name="otp" type="text" inputmode="numeric" autocomplete="one-time-code" pattern="[0-9]{6}" maxlength="6" required placeholder="000000" class="h-[52px] w-full rounded-[10px] border border-[#ded9f7] bg-white px-4 text-center text-xl font-bold tracking-[0.45em] text-[#17171b] outline-none focus:border-[#6747e9] focus:ring-4 focus:ring-[#6747e9]/10" />
            <div class="flex items-center justify-between gap-3 text-xs">
                <button type="button" id="otp-resend" class="font-bold text-[#6747e9] hover:underline">Resend code</button>
                <button type="button" id="otp-back" class="font-semibold text-[#777781] hover:text-[#17151e]">Back to login</button>
            </div>`;
        errorElement.before(challengePanel);
        const messageEl = challengePanel.querySelector("#otp-challenge-message");
        messageEl.textContent = detail;
        submitText.textContent = "Verify code";
        loadingText.textContent = "Verifying...";
        challengePanel.querySelector("#otp-back").addEventListener("click", () => {
            challenge = null;
            challengePanel?.remove();
            challengePanel = null;
            if (usernameField) usernameField.classList.remove("hidden");
            if (passwordField) passwordField.classList.remove("hidden");
            usernameInput.disabled = false;
            passwordInput.disabled = false;
            passwordInput.required = true;
            if (togglePassword) togglePassword.classList.remove("hidden");
            submitText.textContent = "Log in";
            errorElement.textContent = "";
        });
        challengePanel.querySelector("#otp-resend").addEventListener("click", async (event) => {
            const button = event.currentTarget;
            button.disabled = true;
            errorElement.textContent = "";
            try {
                const { resendOTP, challengeAccount } = await import("../services/auth.js");
                const result = await resendOTP({ username: challengeAccount(data, usernameInput.value), deviceId: data.device_id });
                messageEl.textContent = result.message || "A new verification code has been requested.";
            } catch (error) {
                errorElement.textContent = error.message || "Unable to resend the code.";
            } finally {
                button.disabled = false;
            }
        });
        challengePanel.querySelector("#login-otp-code")?.focus();
    };

    const showExpiredPasswordChange = () => {
        passwordChangeMode = true;
        if (challengePanel) challengePanel.remove();
        challengePanel = document.createElement("div");
        challengePanel.id = "expired-password-panel";
        challengePanel.className = "space-y-4 rounded-xl border border-amber-200 bg-amber-50 p-4";
        challengePanel.innerHTML = `
          <div><h3 class="text-base font-extrabold text-slate-900">Password expired</h3>
          <p class="mt-1 text-sm leading-6 text-slate-600">Choose a new password to continue. You will need to sign in again after changing it.</p></div>
          <div><label for="expired-new-password" class="mb-2 block text-sm font-semibold text-slate-800">New password</label>
          <input id="expired-new-password" type="password" autocomplete="new-password" required class="h-12 w-full rounded-xl border border-slate-200 bg-white px-4 text-sm outline-none focus:border-violet-500 focus:ring-4 focus:ring-violet-500/10" placeholder="Enter a new password" /></div>
          <div><label for="expired-confirm-password" class="mb-2 block text-sm font-semibold text-slate-800">Confirm new password</label>
          <input id="expired-confirm-password" type="password" autocomplete="new-password" required class="h-12 w-full rounded-xl border border-slate-200 bg-white px-4 text-sm outline-none focus:border-violet-500 focus:ring-4 focus:ring-violet-500/10" placeholder="Confirm new password" /></div>`;
        errorElement.before(challengePanel);
        if (usernameField) usernameField.classList.add("hidden");
        usernameInput.disabled = true;
        passwordInput.autocomplete = "current-password";
        const passwordLabel = form.querySelector('label[for="login-password"]');
        if (passwordLabel) passwordLabel.textContent = "Current password";
        submitText.textContent = "Update password";
        challengePanel.querySelector("#expired-new-password")?.focus();
    };

    togglePassword?.addEventListener("click", () => {
        const showing = passwordInput.type === "text";
        passwordInput.type = showing ? "password" : "text";
        togglePassword.setAttribute("aria-label", showing ? "Show password" : "Hide password");
    });

    form.addEventListener("submit", async (event) => {
        event.preventDefault();
        errorElement.textContent = "";
        const username = usernameInput.value.trim();
        if (!username) {
            errorElement.textContent = "Please enter your username.";
            return;
        }
        if (!challenge && !passwordInput.value) {
            errorElement.textContent = "Please enter your password.";
            return;
        }
        setBusy(true, challenge ? "Verifying..." : "Signing in...");
        try {
            const auth = await import("../services/auth.js");
            let data;
            if (passwordChangeMode) {
                const newPassword = challengePanel?.querySelector("#expired-new-password")?.value || "";
                const confirmPassword = challengePanel?.querySelector("#expired-confirm-password")?.value || "";
                if (newPassword.length < 8) throw new Error("New password must contain at least 8 characters.");
                if (newPassword !== confirmPassword) throw new Error("The new passwords do not match.");
                data = await auth.changeExpiredPassword({ username: expiredAccount || username, oldPassword: passwordInput.value, newPassword });
                challengePanel?.remove();
                challengePanel = null;
                passwordChangeMode = false;
                if (usernameField) usernameField.classList.remove("hidden");
                usernameInput.disabled = false;
                passwordInput.value = "";
                passwordInput.autocomplete = "current-password";
                const passwordLabel = form.querySelector('label[for="login-password"]');
                if (passwordLabel) passwordLabel.textContent = "Password *";
                errorElement.className = "min-h-5 text-sm font-semibold text-emerald-600";
                errorElement.textContent = data.message || "Password updated. Please sign in with your new password.";
                submitText.textContent = "Log in";
                return;
            } else if (challenge) {
                const code = challengePanel?.querySelector("#login-otp-code")?.value.trim() || "";
                if (!/^[0-9]{6}$/.test(code)) throw new Error("Enter the 6-digit verification code.");
                data = await auth.verifyOTP({ username: auth.challengeAccount(challenge, username), code, deviceId: challenge.device_id });
            } else {
                data = await auth.login({ username, password: passwordInput.value });
            }

            if (data?.requires_2fa || data?.requires_device_authorization) {
                showChallenge(data);
                setBusy(false, "Verify code");
                return;
            }
            auth.saveAuthenticatedSession(data);
            window.location.hash = "#/dashboard";
        } catch (error) {
            console.error("AUTHENTICATION ERROR:", error);
            const data = error?.data;
            if (data?.password_expired && !passwordChangeMode) {
                const { challengeAccount } = await import("../services/auth.js");
                expiredAccount = challengeAccount(data, username);
                showExpiredPasswordChange();
                errorElement.textContent = "";
            } else {
                errorElement.className = "min-h-5 text-sm font-semibold text-red-500";
                errorElement.textContent = error?.message || "Unable to sign in. Please try again.";
            }
        } finally {
            setBusy(false, passwordChangeMode ? "Update password" : challenge ? "Verify code" : "Log in");
        }
    });
}
