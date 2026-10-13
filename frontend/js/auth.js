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
    fetch("/api/auth/logout", { method: "POST" }).catch(() => {});
    this.renderHeader();
  },

  async authFetch(url, options = {}) {
    const headers = options.headers || {};
    const token = this.getToken();
    if (token) {
      headers["Authorization"] = `Bearer ${token}`;
    }
    options.headers = headers;
    const res = await fetch(url, options);
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
        <span style="font-size: 13px; font-weight: 500; color: #10b981;">👤 ${user.email}</span>
        <button id="btn-logout" style="background: rgba(239, 68, 68, 0.15); border: 1px solid #ef4444; color: #ef4444; border-radius: 6px; padding: 4px 10px; font-size: 12px; cursor: pointer;">Log Out</button>
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
        <p style="font-size: 12px; color: #94a3b8; margin-bottom: 18px;">Access your private ergonomic history and sync telemetry.</p>
        
        <div id="signup-name-field" style="display: none; margin-bottom: 12px;">
          <label style="font-size: 12px; color: #94a3b8; display: block; margin-bottom: 4px;">Full Name</label>
          <input type="text" id="auth-name" style="width: 100%; box-sizing: border-box; background: #0f172a; border: 1px solid #475569; border-radius: 6px; padding: 8px 10px; color: #fff;">
        </div>

        <div style="margin-bottom: 12px;">
          <label style="font-size: 12px; color: #94a3b8; display: block; margin-bottom: 4px;">Email Address</label>
          <input type="email" id="auth-email" style="width: 100%; box-sizing: border-box; background: #0f172a; border: 1px solid #475569; border-radius: 6px; padding: 8px 10px; color: #fff;">
        </div>

        <div style="margin-bottom: 16px;">
          <label style="font-size: 12px; color: #94a3b8; display: block; margin-bottom: 4px;">Password</label>
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

    let isSignup = false;
    const toggleBtn = document.getElementById("btn-toggle-auth-mode");
    const nameField = document.getElementById("signup-name-field");
    const title = document.getElementById("modal-title");
    const submitBtn = document.getElementById("btn-auth-submit");
    const errorMsg = document.getElementById("auth-error-msg");

    toggleBtn.onclick = (e) => {
      e.preventDefault();
      isSignup = !isSignup;
      errorMsg.textContent = "";
      if (isSignup) {
        title.textContent = "Create an Account";
        submitBtn.textContent = "Register & Sign In";
        nameField.style.display = "block";
        toggleBtn.textContent = "Already registered? Sign in";
      } else {
        title.textContent = "Sign in to PULSE";
        submitBtn.textContent = "Sign In";
        nameField.style.display = "none";
        toggleBtn.textContent = "Don't have an account? Sign up";
      }
    };

    document.getElementById("btn-close-auth-modal").onclick = (e) => {
      e.preventDefault();
      modal.style.display = "none";
    };

    submitBtn.onclick = async () => {
      const email = document.getElementById("auth-email").value.trim();
      const password = document.getElementById("auth-password").value.trim();
      errorMsg.textContent = "";

      if (!email || !password) {
        errorMsg.textContent = "Email and password are required.";
        return;
      }
      if (password.length < 8) {
        errorMsg.textContent = "Password must be at least 8 characters.";
        return;
      }

      const endpoint = isSignup ? "/api/auth/signup" : "/api/auth/login";
      const payload = { email, password };
      if (isSignup) {
        payload.full_name = document.getElementById("auth-name").value.trim() || null;
      }

      try {
        const res = await fetch(endpoint, {
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
