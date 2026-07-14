const StaffDashboard = {
  props: ['app'],
  template: `
    <div>
         STAFF: DASHBOARD
      ==================================================== -->
      <div v-if="app.currentView === 'staff-dashboard'" class="animate-in">
        <div class="dashboard-hero">
          <div class="hero-badge"><i class="bi bi-person-badge me-1"></i>Trek Staff</div>
          <h1>Welcome, {{ app.authenticatedUserSession?.user_full_name?.split(' ')[0] }}! <span class="emoji-reset">🌿</span></h1>
          <p class="hero-sub">Manage your assigned expeditions and participants.</p>
        </div>

        <div class="row g-3 mb-4" v-if="app.staffDashboardSummary">
          <div class="col-6 col-md-3" v-for="stat in app.staffDashboardStats" :key="stat.label">
            <div class="metric-card count-up-animate">
              <div class="metric-card-icon" :class="stat.iconBg">
                <i :class="stat.icon"></i>
              </div>
              <div class="metric-value">{{ stat.value }}</div>
              <div class="metric-label">{{ stat.label }}</div>
            </div>
          </div>
        </div>

        <div class="glass-panel p-3">
          <h6 class="section-title mb-3">Open Assigned Expeditions</h6>
          <div v-if="app.staffOpenExpeditions.length === 0" class="empty-state">
            <div class="empty-state-icon">🏕️</div>
            <p>No open expeditions assigned to you currently.</p>
          </div>
          <div class="row g-3" v-else>
            <div class="col-md-6 col-lg-4" v-for="exp in app.staffOpenExpeditions" :key="exp.trekking_route_expedition_id">
              <div class="trek-card" @click="app.openStaffExpeditionManageModal(exp)">
                <div class="trek-card-body p-3">
                  <div class="trek-card-name">{{ exp.expedition_route_name }}</div>
                  <div class="trek-card-location"><i class="bi bi-geo-alt-fill"></i>{{ exp.expedition_geographical_location }}</div>
                  <div class="d-flex justify-content-between align-items-center">
                    <span class="trek-badge" :class="app.statusBadgeClass(exp.current_expedition_lifecycle_status)">
                      {{ exp.current_expedition_lifecycle_status }}
                    </span>
                    <span style="font-size:0.82rem;color:var(--trek-text-muted);">
                      {{ exp.available_participant_slots_remaining }} slots left
                    </span>
                  </div>
                  <div class="trek-slot-bar mt-2">
                    <div class="trek-slot-fill" :style="{ width: app.slotFillPercent(exp) + '%' }"></div>
                  </div>
                  <button class="btn btn-trek-primary btn-sm w-100 mt-2" @click.stop="app.openStaffExpeditionManageModal(exp)">
                    <i class="bi bi-gear me-1"></i>Manage
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

         STAFF: ALL ASSIGNED EXPEDITIONS
      ==================================================== -->
      <div v-if="app.currentView === 'staff-expeditions'" class="animate-in">
        <div class="section-header">
          <h2 class="section-title">Assigned <span>Expeditions</span></h2>
          <select class="form-select form-select-sm" v-model="app.staffExpeditionsFilter" @change="app.loadStaffAssignedExpeditions" style="width:auto;font-size:0.83rem;">
            <option value="">All</option>
            <option v-for="s in app.expeditionStatuses" :key="s" :value="s">{{ s }}</option>
          </select>
        </div>

        <div class="row g-3">
          <div v-if="app.staffAllAssignedExpeditions.length === 0" class="col-12">
            <div class="empty-state glass-panel p-5">
              <div class="empty-state-icon">🗺️</div>
              <p>No expeditions assigned yet.</p>
            </div>
          </div>
          <div class="col-md-6 col-lg-4" v-for="exp in app.staffAllAssignedExpeditions" :key="exp.trekking_route_expedition_id">
            <div class="trek-card">
              <div class="trek-card-image">
                <img v-if="exp.expedition_cover_image_url" :src="exp.expedition_cover_image_url" :alt="exp.expedition_route_name" loading="lazy" />
                <div v-else class="trek-card-image-placeholder">⛰️</div>
                <span class="trek-card-difficulty-badge trek-badge" :class="app.difficultyBadgeClass(exp.expedition_difficulty_level)">
                  {{ exp.expedition_difficulty_level }}
                </span>
                <span class="trek-card-status-badge trek-badge" :class="app.statusBadgeClass(exp.current_expedition_lifecycle_status)">
                  {{ exp.current_expedition_lifecycle_status }}
                </span>
              </div>
              <div class="trek-card-body">
                <div class="trek-card-name">{{ exp.expedition_route_name }}</div>
                <div class="trek-card-location"><i class="bi bi-geo-alt-fill"></i>{{ exp.expedition_geographical_location }}</div>
                <div class="trek-meta-grid">
                  <div class="trek-meta-item">
                    <span class="meta-val">{{ exp.expedition_duration_in_days }}d</span>
                    <span class="meta-key">Duration</span>
                  </div>
                  <div class="trek-meta-item">
                    <span class="meta-val">{{ exp.available_participant_slots_remaining }}</span>
                    <span class="meta-key">Slots Left</span>
                  </div>
                </div>
                <div class="trek-slot-bar mb-2">
                  <div class="trek-slot-fill" :style="{ width: app.slotFillPercent(exp) + '%' }"></div>
                </div>
                <div class="d-flex gap-2">
                  <button class="btn btn-trek-primary btn-sm flex-fill" @click="app.openStaffExpeditionManageModal(exp)">
                    <i class="bi bi-gear me-1"></i>Manage
                  </button>
                  <button class="btn btn-trek-outline btn-sm" @click="app.openStaffParticipantsModal(exp)">
                    <i class="bi bi-people"></i>
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div class="modal fade" id="staffManageModal" tabindex="-1" aria-hidden="true">
        <div class="modal-dialog modal-dialog-centered">
          <div class="modal-content">
            <div class="modal-header">
              <h5 class="modal-title"><i class="bi bi-gear me-2" style="color:var(--trek-primary);"></i>Manage Expedition</h5>
              <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
            </div>
            <div class="modal-body" v-if="app.staffManagingExpedition">
              <h6 style="font-weight:700;color:var(--trek-text-primary);margin-bottom:0.25rem;">{{ app.staffManagingExpedition.expedition_route_name }}</h6>
              <div style="font-size:0.82rem;color:var(--trek-text-muted);margin-bottom:1.5rem;">{{ app.staffManagingExpedition.expedition_geographical_location }}</div>
              <div class="mb-3">
                <label class="form-label">Update Status</label>
                <select class="form-select" v-model="app.staffUpdatePayload.current_expedition_lifecycle_status">
                  <option :value="null">— No change —</option>
                  <option value="Open">Open (accepting bookings)</option>
                  <option value="Closed">Closed (no new bookings)</option>
                  <option value="Completed">Completed (trek finished)</option>
                </select>
              </div>
              <div class="mb-3">
                <label class="form-label">Available Slots Override</label>
                <input type="number" class="form-control" v-model.number="app.staffUpdatePayload.available_participant_slots_remaining" :max="app.staffManagingExpedition.total_participant_slots_capacity" min="0" placeholder="Leave empty to keep current" />
                <div style="font-size:0.75rem;color:var(--trek-text-muted);margin-top:4px;">
                  Current: {{ app.staffManagingExpedition.available_participant_slots_remaining }} / {{ app.staffManagingExpedition.total_participant_slots_capacity }}
                </div>
              </div>
            </div>
            <div class="modal-footer">
              <button class="btn btn-trek-outline" data-bs-dismiss="modal">Cancel</button>
              <button class="btn btn-trek-primary" @click="app.handleStaffExpeditionUpdate" :disabled="app.staffUpdateSubmitting">
                <span v-if="app.staffUpdateSubmitting"><span class="spinner-border spinner-border-sm me-2"></span>Updating...</span>
                <span v-else><i class="bi bi-check-lg me-1"></i>Apply Changes</span>
              </button>
            </div>
          </div>
        </div>
      </div>

      <div class="modal fade" id="participantsModal" tabindex="-1" aria-hidden="true">
        <div class="modal-dialog modal-dialog-centered modal-lg modal-dialog-scrollable">
          <div class="modal-content">
            <div class="modal-header">
              <h5 class="modal-title"><i class="bi bi-people me-2" style="color:var(--trek-primary);"></i>Participant Roster</h5>
              <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
            </div>
            <div class="modal-body">
              <div v-if="app.participantsLoading" class="text-center py-4">
                <div class="trek-spinner mx-auto"></div>
              </div>
              <div v-else>
                <div v-if="app.expeditionParticipants.length === 0" class="empty-state py-3">
                  <div class="empty-state-icon" style="font-size:2rem;">👥</div>
                  <p style="font-size:0.88rem;">No confirmed participants yet.</p>
                </div>
                <div v-for="(p, idx) in app.expeditionParticipants" :key="p.participant_booking_record_id" class="d-flex align-items-center gap-3 mb-2 p-2" style="background:rgba(76,175,80,0.05);border-radius:8px;border:1px solid rgba(76,175,80,0.08);">
                  <div style="font-weight:700;color:var(--trek-text-muted);min-width:24px;font-size:0.82rem;">{{ idx + 1 }}</div>
                  <div class="avatar-circle" style="width:36px;height:36px;font-size:0.78rem;flex-shrink:0;">
                    {{ p.booking_owner_trekker?.user_full_name?.slice(0,2)?.toUpperCase() || 'TK' }}
                  </div>
                  <div class="flex-fill">
                    <div style="font-weight:600;font-size:0.88rem;color:var(--trek-text-primary);">Booking Ref: {{ p.booking_confirmation_reference_code }}</div>
                    <div style="font-size:0.75rem;color:var(--trek-text-muted);">{{ p.trekker_special_requirements_note || 'No special requirements' }}</div>
                  </div>
                  <span class="trek-badge" :class="app.bookingBadgeClass(p.current_booking_lifecycle_status)">
                    {{ p.current_booking_lifecycle_status }}
                  </span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

    </div>
  `
};
