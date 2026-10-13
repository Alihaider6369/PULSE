window.getPulseApiUrl = function(endpoint) {
  const base = (window.PULSE_API_URL || "").trim().replace(/\/+$/, "");
  if (!base) return endpoint;
  const path = endpoint.startsWith("/") ? endpoint : `/${endpoint}`;
  return `${base}${path}`;
};

/**
 * Shared Authentication Manager for PULSE Web Dashboard
 */
const Auth = {
  getToken() {
    return localStorage.getItem("pulse_token") || null;
  },

  getUser() {
    try {
      const u = localStorage.getItem("pulse_user");
      return u ? JSON.parse(u) : null;
    } catch {
      return null;
    }
  },

  setSession(token, user) {
    localStorage.setItem("pulse_token", token);
    localStorage.setItem("pulse_user", JSON.stringify(user));
    this.renderHeader();
  },

  clearSession() {
    localStorage.removeItem("pulse_token");
    localStorage.removeItem("pulse_user");
    const logoutUrl = window.getPulseApiUrl("/api/auth/logout");
    fetch(logoutUrl, { method: "POST" }).catch(() => {});
    this.renderHeader();
  },

  async authFetch(url, options = {}) {
    const fullUrl = window.getPulseApiUrl(url);
    const headers = options.headers || {};
    const token = this.getToken();
    if (token) {
      headers["Authorization"] = `Bearer ${token}`;
    }
    options.headers = headers;
    const res = await fetch(fullUrl, options);
    if (res.status === 401) {
      this.clearSession();
    }
    return res;
  },

  init() {
    this.injectAuthModal();
    this.renderHeader();
  },

  renderHeader() {
    const user = this.getUser();
    let authContainer = document.getElementById("auth-header-container");
    if (!authContainer) {
      const header = document.querySelector("header");
      if (!header) return;
      authContainer = document.createElement("div");
      authContainer.id = "auth-header-container";
      authContainer.style.display = "flex";
      authContainer.style.alignItems = "center";
      authContainer.style.gap = "12px";
      header.appendChild(authContainer);
    }

    if (user) {
      authContainer.innerHTML = `
        <span class="user-email-text" style="font-size: 13px; font-weight: 700; color: #ffffff; text-shadow: 0 1px 2px rgba(0,0,0,0.35); display: inline-flex; align-items: center; gap: 6px;">
          <svg class="user-icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#ffffff" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="display: inline-block; vertical-align: middle; flex-shrink: 0; filter: drop-shadow(0 1px 2px rgba(0,0,0,0.35));"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>
          <span>${user.email}</span>
        </span>
        <button id="btn-logout" class="btn-logout" style="background: #ffffff; border: 1px solid #000000; color: #000000; font-weight: 700; border-radius: 6px; padding: 6px 14px; font-size: 12px; cursor: pointer; white-space: nowrap; display: inline-flex; align-items: center; justify-content: center; box-sizing: border-box; line-height: 1.2;">Log Out</button>
      `;
      document.getElementById("btn-logout").onclick = () => {
        this.clearSession();
        window.location.reload();
      };
    } else {
      authContainer.innerHTML = `
        <button id="btn-login-open" style="background: #6366f1; border: none; color: #fff; border-radius: 6px; padding: 6px 14px; font-size: 13px; font-weight: 600; cursor: pointer;">Sign In</button>
      `;
      document.getElementById("btn-login-open").onclick = () => {
        this.openModal();
      };
    }
  },

  injectAuthModal() {
    if (document.getElementById("pulse-auth-modal")) return;

    const modal = document.createElement("div");
    modal.id = "pulse-auth-modal";
    modal.style.display = "none";
    modal.style.position = "fixed";
    modal.style.top = "0";
    modal.style.left = "0";
    modal.style.width = "100%";
    modal.style.height = "100%";
    modal.style.backgroundColor = "rgba(15, 23, 42, 0.75)";
    modal.style.zIndex = "9999";
    modal.style.justifyContent = "center";
    modal.style.alignItems = "center";

    modal.innerHTML = `
      <div style="background: #1e293b; border: 1px solid #334155; border-radius: 12px; padding: 28px; width: 380px; box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.5); color: #f8fafc; font-family: system-ui, sans-serif;">
        <h2 id="modal-title" style="margin-top: 0; font-size: 20px;">Sign in to PULSE</h2>
        <p id="modal-subtitle" style="font-size: 12px; color: #94a3b8; margin-bottom: 18px;">Access your private ergonomic history and sync telemetry.</p>
        
        <div id="signup-name-field" style="display: none; margin-bottom: 12px;">
          <label style="font-size: 12px; color: #94a3b8; display: block; margin-bottom: 4px;">Full Name</label>
          <input type="text" id="auth-name" style="width: 100%; box-sizing: border-box; background: #0f172a; border: 1px solid #475569; border-radius: 6px; padding: 8px 10px; color: #fff;">
        </div>

        <div id="email-field" style="margin-bottom: 12px;">
          <label style="font-size: 12px; color: #94a3b8; display: block; margin-bottom: 4px;">Email Address</label>
          <input type="email" id="auth-email" style="width: 100%; box-sizing: border-box; background: #0f172a; border: 1px solid #475569; border-radius: 6px; padding: 8px 10px; color: #fff;">
        </div>

        <div id="password-field" style="margin-bottom: 12px;">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
            <label style="font-size: 12px; color: #94a3b8;">Password</label>
            <a href="#" id="btn-forgot-password" style="font-size: 11px; color: #818cf8; text-decoration: none;">Forgot password?</a>
          </div>
          <input type="password" id="auth-password" style="width: 100%; box-sizing: border-box; background: #0f172a; border: 1px solid #475569; border-radius: 6px; padding: 8px 10px; color: #fff;">
        </div>

        <div id="auth-error-msg" style="color: #ef4444; font-size: 12px; margin-bottom: 12px; min-height: 16px;"></div>

        <button id="btn-auth-submit" style="width: 100%; background: #6366f1; border: none; color: #fff; padding: 10px; border-radius: 6px; font-weight: 600; cursor: pointer; margin-bottom: 12px;">Sign In</button>
        
        <div style="display: flex; justify-content: space-between; font-size: 12px;">
          <a href="#" id="btn-toggle-auth-mode" style="color: #6366f1; text-decoration: none;">Don't have an account? Sign up</a>
          <a href="#" id="btn-close-auth-modal" style="color: #94a3b8; text-decoration: none;">Cancel</a>
        </div>
      </div>
    `;

    document.body.appendChild(modal);

    let authMode = "login"; // "login", "signup", "forgot"
    const toggleBtn = document.getElementById("btn-toggle-auth-mode");
    const forgotBtn = document.getElementById("btn-forgot-password");
    const nameField = document.getElementById("signup-name-field");
    const passwordField = document.getElementById("password-field");
    const title = document.getElementById("modal-title");
    const subtitle = document.getElementById("modal-subtitle");
    const submitBtn = document.getElementById("btn-auth-submit");
    const errorMsg = document.getElementById("auth-error-msg");

    const emailRegex = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

    function setMode(mode) {
      authMode = mode;
      errorMsg.textContent = "";
      errorMsg.style.color = "#ef4444";
      if (mode === "signup") {
        title.textContent = "Create an Account";
        subtitle.textContent = "Start tracking your posture habits privately.";
        submitBtn.textContent = "Register & Sign In";
        nameField.style.display = "block";
        passwordField.style.display = "block";
        forgotBtn.style.display = "none";
        toggleBtn.textContent = "Already registered? Sign in";
      } else if (mode === "forgot") {
        title.textContent = "Reset Password";
        subtitle.textContent = "Enter your email address to receive a password reset link.";
        submitBtn.textContent = "Send Reset Link";
        nameField.style.display = "none";
        passwordField.style.display = "none";
        toggleBtn.textContent = "Remembered password? Sign in";
      } else {
        authMode = "login";
        title.textContent = "Sign in to PULSE";
        subtitle.textContent = "Access your private ergonomic history and sync telemetry.";
        submitBtn.textContent = "Sign In";
        nameField.style.display = "none";
        passwordField.style.display = "block";
        forgotBtn.style.display = "inline";
        toggleBtn.textContent = "Don't have an account? Sign up";
      }
    }

    toggleBtn.onclick = (e) => {
      e.preventDefault();
      if (authMode === "login") {
        setMode("signup");
      } else {
        setMode("login");
      }
    };

    forgotBtn.onclick = (e) => {
      e.preventDefault();
      setMode("forgot");
    };

    document.getElementById("btn-close-auth-modal").onclick = (e) => {
      e.preventDefault();
      modal.style.display = "none";
    };

    submitBtn.onclick = async () => {
      const email = document.getElementById("auth-email").value.trim();
      const password = document.getElementById("auth-password").value.trim();
      errorMsg.textContent = "";
      errorMsg.style.color = "#ef4444";

      // 1. Client-side email format validation
      if (!email || !emailRegex.test(email)) {
        errorMsg.textContent = "Enter a valid email address";
        return;
      }

      // Handle Forgot Password
      if (authMode === "forgot") {
        try {
          submitBtn.disabled = true;
          submitBtn.textContent = "Sending...";
          const res = await fetch(window.getPulseApiUrl("/api/auth/forgot-password"), {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ email }),
          });
          const data = await res.json();
          errorMsg.style.color = "#10b981";
          errorMsg.textContent = data.message || "If this email is registered, a password reset link has been sent.";
          submitBtn.disabled = false;
          submitBtn.textContent = "Send Reset Link";
        } catch (err) {
          errorMsg.style.color = "#ef4444";
          errorMsg.textContent = "Connection error. Is backend running?";
          submitBtn.disabled = false;
          submitBtn.textContent = "Send Reset Link";
        }
        return;
      }

      // Handle Login and Signup
      if (!password) {
        errorMsg.textContent = "Password is required.";
        return;
      }
      if (password.length < 8) {
        errorMsg.textContent = "Password must be at least 8 characters long";
        return;
      }

      const endpoint = authMode === "signup" ? "/api/auth/signup" : "/api/auth/login";
      const payload = { email, password };
      if (authMode === "signup") {
        payload.full_name = document.getElementById("auth-name").value.trim() || null;
      }

      try {
        const res = await fetch(window.getPulseApiUrl(endpoint), {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        const data = await res.json();
        if (!res.ok) {
          errorMsg.textContent = data.detail || "Authentication failed.";
          return;
        }

        Auth.setSession(data.access_token, data.user);
        modal.style.display = "none";
        window.location.reload();
      } catch (err) {
        errorMsg.textContent = "Connection error. Is backend running?";
      }
    };
  },

  openModal() {
    const modal = document.getElementById("pulse-auth-modal");
    if (modal) modal.style.display = "flex";
  },
};

document.addEventListener("DOMContentLoaded", () => {
  Auth.init();
});
