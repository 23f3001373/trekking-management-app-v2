const TrekkerDashboard = {
  props: ['app'],
  template: `
    <div>
         TREKKER: HOME DASHBOARD
      ==================================================== -->
      <div v-if="app.currentView === 'trekker-dashboard'" class="animate-in">
        <div class="dashboard-hero">
          <div class="hero-badge"><i class="bi bi-backpack me-1"></i>Trekker</div>
          <h1>Hello, {{ app.authenticatedUserSession?.user_full_name?.split(' ')[0] }}! <span class="emoji-reset">🌿</span></h1>
          <p class="hero-sub">Ready for your next adventure? Explore open expeditions.</p>
          <button class="btn btn-trek-primary mt-2" @click="app.navigateTo('trekker-explore')">
            <i class="bi bi-search me-2"></i>Explore Treks
          </button>
        </div>

        <div class="row g-3 mb-4">
          <div class="col-6 col-md-3">
            <div class="metric-card count-up-animate">
              <div class="metric-card-icon metric-icon-green"><i class="bi bi-calendar-check"></i></div>
              <div class="metric-value">{{ app.trekkerStats.totalBookings }}</div>
              <div class="metric-label">Total Bookings</div>
            </div>
          </div>
          <div class="col-6 col-md-3">
            <div class="metric-card count-up-animate">
              <div class="metric-card-icon metric-icon-gold"><i class="bi bi-flag-fill"></i></div>
              <div class="metric-value">{{ app.trekkerStats.completedTreks }}</div>
              <div class="metric-label">Completed Treks</div>
            </div>
          </div>
          <div class="col-6 col-md-3">
            <div class="metric-card count-up-animate">
              <div class="metric-card-icon metric-icon-blue"><i class="bi bi-clock-history"></i></div>
              <div class="metric-value">{{ app.trekkerStats.upcomingTreks }}</div>
              <div class="metric-label">Upcoming</div>
            </div>
          </div>
          <div class="col-6 col-md-3">
            <div class="metric-card count-up-animate">
              <div class="metric-card-icon metric-icon-red"><i class="bi bi-x-circle"></i></div>
              <div class="metric-value">{{ app.trekkerStats.cancelledTreks }}</div>
              <div class="metric-label">Cancelled</div>
            </div>
          </div>
        </div>

        <div class="glass-panel p-3 mb-3">
          <div class="section-header mb-3">
            <h6 class="section-title mb-0">Upcoming Treks</h6>
            <button class="btn btn-trek-outline btn-sm" @click="app.navigateTo('bookings')">View All</button>
          </div>
          <div v-if="app.trekkerUpcomingBookings.length === 0" class="empty-state py-3">
            <div class="empty-state-icon" style="font-size:2rem;">🏔️</div>
            <p style="font-size:0.88rem;">No upcoming treks. <a href="#" @click.prevent="app.navigateTo('trekker-explore')" class="text-trek-primary">Book one now!</a></p>
          </div>
          <div v-for="bk in app.trekkerUpcomingBookings" :key="bk.participant_booking_record_id" class="d-flex align-items-center gap-3 p-2 mb-2" style="background:rgba(76,175,80,0.06);border-radius:10px;border:1px solid rgba(76,175,80,0.1);">
            <div style="font-size:2rem;">⛺</div>
            <div class="flex-fill">
              <div style="font-weight:700;font-size:0.9rem;color:var(--trek-text-primary);">{{ bk.expedition_route_name }}</div>
              <div style="font-size:0.78rem;color:var(--trek-text-muted);">
                📅 {{ app.formatDate(bk.expedition_scheduled_start_date) }} · {{ bk.expedition_geographical_location }}
              </div>
            </div>
            <span class="trek-badge badge-booked">{{ bk.current_booking_lifecycle_status }}</span>
          </div>
        </div>
      </div>

         TREKKER: EXPLORE OPEN TREKS
      ==================================================== -->
      <div v-if="app.currentView === 'trekker-explore'" class="animate-in">
        <div class="section-header">
          <h2 class="section-title">Explore <span>Treks</span></h2>
          <span style="font-size:0.82rem;color:var(--trek-text-muted);">
            {{ app.openTreksPagination.total_open_expedition_count || 0 }} open expeditions
          </span>
        </div>

        <div class="filter-bar mb-4">
          <div class="row g-2 align-items-end">
            <div class="col-6 col-md-3">
              <label class="form-label mb-1" style="font-size:0.78rem;">Difficulty</label>
              <select class="form-select form-select-sm" v-model="app.trekFilterParams.difficulty_level_filter" @change="app.loadOpenExpeditions(1)">
                <option value="">Any</option>
                <option value="Easy">Easy</option>
                <option value="Moderate">Moderate</option>
                <option value="Hard">Hard</option>
              </select>
            </div>
            <div class="col-6 col-md-3">
              <label class="form-label mb-1" style="font-size:0.78rem;">Location</label>
              <input type="text" class="form-control form-control-sm" v-model="app.trekFilterParams.geographical_location_keyword" @input="app.debouncedTrekSearch" placeholder="Search location..." />
            </div>
            <div class="col-6 col-md-2">
              <label class="form-label mb-1" style="font-size:0.78rem;">Max Price (₹)</label>
              <input type="number" class="form-control form-control-sm" v-model.number="app.trekFilterParams.maximum_price_inr" @change="app.loadOpenExpeditions(1)" placeholder="Any" min="0" />
            </div>
            <div class="col-6 col-md-2">
              <label class="form-label mb-1" style="font-size:0.78rem;">Max Duration (days)</label>
              <input type="number" class="form-control form-control-sm" v-model.number="app.trekFilterParams.maximum_duration_days" @change="app.loadOpenExpeditions(1)" placeholder="Any" min="1" />
            </div>
            <div class="col-md-2">
              <button class="btn btn-trek-outline btn-sm w-100" @click="app.clearTrekFilters">
                <i class="bi bi-x-circle me-1"></i>Clear
              </button>
            </div>
          </div>
        </div>

        <div class="row g-3">
          <div v-if="app.trekkerOpenExpeditions.length === 0 && !app.expeditionsLoading" class="col-12">
            <div class="empty-state glass-panel p-5">
              <div class="empty-state-icon">🔍</div>
              <p>No open expeditions match your filters. Try broadening your search!</p>
            </div>
          </div>
          <div v-if="app.expeditionsLoading" class="col-12 text-center py-5">
            <div class="trek-spinner mx-auto"></div>
            <p class="mt-3" style="color:var(--trek-text-muted);">Loading expeditions...</p>
          </div>
          <div class="col-md-6 col-lg-4 col-xl-3" v-for="exp in app.trekkerOpenExpeditions" :key="exp.trekking_route_expedition_id" class="animate-in">
            <div class="trek-card h-100">
              <div class="trek-card-image">
                <img v-if="exp.expedition_cover_image_url" :src="exp.expedition_cover_image_url" :alt="exp.expedition_route_name" loading="lazy" />
                <div v-else class="trek-card-image-placeholder">⛰️</div>
                <span class="trek-card-difficulty-badge trek-badge" :class="app.difficultyBadgeClass(exp.expedition_difficulty_level)">
                  {{ exp.expedition_difficulty_level }}
                </span>
              </div>
              <div class="trek-card-body d-flex flex-column">
                <div class="trek-card-name">{{ exp.expedition_route_name }}</div>
                <div class="trek-card-location">
                  <i class="bi bi-geo-alt-fill"></i>{{ exp.expedition_geographical_location }}
                </div>
                <div class="trek-meta-grid">
                  <div class="trek-meta-item">
                    <span class="meta-val">{{ exp.expedition_duration_in_days }}d</span>
                    <span class="meta-key">Duration</span>
                  </div>
                  <div class="trek-meta-item">
                    <span class="meta-val">₹{{ exp.expedition_price_per_person_inr?.toLocaleString() || 'Free' }}</span>
                    <span class="meta-key">Per Person</span>
                  </div>
                  <div class="trek-meta-item">
                    <span class="meta-val">{{ exp.available_participant_slots_remaining }}</span>
                    <span class="meta-key">Slots Left</span>
                  </div>
                  <div class="trek-meta-item">
                    <span class="meta-val" style="font-size:0.78rem;">{{ app.formatDate(exp.expedition_scheduled_start_date) }}</span>
                    <span class="meta-key">Start</span>
                  </div>
                </div>
                <div class="trek-slot-bar mb-2 mt-auto">
                  <div class="trek-slot-fill" :style="{ width: app.slotFillPercent(exp) + '%' }"></div>
                </div>
                <button class="btn btn-trek-primary btn-sm w-100" @click="app.openBookingModal(exp)">
                  <i class="bi bi-calendar-plus me-2"></i>Book Now
                </button>
              </div>
            </div>
          </div>
        </div>

        <div class="d-flex justify-content-center mt-4 gap-2" v-if="app.openTreksPagination.total_pages > 1">
          <button class="btn btn-trek-outline btn-sm" :disabled="app.openTreksPagination.current_page <= 1" @click="app.loadOpenExpeditions(app.openTreksPagination.current_page - 1)">
            <i class="bi bi-chevron-left"></i>
          </button>
          <span class="btn btn-sm" style="background:var(--trek-surface);color:var(--trek-text-secondary);cursor:default;border-radius:8px;border:1px solid rgba(76,175,80,0.15);">
            {{ app.openTreksPagination.current_page }} / {{ app.openTreksPagination.total_pages }}
          </span>
          <button class="btn btn-trek-outline btn-sm" :disabled="!app.openTreksPagination.has_next_page" @click="app.loadOpenExpeditions(app.openTreksPagination.current_page + 1)">
            <i class="bi bi-chevron-right"></i>
          </button>
        </div>
      </div>

         TREKKER: BOOKING HISTORY
      ==================================================== -->
      <div v-if="app.currentView === 'bookings'" class="animate-in">
        <div class="section-header">
          <h2 class="section-title">My <span>Bookings</span></h2>
          <div class="d-flex gap-2 flex-wrap">
            <select class="form-select form-select-sm" v-model="app.bookingStatusFilter" @change="app.loadTrekkerBookings" style="width:auto;font-size:0.83rem;">
              <option value="">All Statuses</option>
              <option value="Booked">Booked</option>
              <option value="Completed">Completed</option>
              <option value="Cancelled">Cancelled</option>
            </select>
            <button class="btn btn-trek-outline btn-sm" @click="app.triggerBookingCsvExport" :disabled="app.csvExportLoading">
              <span v-if="app.csvExportLoading"><span class="spinner-border spinner-border-sm me-1"></span>Exporting...</span>
              <span v-else><i class="bi bi-file-earmark-csv me-1"></i>Export CSV</span>
            </button>
          </div>
        </div>

        <div v-if="app.trekkerAllBookings.length === 0" class="empty-state glass-panel p-5">
          <div class="empty-state-icon">📋</div>
          <p>No bookings yet. <a href="#" @click.prevent="app.navigateTo('trekker-explore')" class="text-trek-primary">Explore treks →</a></p>
        </div>

        <div class="row g-3" v-else>
          <div class="col-md-6" v-for="bk in app.trekkerAllBookings" :key="bk.participant_booking_record_id">
            <div class="glass-panel p-3" style="border-radius:var(--trek-radius-md);">
              <div class="d-flex justify-content-between align-items-start mb-2">
                <div>
                  <div style="font-weight:700;color:var(--trek-text-primary);">{{ bk.expedition_route_name }}</div>
                  <div style="font-size:0.78rem;color:var(--trek-text-muted);">
                    <i class="bi bi-geo-alt-fill me-1" style="color:var(--trek-primary);"></i>{{ bk.expedition_geographical_location }}
                  </div>
                </div>
                <span class="trek-badge" :class="app.bookingBadgeClass(bk.current_booking_lifecycle_status)">
                  {{ bk.current_booking_lifecycle_status }}
                </span>
              </div>
              <div class="row g-2 mb-2" style="font-size:0.78rem;color:var(--trek-text-muted);">
                <div class="col-6"><i class="bi bi-tag me-1"></i>Ref: <code style="color:var(--trek-primary);font-size:0.75rem;">{{ bk.booking_confirmation_reference_code }}</code></div>
                <div class="col-6"><i class="bi bi-calendar me-1"></i>Start: {{ app.formatDate(bk.expedition_scheduled_start_date) }}</div>
                <div class="col-6"><i class="bi bi-speedometer me-1"></i>{{ bk.expedition_difficulty_level }}</div>
                <div class="col-6"><i class="bi bi-currency-rupee me-1"></i>₹{{ bk.expedition_price_per_person_inr?.toLocaleString() }}</div>
              </div>
              <div v-if="bk.current_booking_lifecycle_status === 'Booked'" class="mt-2">
                <button class="btn btn-trek-danger btn-sm w-100" @click="app.openCancelBookingModal(bk)">
                  <i class="bi bi-x-circle me-1"></i>Cancel Booking
                </button>
              </div>
              <div v-if="bk.cancellation_reason_description" class="mt-2" style="font-size:0.75rem;color:var(--trek-text-muted);padding:6px 8px;background:rgba(239,83,80,0.05);border-radius:6px;">
                <i class="bi bi-info-circle me-1"></i>{{ bk.cancellation_reason_description }}
              </div>
            </div>
          </div>
        </div>
      </div>

      <div class="modal fade" id="bookingModal" tabindex="-1" aria-labelledby="bookingModalLabel" aria-hidden="true">
        <div class="modal-dialog modal-dialog-centered">
          <div class="modal-content">
            <div class="modal-header">
              <h5 class="modal-title" id="bookingModalLabel">
                <i class="bi bi-calendar-plus me-2" style="color:var(--trek-primary);"></i>Book Expedition
              </h5>
              <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
            </div>
            <div class="modal-body" v-if="app.selectedExpeditionForBooking">
              <div v-if="app.bookingStep === 1">
                <div class="p-3 mb-3" style="background:rgba(76,175,80,0.06);border-radius:12px;border:1px solid rgba(76,175,80,0.12);">
                  <h6 style="font-weight:700;color:var(--trek-text-primary);">{{ app.selectedExpeditionForBooking.expedition_route_name }}</h6>
                  <div class="row g-2 mt-1" style="font-size:0.82rem;color:var(--trek-text-muted);">
                    <div class="col-6"><i class="bi bi-geo-alt me-1"></i>{{ app.selectedExpeditionForBooking.expedition_geographical_location }}</div>
                    <div class="col-6"><i class="bi bi-calendar me-1"></i>{{ app.formatDate(app.selectedExpeditionForBooking.expedition_scheduled_start_date) }}</div>
                    <div class="col-6"><i class="bi bi-speedometer me-1"></i>{{ app.selectedExpeditionForBooking.expedition_difficulty_level }}</div>
                    <div class="col-6"><i class="bi bi-clock me-1"></i>{{ app.selectedExpeditionForBooking.expedition_duration_in_days }} days</div>
                  </div>
                </div>
                <div class="mb-3">
                  <label class="form-label">Number of Participants</label>
                  <div class="d-flex align-items-center gap-3">
                    <button type="button" class="btn btn-trek-outline btn-sm" @click="app.bookingParticipants = Math.max(1, app.bookingParticipants - 1)">−</button>
                    <span style="font-size:1.2rem;font-weight:700;color:var(--trek-text-primary);min-width:30px;text-align:center;">{{ app.bookingParticipants }}</span>
                    <button type="button" class="btn btn-trek-outline btn-sm" @click="app.bookingParticipants = Math.min(Math.min(10, app.selectedExpeditionForBooking.available_participant_slots_remaining), app.bookingParticipants + 1)">+</button>
                    <span style="font-size:0.78rem;color:var(--trek-text-muted);">(Max: {{ Math.min(10, app.selectedExpeditionForBooking.available_participant_slots_remaining) }})</span>
                  </div>
                </div>
                <div class="mb-3">
                  <label class="form-label">Special Requirements <span style="color:var(--trek-text-muted);font-weight:400;">(optional)</span></label>
                  <textarea class="form-control" rows="2" v-model="app.bookingSpecialNote" placeholder="Dietary restrictions, accessibility needs..."></textarea>
                </div>
                <div class="p-3 mb-1" style="background:rgba(255,213,79,0.07);border-radius:10px;border:1px solid rgba(255,213,79,0.2);">
                  <div class="d-flex justify-content-between">
                    <span style="font-size:0.9rem;color:var(--trek-text-muted);">Price per person</span>
                    <span style="font-weight:700;color:var(--trek-text-primary);">₹{{ app.selectedExpeditionForBooking.expedition_price_per_person_inr?.toLocaleString() }}</span>
                  </div>
                  <div class="d-flex justify-content-between mt-1">
                    <span style="font-size:0.9rem;color:var(--trek-text-muted);">× {{ app.bookingParticipants }} participant(s)</span>
                    <span style="font-weight:800;font-size:1.1rem;" class="text-trek-accent">
                      ₹{{ (app.selectedExpeditionForBooking.expedition_price_per_person_inr * app.bookingParticipants).toLocaleString() }}
                    </span>
                  </div>
                </div>
              </div>
              <div v-if="app.bookingStep === 2">
                <div class="payment-card-preview mb-4">
                  <div class="d-flex justify-content-between align-items-start mb-3">
                    <div class="payment-card-chip">💳</div>
                    <div style="font-size:0.7rem;color:rgba(200,230,201,0.6);letter-spacing:1px;">SIMULATED</div>
                  </div>
                  <div class="payment-card-number mb-2">•••• •••• •••• 4242</div>
                  <div style="font-size:0.75rem;color:rgba(200,230,201,0.7);">TREKKER / SIMULATION MODE</div>
                </div>
                <div class="mb-3">
                  <label class="form-label">Card Number (Simulated)</label>
                  <input type="text" class="form-control" value="4242 4242 4242 4242" readonly />
                </div>
                <div class="row g-2 mb-3">
                  <div class="col-6">
                    <label class="form-label">Expiry</label>
                    <input type="text" class="form-control" value="12/27" readonly />
                  </div>
                  <div class="col-6">
                    <label class="form-label">CVV</label>
                    <input type="text" class="form-control" value="•••" readonly />
                  </div>
                </div>
                <div class="alert py-2" style="background:rgba(41,182,246,0.08);border-color:rgba(41,182,246,0.2);color:#29b6f6;border-radius:8px;font-size:0.82rem;">
                  <i class="bi bi-info-circle me-2"></i>Simulated payment. No real transaction occurs. Total: <strong>₹{{ (app.selectedExpeditionForBooking.expedition_price_per_person_inr * app.bookingParticipants).toLocaleString() }}</strong>
                </div>
              </div>
              <div v-if="app.bookingStep === 3" class="text-center py-4">
                <div class="trek-spinner mx-auto mb-3"></div>
                <p style="color:var(--trek-text-muted);">Processing your booking...</p>
              </div>
            </div>
            <div class="modal-footer">
              <button type="button" class="btn btn-trek-outline" data-bs-dismiss="modal" v-if="app.bookingStep < 3">Cancel</button>
              <button v-if="app.bookingStep === 1 && app.selectedExpeditionForBooking?.expedition_price_per_person_inr > 0" class="btn btn-trek-primary" @click="app.bookingStep = 2">
                <i class="bi bi-credit-card me-2"></i>Proceed to Payment
              </button>
              <button v-else-if="app.bookingStep === 1" class="btn btn-trek-primary" @click="app.handleConfirmBooking">
                <i class="bi bi-check-circle me-2"></i>Confirm Booking
              </button>
              <button v-if="app.bookingStep === 2" class="btn btn-trek-primary" @click="app.handleConfirmBooking">
                <i class="bi bi-lock me-2"></i>Pay & Confirm
              </button>
            </div>
          </div>
        </div>
      </div>

      <div class="modal fade" id="cancelBookingModal" tabindex="-1" aria-hidden="true">
        <div class="modal-dialog modal-dialog-centered modal-sm">
          <div class="modal-content">
            <div class="modal-header">
              <h5 class="modal-title"><i class="bi bi-x-circle me-2" style="color:var(--trek-danger);"></i>Cancel Booking</h5>
              <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
            </div>
            <div class="modal-body" v-if="app.selectedBookingForCancellation">
              <p style="font-size:0.9rem;color:var(--trek-text-secondary);">Cancel booking for <strong>{{ app.selectedBookingForCancellation.expedition_route_name }}</strong>?</p>
              <div class="mb-3">
                <label class="form-label">Reason <span style="color:var(--trek-text-muted);font-weight:400;">(optional)</span></label>
                <textarea class="form-control" rows="2" v-model="app.cancellationReason" placeholder="Why are you cancelling?"></textarea>
              </div>
            </div>
            <div class="modal-footer">
              <button class="btn btn-trek-outline" data-bs-dismiss="modal">Keep Booking</button>
              <button class="btn btn-trek-danger" @click="app.handleConfirmCancellation" :disabled="app.cancellationSubmitting">
                <span v-if="app.cancellationSubmitting"><span class="spinner-border spinner-border-sm me-2"></span></span>
                <i v-else class="bi bi-x-circle me-1"></i>Cancel Booking
              </button>
            </div>
          </div>
        </div>
      </div>

    </div>
  `
};
