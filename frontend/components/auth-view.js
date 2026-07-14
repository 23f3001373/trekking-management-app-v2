const AuthView = {
  props: ['app'],
  template: `
    <div id="auth-container">

      <div v-if="app.activeAuthView === 'login'" class="auth-card animate-in">
        <div class="auth-mountain-header">
          <div style="width: 68px; height: 68px; overflow: hidden; border-radius: 50%; display: inline-flex; align-items: center; justify-content: center; margin-bottom: 0.75rem; box-shadow: var(--trek-shadow-sm); background: rgba(255, 255, 255, 0.06); backdrop-filter: blur(12px); border: 1px solid rgba(255, 255, 255, 0.12);">
            <img src="assets/icon-192.png" style="width: 100%; height: 100%; object-fit: cover; transform: scale(1.65);" alt="TrekVista Logo" />
          </div>
          <h1 class="auth-title">TrekVista</h1>
          <p class="auth-subtitle">Sign in to your account</p>
        </div>

        <form id="login-form" @submit.prevent="app.handleUserLoginSubmission" novalidate>
          <div class="mb-3">
            <label for="login-email" class="form-label">Email Address</label>
            <div class="input-group">
              <span class="input-group-text" style="background:var(--trek-surface);border-color:rgba(76,175,80,0.2);color:var(--trek-muted);">
                <i class="bi bi-envelope"></i>
              </span>
              <input id="login-email" type="email" class="form-control" :class="{ 'is-invalid': app.loginFormErrors.email }" v-model="app.loginFormData.user_email_address" placeholder="your@email.com" autocomplete="email" required />
              <div class="invalid-feedback">{{ app.loginFormErrors.email }}</div>
            </div>
          </div>

          <div class="mb-4">
            <label for="login-password" class="form-label">Password</label>
            <div class="input-group">
              <span class="input-group-text" style="background:var(--trek-surface);border-color:rgba(76,175,80,0.2);color:var(--trek-muted);">
                <i class="bi bi-lock"></i>
              </span>
              <input id="login-password" :type="app.loginPasswordVisible ? 'text' : 'password'" class="form-control" :class="{ 'is-invalid': app.loginFormErrors.password }" v-model="app.loginFormData.submitted_password" placeholder="Enter password" autocomplete="current-password" required />
              <button type="button" class="input-group-text" style="background:var(--trek-surface);border-color:rgba(76,175,80,0.2);color:var(--trek-muted);cursor:pointer;" @click="app.loginPasswordVisible = !app.loginPasswordVisible" tabindex="-1">
                <i :class="app.loginPasswordVisible ? 'bi bi-eye-slash' : 'bi bi-eye'"></i>
              </button>
              <div class="invalid-feedback">{{ app.loginFormErrors.password }}</div>
            </div>
          </div>

          <div v-if="app.loginApiError" class="alert alert-danger py-2 mb-3" style="background:rgba(239,83,80,0.1);border-color:rgba(239,83,80,0.3);color:#ef9a9a;border-radius:8px;font-size:0.85rem;">
            <i class="bi bi-exclamation-triangle me-2"></i>{{ app.loginApiError }}
          </div>

          <div class="d-flex gap-2">
            <button type="submit" class="btn btn-trek-primary flex-fill py-2" :disabled="app.loginSubmitting">
              <span v-if="app.loginSubmitting">
                <span class="spinner-border spinner-border-sm me-2"></span>Signing in...
              </span>
              <span v-else>
                <i class="bi bi-box-arrow-in-right me-2"></i>Sign In
              </span>
            </button>
            <button type="button" class="btn btn-trek-outline py-2" style="border-color:rgba(255,255,255,0.15);color:var(--trek-text-secondary);" @click="app.loginFormData = { user_email_address: '', submitted_password: '' }; app.loginFormErrors = {}; app.loginApiError = '';" :disabled="app.loginSubmitting" title="Clear form">
              <i class="bi bi-eraser-fill me-1"></i>Clear
            </button>
          </div>
        </form>

        <hr class="divider-glow" />

        <p class="text-center mb-0" style="font-size:0.88rem;color:var(--trek-text-muted);">
          New trekker?
          <a href="#" @click.prevent="app.activeAuthView = 'register'" class="text-trek-primary fw-600">Create your account</a>
        </p>
      </div>

      <div v-if="app.activeAuthView === 'register'" class="auth-card animate-in" style="max-width:480px;">
        <div class="auth-mountain-header">
          <div style="width: 68px; height: 68px; overflow: hidden; border-radius: 50%; display: inline-flex; align-items: center; justify-content: center; margin-bottom: 0.75rem; box-shadow: var(--trek-shadow-sm); background: rgba(255, 255, 255, 0.06); backdrop-filter: blur(12px); border: 1px solid rgba(255, 255, 255, 0.12); font-size: 2.2rem;">
            🏕️
          </div>
          <h1 class="auth-title">Join TrekVista</h1>
          <p class="auth-subtitle">Create your account</p>
        </div>

        <form id="register-form" @submit.prevent="app.handleTrekkerRegistrationSubmission" novalidate>
          <div class="mb-3">
            <label for="reg-name" class="form-label">Full Name</label>
            <input id="reg-name" type="text" class="form-control" :class="{ 'is-invalid': app.registrationFormErrors.user_full_name }" v-model="app.registrationFormData.user_full_name" placeholder="Your full name" autocomplete="name" />
            <div class="invalid-feedback">{{ app.registrationFormErrors.user_full_name }}</div>
          </div>

          <div class="mb-3">
            <label for="reg-email" class="form-label">Email Address</label>
            <input id="reg-email" type="email" class="form-control" :class="{ 'is-invalid': app.registrationFormErrors.user_email_address, 'is-valid': app.registrationEmailChecked && !app.registrationFormErrors.user_email_address }" v-model="app.registrationFormData.user_email_address" placeholder="your@email.com" autocomplete="email" />
            <div class="invalid-feedback">{{ app.registrationFormErrors.user_email_address }}</div>
          </div>

          <div class="mb-3">
            <label for="reg-phone" class="form-label">Phone Number <span style="color:var(--trek-text-muted);font-weight:400;">(optional)</span></label>
            <input id="reg-phone" type="tel" class="form-control" :class="{ 'is-invalid': app.registrationFormErrors.user_contact_phone_number }" v-model="app.registrationFormData.user_contact_phone_number" placeholder="+91 98765 43210" />
            <div class="invalid-feedback">{{ app.registrationFormErrors.user_contact_phone_number }}</div>
          </div>

          <div class="mb-4">
            <label for="reg-password" class="form-label">Password</label>
            <div class="input-group">
              <input id="reg-password" :type="app.registerPasswordVisible ? 'text' : 'password'" class="form-control" :class="{ 'is-invalid': app.registrationFormErrors.raw_password }" v-model="app.registrationFormData.raw_password" placeholder="Min 8 chars, uppercase, digit, special" autocomplete="new-password" />
              <button type="button" class="input-group-text" style="background:var(--trek-surface);border-color:rgba(76,175,80,0.2);color:var(--trek-muted);cursor:pointer;" @click="app.registerPasswordVisible = !app.registerPasswordVisible" tabindex="-1">
                <i :class="app.registerPasswordVisible ? 'bi bi-eye-slash' : 'bi bi-eye'"></i>
              </button>
            </div>
            <div v-if="app.registrationFormData.raw_password" class="mt-2">
              <div class="password-strength-bar">
                <div class="password-strength-fill" :class="app.passwordStrengthClass"></div>
              </div>
              <div class="password-strength-label" :style="{ color: app.passwordStrengthColor }">
                {{ app.passwordStrengthLabel }}
              </div>
            </div>
            <div class="invalid-feedback d-block" v-if="app.registrationFormErrors.raw_password">
              {{ app.registrationFormErrors.raw_password }}
            </div>
          </div>

          <div v-if="app.registrationApiError" class="alert alert-danger py-2 mb-3" style="background:rgba(239,83,80,0.1);border-color:rgba(239,83,80,0.3);color:#ef9a9a;border-radius:8px;font-size:0.85rem;">
            <i class="bi bi-exclamation-triangle me-2"></i>{{ app.registrationApiError }}
          </div>

          <div class="d-flex gap-2">
            <button type="submit" class="btn btn-trek-primary flex-fill py-2" :disabled="app.registrationSubmitting">
              <span v-if="app.registrationSubmitting">
                <span class="spinner-border spinner-border-sm me-2"></span>Creating account...
              </span>
              <span v-else>
                <i class="bi bi-person-plus me-2"></i>Create Account
              </span>
            </button>
            <button type="button" class="btn btn-trek-outline py-2" style="border-color:rgba(255,255,255,0.15);color:var(--trek-text-secondary);" @click="app.registrationFormData = { user_full_name: '', user_email_address: '', user_contact_phone_number: '', raw_password: '' }; app.registrationFormErrors = {}; app.registrationApiError = '';" :disabled="app.registrationSubmitting" title="Clear form">
              <i class="bi bi-eraser-fill me-1"></i>Clear
            </button>
          </div>
        </form>

        <hr class="divider-glow" />
        <p class="text-center mb-0" style="font-size:0.88rem;color:var(--trek-text-muted);">
          Already have an account?
          <a href="#" @click.prevent="app.activeAuthView = 'login'" class="text-trek-primary fw-600">Sign in</a>
        </p>
      </div>

    </div>
  `
};
