const AdminDashboard = {
  props: ['app'],
  template: `
    <div>
         ADMIN: DASHBOARD
      ==================================================== -->
      <div v-if="app.currentView === 'admin-dashboard'" class="animate-in">
        <div class="dashboard-hero">
          <div class="hero-badge"><i class="bi bi-shield-check me-1"></i>Administrator</div>
          <h1>Welcome back, {{ app.authenticatedUserSession?.user_full_name?.split(' ')[0] }}! <span class="emoji-reset">🌿</span></h1>
          <p class="hero-sub">Here's your platform overview for today.</p>
        </div>

        <div class="row g-3 mb-4">
          <div class="col-6 col-md-3" v-for="metric in app.adminDashboardMetrics" :key="metric.key">
            <div class="metric-card count-up-animate">
              <div class="metric-card-icon" :class="metric.iconBg">
                <i :class="metric.icon"></i>
              </div>
              <div class="metric-value">{{ metric.value }}</div>
              <div class="metric-label">{{ metric.label }}</div>
            </div>
          </div>
        </div>

        <div class="row g-3 mb-4">
          <div class="col-md-6">
            <div class="chart-card">
              <div class="chart-title"><i class="bi bi-bar-chart-fill"></i>Expeditions by Difficulty</div>
              <div style="position: relative; height: 220px; width: 100%;">
                <canvas id="admin-difficulty-chart"></canvas>
              </div>
            </div>
          </div>
          <div class="col-md-6">
            <div class="chart-card">
              <div class="chart-title"><i class="bi bi-pie-chart-fill"></i>Booking Status Distribution</div>
              <div style="position: relative; height: 220px; width: 100%;">
                <canvas id="admin-booking-chart"></canvas>
              </div>
            </div>
          </div>
        </div>

        <div class="glass-panel p-3">
          <div class="section-header mb-3">
            <h6 class="section-title mb-0">Recent Expeditions</h6>
            <button class="btn btn-trek-outline btn-sm" @click="app.navigateTo('admin-expeditions')">
              View All <i class="bi bi-arrow-right ms-1"></i>
            </button>
          </div>
          <div class="table-responsive">
            <table class="trek-table">
              <thead>
                <tr>
                  <th>Expedition Name</th>
                  <th>Difficulty</th>
                  <th>Status</th>
                  <th>Slots</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                <tr v-if="app.adminRecentExpeditions.length === 0">
                  <td colspan="5" class="text-center py-4" style="color:var(--trek-text-muted);">
                    No expeditions yet. <a href="#" @click.prevent="app.navigateTo('admin-create-expedition')" class="text-trek-primary">Create one →</a>
                  </td>
                </tr>
                <tr v-for="expedition in app.adminRecentExpeditions" :key="expedition.trekking_route_expedition_id">
                  <td style="color:var(--trek-text-primary);font-weight:600;">{{ expedition.expedition_route_name }}</td>
                  <td>
                    <span class="trek-badge" :class="app.difficultyBadgeClass(expedition.expedition_difficulty_level)">
                      {{ expedition.expedition_difficulty_level }}
                    </span>
                  </td>
                  <td>
                    <span class="trek-badge" :class="app.statusBadgeClass(expedition.current_expedition_lifecycle_status)">
                      {{ expedition.current_expedition_lifecycle_status }}
                    </span>
                  </td>
                  <td>
                    <span style="font-size:0.82rem;">
                      {{ expedition.available_participant_slots_remaining }}/{{ expedition.total_participant_slots_capacity }}
                    </span>
                  </td>
                  <td>
                    <button class="btn btn-sm btn-trek-outline me-1" @click="app.openAdminEditExpeditionModal(expedition)">
                      <i class="bi bi-pencil"></i>
                    </button>
                    <button class="btn btn-sm btn-trek-danger" @click="app.confirmDeleteExpedition(expedition)">
                      <i class="bi bi-trash"></i>
                    </button>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>

         ADMIN: EXPEDITIONS LIST
      ==================================================== -->
      <div v-if="app.currentView === 'admin-expeditions'" class="animate-in">
        <div class="section-header">
          <h2 class="section-title">All <span>Expeditions</span></h2>
          <div class="d-flex gap-2 flex-wrap">
            <select class="form-select form-select-sm" v-model="app.adminExpeditionsStatusFilter" @change="app.loadAdminExpeditions" style="width:auto;font-size:0.83rem;">
              <option value="">All Statuses</option>
              <option v-for="s in app.expeditionStatuses" :key="s" :value="s">{{ s }}</option>
            </select>
            <button class="btn btn-trek-primary btn-sm" @click="app.navigateTo('admin-create-expedition')">
              <i class="bi bi-plus-lg me-1"></i>New Expedition
            </button>
          </div>
        </div>

        <div class="table-responsive glass-panel p-3">
          <table class="trek-table">
            <thead>
              <tr>
                <th>Expedition</th>
                <th>Location</th>
                <th>Difficulty</th>
                <th>Duration</th>
                <th>Price</th>
                <th>Slots</th>
                <th>Staff</th>
                <th>Status</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              <tr v-if="app.adminAllExpeditions.length === 0">
                <td colspan="9" class="py-4">
                  <div class="empty-state">
                    <div class="empty-state-icon">🗺️</div>
                    <p>No expeditions found. Create your first one!</p>
                  </div>
                </td>
              </tr>
              <tr v-for="exp in app.adminAllExpeditions" :key="exp.trekking_route_expedition_id">
                <td style="font-weight:600;color:var(--trek-text-primary);max-width:200px;">
                  <div style="white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">{{ exp.expedition_route_name }}</div>
                </td>
                <td style="font-size:0.82rem;">{{ exp.expedition_geographical_location }}</td>
                <td><span class="trek-badge" :class="app.difficultyBadgeClass(exp.expedition_difficulty_level)">{{ exp.expedition_difficulty_level }}</span></td>
                <td style="font-size:0.82rem;">{{ exp.expedition_duration_in_days }}d</td>
                <td style="font-size:0.82rem;">₹{{ exp.expedition_price_per_person_inr?.toLocaleString() || 0 }}</td>
                <td style="font-size:0.82rem;">{{ exp.available_participant_slots_remaining }}/{{ exp.total_participant_slots_capacity }}</td>
                <td style="font-size:0.82rem;">{{ exp.assigned_staff_leader_name }}</td>
                <td><span class="trek-badge" :class="app.statusBadgeClass(exp.current_expedition_lifecycle_status)">{{ exp.current_expedition_lifecycle_status }}</span></td>
                <td>
                  <button class="btn btn-sm btn-trek-outline me-1" @click="app.openAdminEditExpeditionModal(exp)" title="Edit">
                    <i class="bi bi-pencil"></i>
                  </button>
                  <button class="btn btn-sm me-1" style="background:rgba(41,182,246,0.1);border:1px solid rgba(41,182,246,0.3);color:#29b6f6;border-radius:6px;" @click="app.viewExpeditionParticipants(exp)" title="Participants">
                    <i class="bi bi-people"></i>
                  </button>
                  <button class="btn btn-sm btn-trek-danger" @click="app.confirmDeleteExpedition(exp)" title="Delete">
                    <i class="bi bi-trash"></i>
                  </button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <div class="d-flex justify-content-between align-items-center mt-3" v-if="app.adminExpeditionsPagination.total_pages > 1">
          <span style="font-size:0.82rem;color:var(--trek-text-muted);">
            Page {{ app.adminExpeditionsPagination.current_page }} of {{ app.adminExpeditionsPagination.total_pages }}
            ({{ app.adminExpeditionsPagination.total_expedition_count }} total)
          </span>
          <div class="btn-group">
            <button class="btn btn-trek-outline btn-sm" :disabled="!app.adminExpeditionsPagination.has_previous_page" @click="app.adminExpeditionsPage--; app.loadAdminExpeditions()">← Prev</button>
            <button class="btn btn-trek-outline btn-sm" :disabled="!app.adminExpeditionsPagination.has_next_page" @click="app.adminExpeditionsPage++; app.loadAdminExpeditions()">Next →</button>
          </div>
        </div>
      </div>

         ADMIN: CREATE EXPEDITION FORM
      ==================================================== -->
      <div v-if="app.currentView === 'admin-create-expedition'" class="animate-in">
        <div class="section-header">
          <h2 class="section-title">Create <span>Expedition</span></h2>
          <button class="btn btn-trek-outline btn-sm" @click="app.navigateTo('admin-expeditions')">
            <i class="bi bi-arrow-left me-1"></i>Back
          </button>
        </div>

        <div class="glass-panel p-4">
          <form id="create-expedition-form" @submit.prevent="app.handleCreateExpeditionSubmission" novalidate>
            <div class="row g-3">
              <div class="col-md-8">
                <label class="form-label">Expedition Route Name *</label>
                <input type="text" class="form-control" :class="{ 'is-invalid': app.expeditionFormErrors.expedition_route_name }" v-model="app.expeditionFormData.expedition_route_name" placeholder="e.g. Roopkund Trek — Winter 2026" />
                <div class="invalid-feedback">{{ app.expeditionFormErrors.expedition_route_name }}</div>
              </div>
              <div class="col-md-4">
                <label class="form-label">Difficulty Level *</label>
                <select class="form-select" :class="{ 'is-invalid': app.expeditionFormErrors.expedition_difficulty_level }" v-model="app.expeditionFormData.expedition_difficulty_level">
                  <option value="">Select...</option>
                  <option value="Easy">Easy</option>
                  <option value="Moderate">Moderate</option>
                  <option value="Hard">Hard</option>
                </select>
                <div class="invalid-feedback">{{ app.expeditionFormErrors.expedition_difficulty_level }}</div>
              </div>
              <div class="col-md-6">
                <label class="form-label">Geographical Location *</label>
                <input type="text" class="form-control" :class="{ 'is-invalid': app.expeditionFormErrors.expedition_geographical_location }" v-model="app.expeditionFormData.expedition_geographical_location" placeholder="e.g. Uttarakhand, India" />
                <div class="invalid-feedback">{{ app.expeditionFormErrors.expedition_geographical_location }}</div>
              </div>
              <div class="col-md-3">
                <label class="form-label">Duration (Days) *</label>
                <input type="number" class="form-control" min="1" max="365" :class="{ 'is-invalid': app.expeditionFormErrors.expedition_duration_in_days }" v-model.number="app.expeditionFormData.expedition_duration_in_days" />
                <div class="invalid-feedback">{{ app.expeditionFormErrors.expedition_duration_in_days }}</div>
              </div>
              <div class="col-md-3">
                <label class="form-label">Price per Person (₹) *</label>
                <input type="number" class="form-control" min="0" v-model.number="app.expeditionFormData.expedition_price_per_person_inr" placeholder="0 for free" />
              </div>
              <div class="col-md-4">
                <label class="form-label">Start Date</label>
                <input type="date" class="form-control" v-model="app.expeditionFormData.expedition_scheduled_start_date" />
              </div>
              <div class="col-md-4">
                <label class="form-label">End Date</label>
                <input type="date" class="form-control" v-model="app.expeditionFormData.expedition_scheduled_end_date" />
              </div>
              <div class="col-md-4">
                <label class="form-label">Booking Cutoff Date</label>
                <input type="date" class="form-control" v-model="app.expeditionFormData.expedition_booking_cutoff_date" />
              </div>
              <div class="col-md-4">
                <label class="form-label">Total Slots *</label>
                <input type="number" class="form-control" min="1" max="500" :class="{ 'is-invalid': app.expeditionFormErrors.total_participant_slots_capacity }" v-model.number="app.expeditionFormData.total_participant_slots_capacity" />
                <div class="invalid-feedback">{{ app.expeditionFormErrors.total_participant_slots_capacity }}</div>
              </div>
              <div class="col-md-4">
                <label class="form-label">Assign Staff Leader</label>
                <select class="form-select" v-model="app.expeditionFormData.assigned_staff_leader_id">
                  <option :value="null">Unassigned</option>
                  <option v-for="staff in app.allStaffAccounts" :key="staff.user_account_id" :value="staff.user_account_id">
                    {{ staff.user_full_name }}
                  </option>
                </select>
              </div>
              <div class="col-md-4">
                <label class="form-label">Cover Image</label>
                <div class="d-flex gap-2">
                  <input type="text" class="form-control" v-model="app.expeditionFormData.expedition_cover_image_url" placeholder="https://... or upload" />
                  <label class="btn btn-trek-outline mb-0 d-inline-flex align-items-center justify-content-center" style="cursor:pointer; width:42px; height:38px;">
                    <i class="bi bi-upload"></i>
                    <input type="file" accept="image/*" style="display:none;" @change="e => app.handleCoverImageFileUpload(e, 'create')" />
                  </label>
                </div>
                <div v-if="app.coverImageUploading" style="font-size:0.75rem; color:var(--trek-primary);" class="mt-1">
                  <span class="spinner-border spinner-border-sm me-1"></span>Uploading...
                </div>
              </div>
              <div class="col-12">
                <label class="form-label">Meeting Point Address</label>
                <input type="text" class="form-control" v-model="app.expeditionFormData.expedition_meeting_point_address" placeholder="Assembly point / landmark" />
              </div>
              <div class="col-12">
                <label class="form-label">Detailed Description</label>
                <textarea class="form-control" rows="4" v-model="app.expeditionFormData.expedition_detailed_description" placeholder="Full route description, highlights, requirements..."></textarea>
              </div>
            </div>

            <div v-if="app.expeditionFormApiError" class="alert mt-3 py-2" style="background:rgba(239,83,80,0.1);border-color:rgba(239,83,80,0.3);color:#ef9a9a;border-radius:8px;font-size:0.85rem;">
              <i class="bi bi-exclamation-triangle me-2"></i>{{ app.expeditionFormApiError }}
            </div>

            <div class="mt-4 d-flex gap-2">
              <button type="submit" class="btn btn-trek-primary" :disabled="app.expeditionFormSubmitting">
                <span v-if="app.expeditionFormSubmitting">
                  <span class="spinner-border spinner-border-sm me-2"></span>Creating...
                </span>
                <span v-else><i class="bi bi-plus-circle me-2"></i>Create Expedition</span>
              </button>
              <button type="button" class="btn btn-trek-outline" @click="app.resetExpeditionForm">
                <i class="bi bi-arrow-counterclockwise me-1"></i>Reset
              </button>
            </div>
          </form>
        </div>
      </div>

         ADMIN: USER MANAGEMENT
      ==================================================== -->
      <div v-if="app.currentView === 'admin-users'" class="animate-in">
        <div class="section-header">
          <h2 class="section-title">User <span>Management</span></h2>
          <div class="d-flex gap-2 flex-wrap">
            <input type="text" class="form-control form-control-sm" v-model="app.userSearchKeyword" @input="app.debouncedUserSearch" placeholder="Search users..." style="width:200px;font-size:0.83rem;" />
            <select class="form-select form-select-sm" v-model="app.userRoleFilter" @change="app.loadAdminUsers" style="width:auto;font-size:0.83rem;">
              <option value="">All Roles</option>
              <option value="Trekker">Trekkers</option>
              <option value="Staff">Staff</option>
            </select>
          </div>
        </div>

        <div v-if="app.userRoleFilter === '' || app.userRoleFilter === 'Staff'" class="mb-4">
          <h4 style="font-weight:700;color:var(--trek-text-secondary);font-size:1rem;" class="mb-3">
            <i class="bi bi-person-badge me-2" style="color:var(--trek-primary);"></i>Trek Guides & Staff
          </h4>
          <div class="glass-panel p-3">
            <div class="table-responsive">
              <table class="trek-table">
                <thead>
                  <tr>
                    <th>Name</th>
                    <th>Email</th>
                    <th>Role</th>
                    <th>Status</th>
                    <th>Joined</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-if="app.adminAllUsers.filter(u => u.assigned_platform_role === 'Staff').length === 0">
                    <td colspan="6" class="py-4 text-center" style="color:var(--trek-text-muted);">No staff members found.</td>
                  </tr>
                  <tr v-for="user in app.adminAllUsers.filter(u => u.assigned_platform_role === 'Staff')" :key="user.user_account_id">
                    <td>
                      <div class="d-flex align-items-center gap-2">
                        <div class="avatar-circle" style="width:32px;height:32px;font-size:0.72rem;flex-shrink:0;">
                          {{ user.user_full_name.slice(0,2).toUpperCase() }}
                        </div>
                        <span style="font-weight:600;color:var(--trek-text-primary);font-size:0.88rem;">{{ user.user_full_name }}</span>
                      </div>
                    </td>
                    <td style="font-size:0.82rem;">{{ user.user_email_address }}</td>
                    <td>
                      <span class="trek-badge badge-approved">
                        {{ user.assigned_platform_role }}
                      </span>
                    </td>
                    <td>
                      <span class="trek-badge" v-if="user.is_account_blacklisted" style="background:rgba(239,83,80,0.15);color:#ef9a9a;">
                        <i class="bi bi-ban me-1"></i>Blacklisted
                      </span>
                      <span class="trek-badge badge-open" v-else>
                        <i class="bi bi-check-circle me-1"></i>Active
                      </span>
                    </td>
                    <td style="font-size:0.78rem;color:var(--trek-text-muted);">
                      {{ app.formatDate(user.account_created_at_utc) }}
                    </td>
                    <td>
                      <div class="d-flex gap-2">
                        <button class="btn btn-sm" :class="user.is_account_blacklisted ? 'btn-trek-outline' : 'btn-trek-danger'" @click="app.toggleUserBlacklist(user)" :title="user.is_account_blacklisted ? 'Remove Blacklist' : 'Blacklist User'">
                          <i :class="user.is_account_blacklisted ? 'bi bi-shield-check' : 'bi bi-ban'"></i>
                          {{ user.is_account_blacklisted ? 'Unban' : 'Ban' }}
                        </button>
                        <button class="btn btn-sm btn-trek-danger" style="background:linear-gradient(90deg, #ef5350, #d32f2f);" @click="app.deleteUserAccount(user)" title="Delete Account">
                          <i class="bi bi-trash"></i>
                        </button>
                      </div>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </div>

        <div v-if="app.userRoleFilter === '' || app.userRoleFilter === 'Trekker'">
          <h4 style="font-weight:700;color:var(--trek-text-secondary);font-size:1rem;" class="mb-3">
            <i class="bi bi-backpack me-2" style="color:var(--trek-primary);"></i>Adventure Seekers & Trekkers
          </h4>
          <div class="glass-panel p-3">
            <div class="table-responsive">
              <table class="trek-table">
                <thead>
                  <tr>
                    <th>Name</th>
                    <th>Email</th>
                    <th>Role</th>
                    <th>Status</th>
                    <th>Joined</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-if="app.adminAllUsers.filter(u => u.assigned_platform_role === 'Trekker').length === 0">
                    <td colspan="6" class="py-4 text-center" style="color:var(--trek-text-muted);">No trekkers found.</td>
                  </tr>
                  <tr v-for="user in app.adminAllUsers.filter(u => u.assigned_platform_role === 'Trekker')" :key="user.user_account_id">
                    <td>
                      <div class="d-flex align-items-center gap-2">
                        <div class="avatar-circle" style="width:32px;height:32px;font-size:0.72rem;flex-shrink:0;">
                          {{ user.user_full_name.slice(0,2).toUpperCase() }}
                        </div>
                        <span style="font-weight:600;color:var(--trek-text-primary);font-size:0.88rem;">{{ user.user_full_name }}</span>
                      </div>
                    </td>
                    <td style="font-size:0.82rem;">{{ user.user_email_address }}</td>
                    <td>
                      <span class="trek-badge badge-booked">
                        {{ user.assigned_platform_role }}
                      </span>
                    </td>
                    <td>
                      <span class="trek-badge" v-if="user.is_account_blacklisted" style="background:rgba(239,83,80,0.15);color:#ef9a9a;">
                        <i class="bi bi-ban me-1"></i>Blacklisted
                      </span>
                      <span class="trek-badge badge-open" v-else>
                        <i class="bi bi-check-circle me-1"></i>Active
                      </span>
                    </td>
                    <td style="font-size:0.78rem;color:var(--trek-text-muted);">
                      {{ app.formatDate(user.account_created_at_utc) }}
                    </td>
                    <td>
                      <div class="d-flex gap-2">
                        <button class="btn btn-sm" :class="user.is_account_blacklisted ? 'btn-trek-outline' : 'btn-trek-danger'" @click="app.toggleUserBlacklist(user)" :title="user.is_account_blacklisted ? 'Remove Blacklist' : 'Blacklist User'">
                          <i :class="user.is_account_blacklisted ? 'bi bi-shield-check' : 'bi bi-ban'"></i>
                          {{ user.is_account_blacklisted ? 'Unban' : 'Ban' }}
                        </button>
                        <button class="btn btn-sm btn-trek-danger" style="background:linear-gradient(90deg, #ef5350, #d32f2f);" @click="app.deleteUserAccount(user)" title="Delete Account">
                          <i class="bi bi-trash"></i>
                        </button>
                      </div>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </div>

         ADMIN: ADD STAFF
      ==================================================== -->
      <div v-if="app.currentView === 'admin-create-staff'" class="animate-in">
        <div class="section-header">
          <h2 class="section-title">Add Trek <span>Staff</span></h2>
          <button class="btn btn-trek-outline btn-sm" @click="app.navigateTo('admin-users')">
            <i class="bi bi-arrow-left me-1"></i>Back
          </button>
        </div>
        <div class="glass-panel p-4" style="max-width:560px;">
          <form @submit.prevent="app.handleCreateStaffSubmission" novalidate>
            <div class="mb-3">
              <label class="form-label">Full Name *</label>
              <input type="text" class="form-control" :class="{ 'is-invalid': app.staffFormErrors.user_full_name }" v-model="app.staffFormData.user_full_name" placeholder="Staff member's full name" />
              <div class="invalid-feedback">{{ app.staffFormErrors.user_full_name }}</div>
            </div>
            <div class="mb-3">
              <label class="form-label">Email Address *</label>
              <input type="email" class="form-control" :class="{ 'is-invalid': app.staffFormErrors.user_email_address }" v-model="app.staffFormData.user_email_address" placeholder="staff@trekapp.com" />
              <div class="invalid-feedback">{{ app.staffFormErrors.user_email_address }}</div>
            </div>
            <div class="mb-3">
              <label class="form-label">Phone Number</label>
              <input type="tel" class="form-control" v-model="app.staffFormData.user_contact_phone_number" />
            </div>
            <div class="mb-4">
              <label class="form-label">Initial Password *</label>
              <input type="password" class="form-control" :class="{ 'is-invalid': app.staffFormErrors.raw_password }" v-model="app.staffFormData.raw_password" placeholder="Communicate securely to the staff member" />
              <div class="invalid-feedback">{{ app.staffFormErrors.raw_password }}</div>
            </div>
            <div v-if="app.staffFormApiError" class="alert py-2 mb-3" style="background:rgba(239,83,80,0.1);border-color:rgba(239,83,80,0.3);color:#ef9a9a;border-radius:8px;font-size:0.85rem;">
              {{ app.staffFormApiError }}
            </div>
            <button type="submit" class="btn btn-trek-primary" :disabled="app.staffFormSubmitting">
              <span v-if="app.staffFormSubmitting"><span class="spinner-border spinner-border-sm me-2"></span>Creating...</span>
              <span v-else><i class="bi bi-person-plus me-2"></i>Create Staff Account</span>
            </button>
          </form>
        </div>
      </div>

         ADMIN: ANALYTICS
      ==================================================== -->
      <div v-if="app.currentView === 'admin-analytics'" class="animate-in">
        <div class="section-header">
          <h2 class="section-title">Platform <span>Analytics</span></h2>
        </div>
        <div class="row g-3">
          <div class="col-md-6">
            <div class="chart-card">
              <div class="chart-title"><i class="bi bi-trophy-fill"></i>Popular Expeditions (by Bookings)</div>
              <div style="position: relative; height: 300px; width: 100%;">
                <canvas id="popular-treks-chart"></canvas>
              </div>
            </div>
          </div>
          <div class="col-md-6">
            <div class="chart-card">
              <div class="chart-title"><i class="bi bi-graph-up-arrow"></i>User Participation (by Difficulty)</div>
              <div style="position: relative; height: 300px; width: 100%;">
                <canvas id="difficulty-participation-chart"></canvas>
              </div>
            </div>
          </div>
          <div class="col-12">
            <div class="chart-card">
              <div class="chart-title"><i class="bi bi-calendar3"></i>Bookings Over Time (Monthly)</div>
              <div style="position: relative; height: 200px; width: 100%;">
                <canvas id="bookings-timeline-chart"></canvas>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div class="modal fade" id="adminEditExpeditionModal" tabindex="-1" aria-hidden="true">
        <div class="modal-dialog modal-dialog-centered modal-lg modal-dialog-scrollable">
          <div class="modal-content">
            <div class="modal-header">
              <h5 class="modal-title"><i class="bi bi-pencil-square me-2" style="color:var(--trek-primary);"></i>Edit Expedition</h5>
              <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
            </div>
            <div class="modal-body" v-if="app.adminEditingExpedition">
              <div class="row g-3">
                <div class="col-md-8">
                  <label class="form-label">Expedition Name</label>
                  <input type="text" class="form-control" v-model="app.adminEditingExpedition.expedition_route_name" />
                </div>
                <div class="col-md-4">
                  <label class="form-label">Status</label>
                  <select class="form-select" v-model="app.adminEditingExpedition.current_expedition_lifecycle_status">
                    <option v-for="s in app.expeditionStatuses" :key="s" :value="s">{{ s }}</option>
                  </select>
                </div>
                <div class="col-md-6">
                  <label class="form-label">Location</label>
                  <input type="text" class="form-control" v-model="app.adminEditingExpedition.expedition_geographical_location" />
                </div>
                <div class="col-md-3">
                  <label class="form-label">Difficulty</label>
                  <select class="form-select" v-model="app.adminEditingExpedition.expedition_difficulty_level">
                    <option value="Easy">Easy</option>
                    <option value="Moderate">Moderate</option>
                    <option value="Hard">Hard</option>
                  </select>
                </div>
                <div class="col-md-3">
                  <label class="form-label">Duration (Days)</label>
                  <input type="number" class="form-control" v-model.number="app.adminEditingExpedition.expedition_duration_in_days" min="1" />
                </div>
                <div class="col-md-4">
                  <label class="form-label">Price per Person (₹)</label>
                  <input type="number" class="form-control" v-model.number="app.adminEditingExpedition.expedition_price_per_person_inr" min="0" />
                </div>
                <div class="col-md-4">
                  <label class="form-label">Total Capacity</label>
                  <input type="number" class="form-control" v-model.number="app.adminEditingExpedition.total_participant_slots_capacity" min="1" />
                </div>
                <div class="col-md-4">
                  <label class="form-label">Assign Staff</label>
                  <select class="form-select" v-model="app.adminEditingExpedition.assigned_staff_leader_id">
                    <option :value="null">Unassigned</option>
                    <option v-for="staff in app.allStaffAccounts" :key="staff.user_account_id" :value="staff.user_account_id">
                      {{ staff.user_full_name }}</option>
                  </select>
                </div>
                <div class="col-md-4">
                  <label class="form-label">Start Date</label>
                  <input type="date" class="form-control" v-model="app.adminEditingExpedition.expedition_scheduled_start_date" />
                </div>
                <div class="col-md-4">
                  <label class="form-label">End Date</label>
                  <input type="date" class="form-control" v-model="app.adminEditingExpedition.expedition_scheduled_end_date" />
                </div>
                <div class="col-md-4">
                  <label class="form-label">Booking Cutoff</label>
                  <input type="date" class="form-control" v-model="app.adminEditingExpedition.expedition_booking_cutoff_date" />
                </div>
                <div class="col-12">
                  <label class="form-label">Meeting Point</label>
                  <input type="text" class="form-control" v-model="app.adminEditingExpedition.expedition_meeting_point_address" />
                </div>
                <div class="col-12">
                  <label class="form-label">Cover Image</label>
                  <div class="d-flex gap-2">
                    <input type="text" class="form-control" v-model="app.adminEditingExpedition.expedition_cover_image_url" placeholder="https://... or upload" />
                    <label class="btn btn-trek-outline mb-0 d-inline-flex align-items-center justify-content-center" style="cursor:pointer; width:42px; height:38px;">
                      <i class="bi bi-upload"></i>
                      <input type="file" accept="image/*" style="display:none;" @change="e => app.handleCoverImageFileUpload(e, 'edit')" />
                    </label>
                  </div>
                  <div v-if="app.coverImageUploading" style="font-size:0.75rem; color:var(--trek-primary);" class="mt-1">
                    <span class="spinner-border spinner-border-sm me-1"></span>Uploading...
                  </div>
                </div>
                <div class="col-12">
                  <label class="form-label">Description</label>
                  <textarea class="form-control" rows="3" v-model="app.adminEditingExpedition.expedition_detailed_description"></textarea>
                </div>
              </div>
            </div>
            <div class="modal-footer">
              <button class="btn btn-trek-outline" data-bs-dismiss="modal">Cancel</button>
              <button class="btn btn-trek-primary" @click="app.handleUpdateExpedition" :disabled="app.editExpeditionSubmitting">
                <span v-if="app.editExpeditionSubmitting"><span class="spinner-border spinner-border-sm me-2"></span></span>
                <i v-else class="bi bi-check-lg me-1"></i>Save Changes
              </button>
            </div>
          </div>
        </div>
      </div>

      <div class="modal fade" id="deleteConfirmModal" tabindex="-1" aria-hidden="true">
        <div class="modal-dialog modal-dialog-centered modal-sm">
          <div class="modal-content">
            <div class="modal-header">
              <h5 class="modal-title" style="color:var(--trek-danger);">
                <i class="bi bi-exclamation-triangle me-2"></i>Confirm Delete
              </h5>
              <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
            </div>
            <div class="modal-body">
              <p style="font-size:0.9rem;color:var(--trek-text-secondary);">
                Permanently delete <strong>{{ app.expeditionToDelete?.expedition_route_name }}</strong>?
                This cannot be undone.
              </p>
            </div>
            <div class="modal-footer">
              <button class="btn btn-trek-outline" data-bs-dismiss="modal">Cancel</button>
              <button class="btn btn-trek-danger" @click="app.handleDeleteExpedition" :disabled="app.deleteSubmitting">
                <span v-if="app.deleteSubmitting"><span class="spinner-border spinner-border-sm me-2"></span></span>
                <i v-else class="bi bi-trash me-1"></i>Delete
              </button>
            </div>
          </div>
        </div>
      </div>

    </div>
  `
};
