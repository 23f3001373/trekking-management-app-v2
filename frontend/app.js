

const { createApp } = Vue;

const TREK_PLATFORM_API_BASE_URL = 'http://127.0.0.1:5000/api';

const REFRESH_TOKEN_STORAGE_KEY = 'trek_platform_refresh_token_v2';

const SEARCH_DEBOUNCE_DELAY_MS = 400;

const CHART_COLOR_PALETTE = {
  green:   'rgba(76, 175, 80, 0.8)',
  sage:    'rgba(129, 199, 132, 0.8)',
  gold:    'rgba(255, 213, 79, 0.8)',
  amber:   'rgba(255, 143, 0, 0.8)',
  blue:    'rgba(41, 182, 246, 0.8)',
  red:     'rgba(239, 83, 80, 0.8)',
  purple:  'rgba(171, 71, 188, 0.8)',
  teal:    'rgba(38, 198, 218, 0.8)',
};

// call api

createApp({

  data() {
    return {
      globalLoadingState: false,
      globalLoadingMessage: '',

      authenticatedUserSession: null,
      inMemoryAccessToken: null,
      activeAuthView: 'login',

      currentView: 'admin-dashboard',
      sidebarOpen: false,

      _toastIdCounter: 0,

      loginFormData: {
        user_email_address: '',
        submitted_password: '',
      },
      loginFormErrors: {},
      loginApiError: '',
      loginSubmitting: false,
      loginPasswordVisible: false,

      registrationFormData: {
        user_full_name: '',
        user_email_address: '',
        user_contact_phone_number: '',
        raw_password: '',
      },
      registrationFormErrors: {},
      registrationApiError: '',
      registrationSubmitting: false,
      registrationEmailChecked: false,
      registerPasswordVisible: false,

      adminDashboardMetrics: [],
      adminRecentExpeditions: [],

      adminAllExpeditions: [],
      adminExpeditionsStatusFilter: '',
      adminExpeditionsPage: 1,
      adminExpeditionsPagination: { current_page: 1, total_pages: 1, total_expedition_count: 0, has_next_page: false, has_previous_page: false },

      adminAllUsers: [],
      userSearchKeyword: '',
      userRoleFilter: '',
      _userSearchDebounceTimer: null,

      expeditionFormData: {
        expedition_route_name: '',
        expedition_geographical_location: '',
        expedition_difficulty_level: '',
        expedition_duration_in_days: 5,
        expedition_price_per_person_inr: 0,
        total_participant_slots_capacity: 20,
        expedition_scheduled_start_date: '',
        expedition_scheduled_end_date: '',
        expedition_booking_cutoff_date: '',
        assigned_staff_leader_id: null,
        expedition_cover_image_url: '',
        expedition_meeting_point_address: '',
        expedition_detailed_description: '',
      },
      expeditionFormErrors: {},
      expeditionFormApiError: '',
      expeditionFormSubmitting: false,
      coverImageUploading: false,

      adminEditingExpedition: null,
      editExpeditionSubmitting: false,

      expeditionToDelete: null,
      deleteSubmitting: false,

      staffFormData: {
        user_full_name: '',
        user_email_address: '',
        user_contact_phone_number: '',
        raw_password: '',
      },
      staffFormErrors: {},
      staffFormApiError: '',
      staffFormSubmitting: false,
      allStaffAccounts: [],

      expeditionStatuses: ['Pending', 'Approved', 'Open', 'Closed', 'Completed', 'Cancelled'],

      staffDashboardSummary: null,
      staffOpenExpeditions: [],
      staffAllAssignedExpeditions: [],
      staffExpeditionsFilter: '',

      staffManagingExpedition: null,
      staffUpdatePayload: {
        current_expedition_lifecycle_status: null,
        available_participant_slots_remaining: null,
      },
      staffUpdateSubmitting: false,

      trekkerOpenExpeditions: [],
      expeditionsLoading: false,
      trekFilterParams: {
        difficulty_level_filter: '',
        geographical_location_keyword: '',
        maximum_price_inr: null,
        maximum_duration_days: null,
      },
      openTreksPagination: { current_page: 1, total_pages: 1, total_open_expedition_count: 0, has_next_page: false },
      _trekSearchDebounceTimer: null,

      trekkerAllBookings: [],
      trekkerUpcomingBookings: [],
      bookingStatusFilter: '',
      trekkerStats: { totalBookings: 0, completedTreks: 0, upcomingTreks: 0, cancelledTreks: 0 },

      selectedExpeditionForBooking: null,
      bookingParticipants: 1,
      bookingSpecialNote: '',
      bookingStep: 1,
      bookingModalInstance: null,

      selectedBookingForCancellation: null,
      cancellationReason: '',
      cancellationSubmitting: false,
      cancelBookingModalInstance: null,

      csvExportLoading: false,

      expeditionParticipants: [],
      participantsLoading: false,
      participantsModalInstance: null,

      profileFormData: {
        user_full_name: '',
        user_contact_phone_number: '',
        user_profile_bio_summary: '',
        user_emergency_contact_name: '',
        user_emergency_contact_phone: '',
      },
      profileUpdateSubmitting: false,
      passwordChangeData: { current_password: '', new_password: '' },
      passwordChangeErrors: {},
      passwordChangeSubmitting: false,

      _chartInstances: {},
    };
  },

  // update ui state
  computed: {
    
    userInitials() {
      if (!this.authenticatedUserSession?.user_full_name) return '??';
      const name_parts = this.authenticatedUserSession.user_full_name.trim().split(' ');
      if (name_parts.length >= 2) {
        return (name_parts[0][0] + name_parts[name_parts.length - 1][0]).toUpperCase();
      }
      return name_parts[0].slice(0, 2).toUpperCase();
    },

    
    passwordStrength() {
      const pwd = this.registrationFormData.raw_password;
      if (!pwd) return '';
      let score = 0;
      if (pwd.length >= 8) score++;
      if (pwd.length >= 12) score++;
      if (/[A-Z]/.test(pwd)) score++;
      if (/[0-9]/.test(pwd)) score++;
      if (/[^A-Za-z0-9]/.test(pwd)) score++;
      if (score <= 2) return 'weak';
      if (score <= 3) return 'medium';
      return 'strong';
    },

    passwordStrengthClass() {
      return `strength-${this.passwordStrength}`;
    },

    passwordStrengthColor() {
      return { weak: '#ef5350', medium: '#ffd54f', strong: '#4caf50' }[this.passwordStrength] || '';
    },

    passwordStrengthLabel() {
      return { weak: '⚠ Weak password', medium: '◑ Medium strength', strong: '✓ Strong password' }[this.passwordStrength] || '';
    },

    
    staffDashboardStats() {
      if (!this.staffDashboardSummary) return [];
      return [
        { label: 'Assigned Treks', value: this.staffDashboardSummary.total_assigned_expeditions || 0, icon: 'bi bi-map', iconBg: 'metric-icon-green' },
        { label: 'Total Participants', value: this.staffDashboardSummary.total_participants_across_assignments || 0, icon: 'bi bi-people', iconBg: 'metric-icon-gold' },
        { label: 'Open Treks', value: this.staffDashboardSummary.open_expeditions_count || 0, icon: 'bi bi-play-circle', iconBg: 'metric-icon-blue' },
        { label: 'Completed', value: this.staffDashboardSummary.completed_expeditions_count || 0, icon: 'bi bi-flag-fill', iconBg: 'metric-icon-red' },
      ];
    },
  },

  
  async mounted() {
    this.bookingModalInstance = new bootstrap.Modal(document.getElementById('bookingModal'));
    this.cancelBookingModalInstance = new bootstrap.Modal(document.getElementById('cancelBookingModal'));
    this.participantsModalInstance = new bootstrap.Modal(document.getElementById('participantsModal'));

    const stored_refresh_token = localStorage.getItem(REFRESH_TOKEN_STORAGE_KEY);
    if (stored_refresh_token) {
      await this.attemptSessionRestoreFromRefreshToken(stored_refresh_token);
    }

    const preloader = document.getElementById('app-preloader');
    if (preloader) {
      preloader.style.opacity = '0';
      setTimeout(() => preloader.remove(), 300);
    }
  },

  methods: {

    
    async callTrekPlatformApi(endpoint, method = 'GET', body = null, skipAuth = false, isRetry = false) {
      const request_headers = { 'Content-Type': 'application/json' };

      if (!skipAuth && this.inMemoryAccessToken) {
        request_headers['Authorization'] = `Bearer ${this.inMemoryAccessToken}`;
      }

      const fetch_options = { method, headers: request_headers };
      if (body) fetch_options.body = JSON.stringify(body);

      let api_response;
      try {
        api_response = await fetch(`${TREK_PLATFORM_API_BASE_URL}${endpoint}`, fetch_options);
      } catch (network_error) {
        this.showToast('error', 'Network Error', 'Could not reach the server. Is the backend running?');
        return { data: null, status: 0, ok: false };
      }

      if (api_response.status === 401 && !isRetry && !skipAuth) {
        const refresh_token = localStorage.getItem(REFRESH_TOKEN_STORAGE_KEY);
        if (refresh_token) {
          const token_refreshed = await this.performTokenRefresh(refresh_token);
          if (token_refreshed) {
            return await this.callTrekPlatformApi(endpoint, method, body, skipAuth, true);
          } else {
            this.forceLogoutAndClearSession();
            return { data: null, status: 401, ok: false };
          }
        }
      }

      let response_data = null;
      try {
        response_data = await api_response.json();
      } catch (_) {
      }

      return { data: response_data, status: api_response.status, ok: api_response.ok };
    },

    async handleCoverImageFileUpload(event, type) {
      const file = event.target.files[0];
      if (!file) return;

      if (file.size > 5 * 1024 * 1024) {
        this.showToast('error', 'File Too Large', 'Cover images must be smaller than 5MB.');
        return;
      }

      this.coverImageUploading = true;

      const reader = new FileReader();
      reader.onload = () => {
        const base64Url = reader.result;
        if (type === 'create') {
          this.expeditionFormData.expedition_cover_image_url = base64Url;
        } else if (type === 'edit' && this.adminEditingExpedition) {
          this.adminEditingExpedition.expedition_cover_image_url = base64Url;
        }
        this.coverImageUploading = false;
        this.showToast('success', 'Upload Complete', 'Cover image updated successfully!');
      };
      reader.onerror = () => {
        this.coverImageUploading = false;
        this.showToast('error', 'Upload Failed', 'Failed to read cover image file.');
      };
      reader.readAsDataURL(file);
    },

    
    validateLoginForm() {
      this.loginFormErrors = {};
      if (!this.loginFormData.user_email_address.trim()) {
        this.loginFormErrors.email = 'Email address is required.';
      } else if (!/\S+@\S+\.\S+/.test(this.loginFormData.user_email_address)) {
        this.loginFormErrors.email = 'Please enter a valid email address.';
      }
      if (!this.loginFormData.submitted_password) {
        this.loginFormErrors.password = 'Password is required.';
      }
      return Object.keys(this.loginFormErrors).length === 0;
    },

    
    async handleUserLoginSubmission() {
      if (!this.validateLoginForm()) return;
      this.loginSubmitting = true;
      this.loginApiError = '';

      const { data, ok } = await this.callTrekPlatformApi('/auth/login', 'POST', {
        user_email_address: this.loginFormData.user_email_address,
        submitted_password: this.loginFormData.submitted_password,
      }, true);

      this.loginSubmitting = false;

      if (ok && data) {
        this.inMemoryAccessToken = data.access_token;
        if (data.refresh_token) {
          localStorage.setItem(REFRESH_TOKEN_STORAGE_KEY, data.refresh_token);
        }
        this.authenticatedUserSession = data.authenticated_user;
        this.loginFormData = { user_email_address: '', submitted_password: '' };
        this.navigateToDefaultViewForRole(data.authenticated_user.assigned_platform_role);
        await this.loadInitialDataForRole();
        this.showToast('success', 'Welcome back!', `Logged in as ${data.authenticated_user.user_full_name}`);
      } else {
        this.loginApiError = data?.error_detail?.message || data?.message || 'Invalid credentials.';
      }
    },

    
    validateRegistrationForm() {
      this.registrationFormErrors = {};
      const reg = this.registrationFormData;

      if (!reg.user_full_name.trim() || reg.user_full_name.trim().length < 2) {
        this.registrationFormErrors.user_full_name = 'Full name must be at least 2 characters.';
      }
      if (!reg.user_email_address.trim()) {
        this.registrationFormErrors.user_email_address = 'Email is required.';
      } else if (!/\S+@\S+\.\S+/.test(reg.user_email_address)) {
        this.registrationFormErrors.user_email_address = 'Enter a valid email address.';
      }
      if (reg.user_contact_phone_number && !/^[+]?[\d\s\-()]{7,15}$/.test(reg.user_contact_phone_number)) {
        this.registrationFormErrors.user_contact_phone_number = 'Enter a valid phone number.';
      }
      if (!reg.raw_password) {
        this.registrationFormErrors.raw_password = 'Password is required.';
      } else if (reg.raw_password.length < 8) {
        this.registrationFormErrors.raw_password = 'Password must be at least 8 characters.';
      } else if (!/[A-Z]/.test(reg.raw_password)) {
        this.registrationFormErrors.raw_password = 'Must contain at least one uppercase letter.';
      } else if (!/[0-9]/.test(reg.raw_password)) {
        this.registrationFormErrors.raw_password = 'Must contain at least one digit.';
      } else if (!/[^A-Za-z0-9]/.test(reg.raw_password)) {
        this.registrationFormErrors.raw_password = 'Must contain at least one special character (!@#$...).';
      }
      return Object.keys(this.registrationFormErrors).length === 0;
    },

    
    async handleTrekkerRegistrationSubmission() {
      if (!this.validateRegistrationForm()) return;
      this.registrationSubmitting = true;
      this.registrationApiError = '';

      const { data, ok } = await this.callTrekPlatformApi('/auth/register', 'POST', this.registrationFormData, true);
      this.registrationSubmitting = false;

      if (ok && data) {
        this.loginFormData.user_email_address = this.registrationFormData.user_email_address;
        this.loginFormData.submitted_password = this.registrationFormData.raw_password;
        this.registrationFormData = { user_full_name: '', user_email_address: '', user_contact_phone_number: '', raw_password: '' };
        this.showToast('success', 'Account Created!', 'Welcome to TrekVista. Logging you in...');
        await this.handleUserLoginSubmission();
      } else {
        this.registrationApiError = data?.error_detail?.message || data?.message || 'Registration failed. Please try again.';
      }
    },

    
    async performTokenRefresh(stored_refresh_token) {
      const old_access_token = this.inMemoryAccessToken;
      this.inMemoryAccessToken = stored_refresh_token;
      const { data, ok } = await this.callTrekPlatformApi('/auth/refresh-token', 'POST', {}, false);
      if (ok && data?.new_access_token) {
        this.inMemoryAccessToken = data.new_access_token;
        return true;
      }
      this.inMemoryAccessToken = old_access_token;
      return false;
    },

    
    async attemptSessionRestoreFromRefreshToken(refresh_token) {
      this.globalLoadingState = true;
      this.globalLoadingMessage = 'Restoring session...';

      // handle error
      this.inMemoryAccessToken = refresh_token;

      const { data, ok } = await this.callTrekPlatformApi('/auth/refresh-token', 'POST', {}, false);

      if (ok && data?.new_access_token) {
        this.inMemoryAccessToken = data.new_access_token;
        const profile_response = await this.callTrekPlatformApi('/auth/me', 'GET');
        if (profile_response.ok && profile_response.data?.current_user_profile) {
          this.authenticatedUserSession = profile_response.data.current_user_profile;
          this.navigateToDefaultViewForRole(profile_response.data.current_user_profile.assigned_platform_role);
          await this.loadInitialDataForRole();
        } else {
          this.inMemoryAccessToken = null;
          localStorage.removeItem(REFRESH_TOKEN_STORAGE_KEY);
        }
      } else {
        this.inMemoryAccessToken = null;
        localStorage.removeItem(REFRESH_TOKEN_STORAGE_KEY);
      }

      this.globalLoadingState = false;
    },

    
    async handleLogout() {
      await this.callTrekPlatformApi('/auth/logout', 'DELETE');
      this.forceLogoutAndClearSession();
      this.showToast('info', 'Logged out', 'See you on the trails! 🏔️');
    },

    
    forceLogoutAndClearSession() {
      this.inMemoryAccessToken = null;
      this.authenticatedUserSession = null;
      localStorage.removeItem(REFRESH_TOKEN_STORAGE_KEY);
      this.activeAuthView = 'login';
      this.destroyAllChartInstances();
    },

    
    async navigateTo(target_view) {
      this.currentView = target_view;
      this.sidebarOpen = false;
      await this.loadDataForView(target_view);
    },

    
    navigateToDefaultViewForRole(role) {
      const role_default_views = {
        Admin: 'admin-dashboard',
        Staff: 'staff-dashboard',
        Trekker: 'trekker-dashboard',
      };
      this.currentView = role_default_views[role] || 'login';
    },

    
    toggleSidebar() {
      this.sidebarOpen = !this.sidebarOpen;
    },

    
    async loadDataForView(view) {
      const view_loaders = {
        'admin-dashboard':         this.loadAdminDashboard,
        'admin-expeditions':       this.loadAdminExpeditions,
        'admin-users':             this.loadAdminUsers,
        'admin-create-expedition': this.loadAllStaffForDropdown,
        'admin-create-staff':      () => {},
        'admin-analytics':         this.loadAdminAnalyticsCharts,
        'staff-dashboard':         this.loadStaffDashboard,
        'staff-expeditions':       this.loadStaffAssignedExpeditions,
        'trekker-dashboard':       this.loadTrekkerDashboard,
        'trekker-explore':         () => this.loadOpenExpeditions(1),
        'bookings':                this.loadTrekkerBookings,
        'profile':                 this.loadProfileData,
      };
      if (view_loaders[view]) await view_loaders[view]();
    },

    
    async loadInitialDataForRole() {
      if (!this.authenticatedUserSession) return;
      await this.loadDataForView(this.currentView);
    },

    
    async loadAdminDashboard() {
      const { data, ok } = await this.callTrekPlatformApi('/admin/dashboard/metrics');
      if (ok && data) {
        const metrics = data.admin_dashboard_metrics || data;
        const totalExpeditions = metrics.total_expeditions_on_platform !== undefined ? metrics.total_expeditions_on_platform : (metrics.total_expedition_routes || 0);
        const totalStaff = metrics.total_staff_accounts !== undefined ? metrics.total_staff_accounts : (metrics.total_registered_staff_members || 0);
        const totalBookings = metrics.active_participant_bookings !== undefined ? metrics.active_participant_bookings : (metrics.total_platform_wide_bookings || 0);
        const totalTrekkers = metrics.total_registered_trekkers !== undefined ? metrics.total_registered_trekkers : 0;

        this.adminDashboardMetrics = [
          { key: 'treks', label: 'Total Expeditions', value: totalExpeditions, icon: 'bi bi-map-fill', iconBg: 'metric-icon-green' },
          { key: 'users', label: 'Registered Users',  value: totalTrekkers, icon: 'bi bi-people-fill', iconBg: 'metric-icon-gold' },
          { key: 'staff', label: 'Trek Staff',         value: totalStaff, icon: 'bi bi-person-badge-fill', iconBg: 'metric-icon-blue' },
          { key: 'bookings', label: 'Total Bookings',  value: totalBookings, icon: 'bi bi-calendar-check-fill', iconBg: 'metric-icon-red' },
        ];

        this.$nextTick(() => this.renderAdminDashboardCharts(metrics));
      }

      const exp_response = await this.callTrekPlatformApi('/admin/expeditions?page=1&per_page=5');
      if (exp_response.ok && exp_response.data) {
        this.adminRecentExpeditions = exp_response.data.expeditions || exp_response.data.expedition_list || [];
      }
    },

    
    async loadAdminExpeditions() {
      const params = new URLSearchParams({
        page: this.adminExpeditionsPage,
        per_page: 15,
      });
      if (this.adminExpeditionsStatusFilter) params.append('status_filter', this.adminExpeditionsStatusFilter);

      const { data, ok } = await this.callTrekPlatformApi(`/admin/expeditions?${params}`);
      if (ok && data) {
        this.adminAllExpeditions = data.expeditions || data.expedition_list || [];
        this.adminExpeditionsPagination = data.pagination || data.pagination_metadata || {};
      }
    },

    
    async loadAdminUsers() {
      const params = new URLSearchParams();
      if (this.userSearchKeyword.trim()) params.append('search_keyword', this.userSearchKeyword);
      if (this.userRoleFilter) params.append('role_filter', this.userRoleFilter);

      const { data, ok } = await this.callTrekPlatformApi(`/admin/users?${params}`);
      if (ok && data) this.adminAllUsers = data.platform_users || data.user_accounts_list || [];
    },

    
    async loadAllStaffForDropdown() {
      const { data, ok } = await this.callTrekPlatformApi('/admin/users?role_filter=Staff&per_page=100');
      if (ok && data) this.allStaffAccounts = data.platform_users || data.user_accounts_list || [];
    },

    
    debouncedUserSearch() {
      clearTimeout(this._userSearchDebounceTimer);
      this._userSearchDebounceTimer = setTimeout(() => this.loadAdminUsers(), SEARCH_DEBOUNCE_DELAY_MS);
    },

    
    validateExpeditionForm(form_data) {
      const errors = {};
      if (!form_data.expedition_route_name?.trim()) {
        errors.expedition_route_name = 'Route name is required.';
      }
      if (!form_data.expedition_geographical_location?.trim()) {
        errors.expedition_geographical_location = 'Location is required.';
      }
      if (!form_data.expedition_difficulty_level) {
        errors.expedition_difficulty_level = 'Select a difficulty level.';
      }
      if (!form_data.expedition_duration_in_days || form_data.expedition_duration_in_days < 1) {
        errors.expedition_duration_in_days = 'Duration must be at least 1 day.';
      }
      if (!form_data.total_participant_slots_capacity || form_data.total_participant_slots_capacity < 1) {
        errors.total_participant_slots_capacity = 'Must have at least 1 slot.';
      }
      if (form_data.expedition_scheduled_start_date && form_data.expedition_scheduled_end_date) {
        if (new Date(form_data.expedition_scheduled_end_date) < new Date(form_data.expedition_scheduled_start_date)) {
          errors.expedition_scheduled_end_date = 'End date cannot be before start date.';
        }
      }
      return errors;
    },

    
    async handleCreateExpeditionSubmission() {
      this.expeditionFormErrors = this.validateExpeditionForm(this.expeditionFormData);
      if (Object.keys(this.expeditionFormErrors).length > 0) return;

      this.expeditionFormSubmitting = true;
      this.expeditionFormApiError = '';

      const payload = { ...this.expeditionFormData };
      if (!payload.expedition_cover_image_url || payload.expedition_cover_image_url.trim() === '') {
        payload.expedition_cover_image_url = null;
      }
      if (payload.assigned_staff_leader_id === '' || payload.assigned_staff_leader_id === null) {
        payload.assigned_staff_leader_id = null;
      } else {
        payload.assigned_staff_leader_id = parseInt(payload.assigned_staff_leader_id, 10);
      }

      const { data, ok } = await this.callTrekPlatformApi('/admin/expeditions', 'POST', payload);
      this.expeditionFormSubmitting = false;

      if (ok) {
        this.showToast('success', 'Expedition Created!', `"${data.new_expedition_route_name}" is ready.`);
        this.resetExpeditionForm();
        this.navigateTo('admin-expeditions');
      } else {
        this.expeditionFormApiError = data?.message || 'Failed to create expedition.';
      }
    },

    
    resetExpeditionForm() {
      this.expeditionFormData = {
        expedition_route_name: '', expedition_geographical_location: '',
        expedition_difficulty_level: '', expedition_duration_in_days: 5,
        expedition_price_per_person_inr: 0, total_participant_slots_capacity: 20,
        expedition_scheduled_start_date: '', expedition_scheduled_end_date: '',
        expedition_booking_cutoff_date: '', assigned_staff_leader_id: null,
        expedition_cover_image_url: '', expedition_meeting_point_address: '',
        expedition_detailed_description: '',
      };
      this.expeditionFormErrors = {};
      this.expeditionFormApiError = '';
    },

    
    openAdminEditExpeditionModal(expedition) {
      this.adminEditingExpedition = JSON.parse(JSON.stringify(expedition));
      // redirct to page
      if (this.allStaffAccounts.length === 0) this.loadAllStaffForDropdown();
      new bootstrap.Modal(document.getElementById('adminEditExpeditionModal')).show();
    },

    
    async handleUpdateExpedition() {
      if (!this.adminEditingExpedition) return;
      this.editExpeditionSubmitting = true;

      const payload = { ...this.adminEditingExpedition };
      if (!payload.expedition_cover_image_url || payload.expedition_cover_image_url.trim() === '') {
        payload.expedition_cover_image_url = null;
      }
      if (payload.assigned_staff_leader_id === '' || payload.assigned_staff_leader_id === null) {
        payload.assigned_staff_leader_id = null;
      } else {
        payload.assigned_staff_leader_id = parseInt(payload.assigned_staff_leader_id, 10);
      }

      const expedition_id = this.adminEditingExpedition.trekking_route_expedition_id;
      const { data, ok } = await this.callTrekPlatformApi(
        `/admin/expeditions/${expedition_id}`, 'PATCH', payload
      );
      this.editExpeditionSubmitting = false;

      if (ok) {
        this.showToast('success', 'Expedition Updated', `"${this.adminEditingExpedition.expedition_route_name}" saved.`);
        bootstrap.Modal.getInstance(document.getElementById('adminEditExpeditionModal')).hide();
        await this.loadAdminExpeditions();
        if (this.currentView === 'admin-dashboard') await this.loadAdminDashboard();
      } else {
        this.showToast('error', 'Update Failed', data?.message || 'Could not save changes.');
      }
    },

    
    confirmDeleteExpedition(expedition) {
      this.expeditionToDelete = expedition;
      new bootstrap.Modal(document.getElementById('deleteConfirmModal')).show();
    },

    
    async handleDeleteExpedition() {
      if (!this.expeditionToDelete) return;
      this.deleteSubmitting = true;

      const { ok } = await this.callTrekPlatformApi(
        `/admin/expeditions/${this.expeditionToDelete.trekking_route_expedition_id}`, 'DELETE'
      );
      this.deleteSubmitting = false;

      if (ok) {
        this.showToast('success', 'Deleted', `"${this.expeditionToDelete.expedition_route_name}" removed.`);
        bootstrap.Modal.getInstance(document.getElementById('deleteConfirmModal')).hide();
        this.expeditionToDelete = null;
        await this.loadAdminExpeditions();
      } else {
        this.showToast('error', 'Delete Failed', 'Could not delete the expedition.');
      }
    },

    
    async handleCreateStaffSubmission() {
      this.staffFormErrors = {};
      if (!this.staffFormData.user_full_name.trim()) this.staffFormErrors.user_full_name = 'Name is required.';
      if (!this.staffFormData.user_email_address.trim()) this.staffFormErrors.user_email_address = 'Email is required.';
      if (!this.staffFormData.raw_password || this.staffFormData.raw_password.length < 8) {
        this.staffFormErrors.raw_password = 'Password must be at least 8 characters.';
      }
      if (Object.keys(this.staffFormErrors).length > 0) return;

      this.staffFormSubmitting = true;
      this.staffFormApiError = '';

      const { data, ok } = await this.callTrekPlatformApi('/admin/staff', 'POST', this.staffFormData);
      this.staffFormSubmitting = false;

      if (ok) {
        this.showToast('success', 'Staff Created', `${this.staffFormData.user_full_name} can now log in.`);
        this.staffFormData = { user_full_name: '', user_email_address: '', user_contact_phone_number: '', raw_password: '' };
        this.navigateTo('admin-users');
      } else {
        this.staffFormApiError = data?.message || 'Failed to create staff account.';
      }
    },

    
    async toggleUserBlacklist(user) {
      const { ok } = await this.callTrekPlatformApi(`/admin/users/${user.user_account_id}/blacklist`, 'PATCH');
      if (ok) {
        user.is_account_blacklisted = !user.is_account_blacklisted;
        const action = user.is_account_blacklisted ? 'banned' : 'unbanned';
        this.showToast('info', 'Status Updated', `${user.user_full_name}'s account has been ${action}.`);
      }
    },

    
    async deleteUserAccount(user) {
      if (!confirm(`Are you sure you want to permanently delete user "${user.user_full_name}" (${user.user_email_address})? All bookings (if Trekker) will be deleted.`)) {
        return;
      }
      const { ok, data } = await this.callTrekPlatformApi(`/admin/users/${user.user_account_id}`, 'DELETE');
      if (ok) {
        this.showToast('success', 'User Deleted', `Account for ${user.user_full_name} has been permanently deleted.`);
        this.loadAdminUsers();
      } else {
        this.showToast('danger', 'Deletion Failed', data?.error || 'Failed to delete user.');
      }
    },

    
    async viewExpeditionParticipants(expedition) {
      this.openStaffParticipantsModal(expedition);
    },

    
    renderAdminDashboardCharts(metrics_data) {
      this.destroyChart('admin-difficulty-chart');
      const difficulty_canvas = document.getElementById('admin-difficulty-chart');
      if (difficulty_canvas && metrics_data.difficulty_distribution) {
        const dist = metrics_data.difficulty_distribution;
        this._chartInstances['admin-difficulty-chart'] = new Chart(difficulty_canvas, {
          type: 'bar',
          data: {
            labels: Object.keys(dist),
            datasets: [{
              label: 'Expeditions',
              data: Object.values(dist),
              backgroundColor: [CHART_COLOR_PALETTE.green, CHART_COLOR_PALETTE.gold, CHART_COLOR_PALETTE.red],
              borderRadius: 8,
              borderSkipped: false,
            }],
          },
          options: this.getChartBaseOptions('bar'),
        });
      }

      this.destroyChart('admin-booking-chart');
      const booking_canvas = document.getElementById('admin-booking-chart');
      if (booking_canvas && metrics_data.booking_status_distribution) {
        const dist = metrics_data.booking_status_distribution;
        this._chartInstances['admin-booking-chart'] = new Chart(booking_canvas, {
          type: 'doughnut',
          data: {
            labels: Object.keys(dist),
            datasets: [{
              data: Object.values(dist),
              backgroundColor: [CHART_COLOR_PALETTE.green, CHART_COLOR_PALETTE.red, CHART_COLOR_PALETTE.blue],
              borderWidth: 0,
            }],
          },
          options: { ...this.getChartBaseOptions('doughnut'), cutout: '65%' },
        });
      }
    },

    
    async loadAdminAnalyticsCharts() {
      const { data, ok } = await this.callTrekPlatformApi('/admin/dashboard/metrics');
      if (!ok || !data) return;

      await this.$nextTick();

      this.destroyChart('popular-treks-chart');
      const popular_canvas = document.getElementById('popular-treks-chart');
      if (popular_canvas && data.most_popular_expeditions?.length > 0) {
        const popular = data.most_popular_expeditions.slice(0, 8);
        this._chartInstances['popular-treks-chart'] = new Chart(popular_canvas, {
          type: 'bar',
          data: {
            labels: popular.map(e => e.expedition_route_name.slice(0, 20)),
            datasets: [{
              label: 'Bookings',
              data: popular.map(e => e.booking_count),
              backgroundColor: [
                CHART_COLOR_PALETTE.green, CHART_COLOR_PALETTE.sage, CHART_COLOR_PALETTE.teal,
                CHART_COLOR_PALETTE.blue, CHART_COLOR_PALETTE.gold, CHART_COLOR_PALETTE.amber,
                CHART_COLOR_PALETTE.purple, CHART_COLOR_PALETTE.red,
              ],
              borderRadius: 8, borderSkipped: false,
            }],
          },
          options: this.getChartBaseOptions('bar'),
        });
      }

      this.destroyChart('difficulty-participation-chart');
      const diff_canvas = document.getElementById('difficulty-participation-chart');
      if (diff_canvas && data.difficulty_distribution) {
        this._chartInstances['difficulty-participation-chart'] = new Chart(diff_canvas, {
          type: 'pie',
          data: {
            labels: Object.keys(data.difficulty_distribution),
            datasets: [{
              data: Object.values(data.difficulty_distribution),
              backgroundColor: [CHART_COLOR_PALETTE.green, CHART_COLOR_PALETTE.gold, CHART_COLOR_PALETTE.red],
              borderWidth: 0,
            }],
          },
          options: this.getChartBaseOptions('pie'),
        });
      }

      this.destroyChart('bookings-timeline-chart');
      const timeline_canvas = document.getElementById('bookings-timeline-chart');
      if (timeline_canvas) {
        const monthly_data = data.monthly_bookings_last_6_months || [12, 28, 45, 33, 61, 52];
        const month_labels = data.monthly_labels_last_6_months || this.getLastSixMonthLabels();
        this._chartInstances['bookings-timeline-chart'] = new Chart(timeline_canvas, {
          type: 'line',
          data: {
            labels: month_labels,
            datasets: [{
              label: 'New Bookings',
              data: monthly_data,
              borderColor: CHART_COLOR_PALETTE.green,
              backgroundColor: 'rgba(76, 175, 80, 0.08)',
              tension: 0.4,
              fill: true,
              pointBackgroundColor: CHART_COLOR_PALETTE.green,
              pointRadius: 5,
            }],
          },
          options: this.getChartBaseOptions('line'),
        });
      }
    },

    
    getChartBaseOptions(chart_type) {
      const base = {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: {
            display: chart_type !== 'bar',
            labels: {
              color: '#a5c8a5',
              padding: 20,
              usePointStyle: true,
              font: { family: 'Inter', size: 12 },
            },
          },
          tooltip: {
            backgroundColor: '#1c321c',
            titleColor: '#e8f5e9',
            bodyColor: '#a5c8a5',
            borderColor: 'rgba(76,175,80,0.3)',
            borderWidth: 1,
            cornerRadius: 8,
            padding: 12,
          },
        },
      };
      if (chart_type === 'bar' || chart_type === 'line') {
        base.scales = {
          x: {
            ticks: { color: '#6a8f6a', font: { size: 11 } },
            grid: { color: 'rgba(76,175,80,0.07)' },
          },
          y: {
            ticks: { color: '#6a8f6a', font: { size: 11 } },
            grid: { color: 'rgba(76,175,80,0.07)' },
            beginAtZero: true,
          },
        };
      }
      return base;
    },

    
    getLastSixMonthLabels() {
      const months = [];
      const now = new Date();
      for (let i = 5; i >= 0; i--) {
        const d = new Date(now.getFullYear(), now.getMonth() - i, 1);
        months.push(d.toLocaleString('default', { month: 'short', year: '2-digit' }));
      }
      return months;
    },

    
    destroyChart(canvas_id) {
      if (this._chartInstances[canvas_id]) {
        this._chartInstances[canvas_id].destroy();
        delete this._chartInstances[canvas_id];
      }
    },

    
    destroyAllChartInstances() {
      Object.keys(this._chartInstances).forEach(id => this.destroyChart(id));
    },

    
    async loadStaffDashboard() {
      const { data, ok } = await this.callTrekPlatformApi('/staff/dashboard/summary');
      if (ok && data) {
        const summary = data.staff_dashboard_summary || data;
        const counts = summary.assigned_expedition_counts_by_status || {};
        const totalAssigned = Object.values(counts).reduce((a, b) => a + b, 0);

        this.staffDashboardSummary = {
          total_assigned_expeditions: summary.total_assigned_expeditions !== undefined ? summary.total_assigned_expeditions : totalAssigned,
          total_participants_across_assignments: summary.total_participants_across_assignments !== undefined ? summary.total_participants_across_assignments : (summary.total_active_participants_under_management || 0),
          open_expeditions_count: summary.open_expeditions_count !== undefined ? summary.open_expeditions_count : (counts['Open'] || 0),
          completed_expeditions_count: summary.completed_expeditions_count !== undefined ? summary.completed_expeditions_count : (counts['Completed'] || 0),
        };

        if (summary.all_assigned_expeditions) {
          this.staffOpenExpeditions = summary.all_assigned_expeditions.filter(
            e => e.current_expedition_lifecycle_status === 'Open'
          );
        } else {
          const exp_res = await this.callTrekPlatformApi('/staff/assigned-expeditions');
          if (exp_res.ok && exp_res.data) {
            const list = exp_res.data.assigned_expeditions || exp_res.data.assigned_expedition_routes_list || [];
            this.staffOpenExpeditions = list.filter(
              e => e.current_expedition_lifecycle_status === 'Open'
            );
          }
        }
      }
    },

    
    async loadStaffAssignedExpeditions() {
      const params = new URLSearchParams();
      if (this.staffExpeditionsFilter) params.append('status_filter', this.staffExpeditionsFilter);
      const { data, ok } = await this.callTrekPlatformApi(`/staff/assigned-expeditions?${params}`);
      if (ok && data) {
        this.staffAllAssignedExpeditions = data.assigned_expeditions || data.assigned_expedition_routes_list || [];
      }
    },

    
    openStaffExpeditionManageModal(expedition) {
      this.staffManagingExpedition = expedition;
      this.staffUpdatePayload = {
        current_expedition_lifecycle_status: null,
        available_participant_slots_remaining: null,
      };
      new bootstrap.Modal(document.getElementById('staffManageModal')).show();
    },

    
    async handleStaffExpeditionUpdate() {
      if (!this.staffManagingExpedition) return;
      this.staffUpdateSubmitting = true;

      const update_payload = {};
      if (this.staffUpdatePayload.current_expedition_lifecycle_status) {
        update_payload.current_expedition_lifecycle_status = this.staffUpdatePayload.current_expedition_lifecycle_status;
      }
      if (this.staffUpdatePayload.available_participant_slots_remaining !== null) {
        update_payload.available_participant_slots_remaining = this.staffUpdatePayload.available_participant_slots_remaining;
      }

      const exp_id = this.staffManagingExpedition.trekking_route_expedition_id;
      const { ok } = await this.callTrekPlatformApi(`/staff/assigned-expeditions/${exp_id}/operational-update`, 'PATCH', update_payload);
      this.staffUpdateSubmitting = false;

      if (ok) {
        this.showToast('success', 'Expedition Updated', 'Changes applied successfully.');
        bootstrap.Modal.getInstance(document.getElementById('staffManageModal')).hide();
        await this.loadStaffDashboard();
        await this.loadStaffAssignedExpeditions();
      } else {
        this.showToast('error', 'Update Failed', 'Could not apply changes.');
      }
    },

    
    async openStaffParticipantsModal(expedition) {
      this.expeditionParticipants = [];
      this.participantsLoading = true;
      this.participantsModalInstance.show();

      const { data, ok } = await this.callTrekPlatformApi(
        `/staff/assigned-expeditions/${expedition.trekking_route_expedition_id}/participants`
      );
      this.participantsLoading = false;
      if (ok && data) this.expeditionParticipants = data.participant_booking_records_list || [];
    },

    
    async loadTrekkerDashboard() {
      await Promise.all([this.loadTrekkerBookings(), this.loadOpenExpeditions(1)]);

      this.trekkerStats = {
        totalBookings: this.trekkerAllBookings.length,
        completedTreks: this.trekkerAllBookings.filter(b => b.current_booking_lifecycle_status === 'Completed').length,
        upcomingTreks:  this.trekkerAllBookings.filter(b => b.current_booking_lifecycle_status === 'Booked').length,
        cancelledTreks: this.trekkerAllBookings.filter(b => b.current_booking_lifecycle_status === 'Cancelled').length,
      };

      this.trekkerUpcomingBookings = this.trekkerAllBookings
        .filter(b => b.current_booking_lifecycle_status === 'Booked')
        .sort((a, b) => new Date(a.expedition_scheduled_start_date) - new Date(b.expedition_scheduled_start_date))
        .slice(0, 3);
    },

    
    async loadOpenExpeditions(page = 1) {
      this.expeditionsLoading = true;
      const params = new URLSearchParams({ page, per_page: 12 });
      if (this.trekFilterParams.difficulty_level_filter) params.append('difficulty_level_filter', this.trekFilterParams.difficulty_level_filter);
      if (this.trekFilterParams.geographical_location_keyword) params.append('geographical_location_keyword', this.trekFilterParams.geographical_location_keyword);
      if (this.trekFilterParams.maximum_price_inr) params.append('maximum_price_inr', this.trekFilterParams.maximum_price_inr);
      if (this.trekFilterParams.maximum_duration_days) params.append('maximum_duration_days', this.trekFilterParams.maximum_duration_days);

      const { data, ok } = await this.callTrekPlatformApi(`/trekker/expeditions/open?${params}`);
      this.expeditionsLoading = false;
      if (ok && data) {
        this.trekkerOpenExpeditions = data.open_expeditions || [];
        this.openTreksPagination = data.pagination || {};
      }
    },

    
    debouncedTrekSearch() {
      clearTimeout(this._trekSearchDebounceTimer);
      this._trekSearchDebounceTimer = setTimeout(() => this.loadOpenExpeditions(1), SEARCH_DEBOUNCE_DELAY_MS);
    },

    
    clearTrekFilters() {
      this.trekFilterParams = { difficulty_level_filter: '', geographical_location_keyword: '', maximum_price_inr: null, maximum_duration_days: null };
      this.loadOpenExpeditions(1);
    },

    
    async loadTrekkerBookings() {
      const params = new URLSearchParams();
      if (this.bookingStatusFilter) params.append('status_filter', this.bookingStatusFilter);
      const { data, ok } = await this.callTrekPlatformApi(`/trekker/bookings?${params}`);
      if (ok && data) {
        this.trekkerAllBookings = data.booking_history || data.booking_history_records || [];
      }
    },

    
    openBookingModal(expedition) {
      this.selectedExpeditionForBooking = expedition;
      this.bookingParticipants = 1;
      this.bookingSpecialNote = '';
      this.bookingStep = 1;
      this.bookingModalInstance.show();
    },

    
    async handleConfirmBooking() {
      if (!this.selectedExpeditionForBooking) return;
      this.bookingStep = 3;

      const { data, ok } = await this.callTrekPlatformApi(
        '/trekker/bookings',
        'POST',
        {
          booked_expedition_instance_id: this.selectedExpeditionForBooking.trekking_route_expedition_id,
          number_of_participants_in_booking: this.bookingParticipants,
          trekker_special_requirements_note: this.bookingSpecialNote || null,
          simulated_payment_completed: true,
        }
      );

      if (ok && data) {
        this.bookingModalInstance.hide();
        this.showToast(
          'success',
          '🎉 Booking Confirmed!',
          `Your trek is booked! Ref: ${data.booking_confirmation_reference_code}`,
          6000
        );
        await this.loadOpenExpeditions(this.openTreksPagination.current_page);
        await this.loadTrekkerBookings();
      } else {
        this.bookingStep = 2;
        this.showToast('error', 'Booking Failed', data?.message || 'Could not complete booking.');
      }
    },

    
    openCancelBookingModal(booking) {
      this.selectedBookingForCancellation = booking;
      this.cancellationReason = '';
      this.cancelBookingModalInstance.show();
    },

    
    async handleConfirmCancellation() {
      if (!this.selectedBookingForCancellation) return;
      this.cancellationSubmitting = true;

      const { data, ok } = await this.callTrekPlatformApi(
        `/trekker/bookings/${this.selectedBookingForCancellation.participant_booking_record_id}/cancel`,
        'PATCH',
        { cancellation_reason_description: this.cancellationReason || null }
      );
      this.cancellationSubmitting = false;

      if (ok) {
        this.cancelBookingModalInstance.hide();
        this.showToast('warning', 'Booking Cancelled', 'Your booking has been cancelled. Slot restored.');
        await this.loadTrekkerBookings();
        if (this.currentView === 'trekker-dashboard') await this.loadTrekkerDashboard();
      } else {
        this.showToast('error', 'Cancellation Failed', data?.message || 'Could not cancel booking.');
      }
    },

    
    async triggerBookingCsvExport() {
      this.csvExportLoading = true;
      const { data, ok } = await this.callTrekPlatformApi('/trekker/bookings/export-csv', 'POST');
      this.csvExportLoading = false;

      if (ok) {
        this.showToast(
          'info',
          '📄 CSV Export Queued',
          'Your booking history export is being prepared. You\'ll receive it via email shortly.',
          7000
        );
      } else {
        this.showToast('error', 'Export Failed', data?.message || 'Could not queue CSV export.');
      }
    },

    
    async loadProfileData() {
      this.profileFormData = {
        user_full_name: this.authenticatedUserSession.user_full_name || '',
        user_contact_phone_number: this.authenticatedUserSession.user_contact_phone_number || '',
        user_profile_bio_summary: this.authenticatedUserSession.user_profile_bio_summary || '',
        user_emergency_contact_name: this.authenticatedUserSession.user_emergency_contact_name || '',
        user_emergency_contact_phone: this.authenticatedUserSession.user_emergency_contact_phone || '',
      };
    },

    
    async handleProfileUpdate() {
      this.profileUpdateSubmitting = true;
      const { data, ok } = await this.callTrekPlatformApi('/auth/update-profile', 'PATCH', this.profileFormData);
      this.profileUpdateSubmitting = false;

      if (ok) {
        this.authenticatedUserSession = { ...this.authenticatedUserSession, ...this.profileFormData };
        this.showToast('success', 'Profile Updated', 'Your profile has been saved.');
      } else {
        this.showToast('error', 'Update Failed', data?.message || 'Could not save profile.');
      }
    },

    
    async handlePasswordChange() {
      this.passwordChangeErrors = {};
      if (!this.passwordChangeData.current_password) {
        this.passwordChangeErrors.current_password = 'Current password is required.';
      }
      if (!this.passwordChangeData.new_password || this.passwordChangeData.new_password.length < 8) {
        this.passwordChangeErrors.new_password = 'New password must be at least 8 characters.';
      }
      if (Object.keys(this.passwordChangeErrors).length > 0) return;

      this.passwordChangeSubmitting = true;
      const { data, ok } = await this.callTrekPlatformApi('/auth/change-password', 'PATCH', this.passwordChangeData);
      this.passwordChangeSubmitting = false;

      if (ok) {
        this.showToast('success', 'Password Changed', 'Your password has been updated successfully.');
        this.passwordChangeData = { current_password: '', new_password: '' };
      } else {
        this.showToast('error', 'Change Failed', data?.message || 'Incorrect current password.');
      }
    },

    
    showToast(type, title, message, duration = 4000) {
      const toast_id = `toast-${++this._toastIdCounter}`;
      const icon_map = {
        success: 'bi bi-check-circle-fill',
        error:   'bi bi-x-circle-fill',
        warning: 'bi bi-exclamation-triangle-fill',
        info:    'bi bi-info-circle-fill',
      };
      const color_map = {
        success: '#4caf50',
        error:   '#ef5350',
        warning: '#ffd54f',
        info:    '#29b6f6',
      };

      const toast_container = document.getElementById('trek-toast-container');
      if (!toast_container) return;

      const toast_el = document.createElement('div');
      toast_el.id = toast_id;
      toast_el.className = `trek-toast toast-${type}`;
      toast_el.innerHTML = `
        <i class="${icon_map[type]} toast-icon" style="color:${color_map[type]};"></i>
        <div class="toast-body">
          <div class="toast-title" style="color:${color_map[type]};">${title}</div>
          <div class="toast-message">${message}</div>
        </div>
        <button class="toast-close" onclick="this.parentElement.remove()">
          <i class="bi bi-x-lg"></i>
        </button>
      `;
      toast_container.appendChild(toast_el);

      setTimeout(() => {
        toast_el.classList.add('toast-exit');
        setTimeout(() => toast_el.remove(), 300);
      }, duration);
    },

    
    formatDate(iso_date_string) {
      if (!iso_date_string) return 'N/A';
      try {
        const date = new Date(iso_date_string);
        return date.toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' });
      } catch (_) { return iso_date_string; }
    },

    
    difficultyBadgeClass(difficulty) {
      const class_map = { Easy: 'badge-easy', Moderate: 'badge-moderate', Hard: 'badge-hard' };
      return class_map[difficulty] || 'badge-easy';
    },

    
    statusBadgeClass(status) {
      const class_map = {
        Open: 'badge-open', Closed: 'badge-closed', Pending: 'badge-pending',
        Approved: 'badge-approved', Completed: 'badge-completed', Cancelled: 'badge-closed',
      };
      return class_map[status] || 'badge-pending';
    },

    
    bookingBadgeClass(status) {
      const class_map = { Booked: 'badge-booked', Completed: 'badge-completed', Cancelled: 'badge-cancelled' };
      return class_map[status] || 'badge-booked';
    },

    
    slotFillPercent(expedition) {
      const total = expedition.total_participant_slots_capacity;
      const remaining = expedition.available_participant_slots_remaining;
      if (!total) return 0;
      const filled = total - remaining;
      return Math.min(100, Math.round((filled / total) * 100));
    },
  },

}).mount('#trek-app');
