const requests = [
  { initials: 'AL', name: 'Avery Lee', pickup: 'North Gate', route: 'North Gate → Student Union', time: '4 min ago', tone: '' },
  { initials: 'KS', name: 'Kai Santos', pickup: 'Library entrance', route: 'Library entrance → East Parking', time: '2 min ago', tone: 'yellow' },
  { initials: 'MR', name: 'Maya Rivera', pickup: 'West Residences', route: 'West Residences → Arts Quad', time: 'Just now', tone: 'blue' }
];

const requestList = document.querySelector('#request-list');
const waitingCount = document.querySelector('#waiting-count');
const walkingCount = document.querySelector('#walking-count');
const requestBadge = document.querySelector('#request-badge');
const toast = document.querySelector('#toast');
const departureTime = document.querySelector('#departure-time');
const departureAlertButton = document.querySelector('#departure-alert-btn');
const studentAlertTitle = document.querySelector('#student-alert-title');
const studentAlertDetail = document.querySelector('#student-alert-detail');
const studentAlertTime = document.querySelector('#student-alert-time');
const studentDepartureTime = document.querySelector('#student-departure-time');
const studentVanLocation = document.querySelector('#student-van-location');
const studentVanLocationTime = document.querySelector('#student-van-location-time');
const vanFullReturnButton = document.querySelector('#van-full-return-btn');
const noRidesButton = document.querySelector('#no-rides-btn');
const accessForm = document.querySelector('#access-form');
const accessHistory = document.querySelector('#access-history');
const accessCount = document.querySelector('#access-count');
const accessFormMessage = document.querySelector('#access-form-message');
const accessStorageKey = 'arc-van-driver-access';
const studentSignupQr = document.querySelector('#student-signup-qr');
const qrUrl = document.querySelector('#qr-url');
const studentSignupForm = document.querySelector('#student-signup-form');
const signupMessage = document.querySelector('#signup-message');
const signupStorageKey = 'arc-van-alert-signups';
const headingToVanForm = document.querySelector('#heading-to-van-form');
const headingMessage = document.querySelector('#heading-message');
const driverPin = '045048';
const driverAuthKey = 'arc-van-driver-auth';

function isDriverAuthenticated() {
  return sessionStorage.getItem(driverAuthKey) === 'true';
}
function setDriverAuthenticated(val) {
  if (val) sessionStorage.setItem(driverAuthKey, 'true'); else sessionStorage.removeItem(driverAuthKey);
}

function updateDriverControls() {
  const driverView = document.querySelector('#driver-view');
  if (!driverView) return;
  const controls = driverView.querySelectorAll('.location-btn, .destination-btn, #send-other-alert, #send-destination-other, #announce-btn, .departure-option, #departure-alert-btn, #van-full-return-btn, #no-rides-btn, .request-alert-btn, #access-form button, #driver-name, #driver-email');
  const enabled = isDriverAuthenticated();
  controls.forEach((el) => {
    try { el.disabled = !enabled; } catch (e) {}
    el.classList.toggle('locked', !enabled);
  });
}

function showPinModal(message) {
  const modal = document.querySelector('#driver-pin-modal');
  if (!modal) return;
  modal.classList.add('visible');
  modal.setAttribute('aria-hidden', 'false');
  const err = modal.querySelector('.pin-error');
  if (err) err.textContent = message || '';
  const input = modal.querySelector('.pin-input');
  if (input) { input.value = ''; input.focus(); }
}
function hidePinModal() {
  const modal = document.querySelector('#driver-pin-modal');
  if (!modal) return;
  modal.classList.remove('visible');
  modal.setAttribute('aria-hidden', 'true');
}

// Wire up modal behavior once DOM is ready
window.addEventListener('load', () => {
  updateDriverControls();
  // Show PIN modal when switching to driver view if not authenticated
  document.querySelectorAll('[data-view]').forEach((button) => {
    button.addEventListener('click', () => {
      if (button.dataset.view === 'driver' && !isDriverAuthenticated()) {
        showPinModal('Enter driver PIN to unlock console');
      }
    });
  });

  const modal = document.querySelector('#driver-pin-modal');
  if (modal) {
    modal.querySelector('.pin-submit').addEventListener('click', () => {
      const val = modal.querySelector('.pin-input').value.trim();
      if (val === driverPin) {
        setDriverAuthenticated(true);
        hidePinModal();
        updateDriverControls();
        showToast('Driver console unlocked');
      } else {
        modal.querySelector('.pin-error').textContent = 'Invalid PIN';
        modal.querySelector('.pin-input').focus();
      }
    });
    modal.querySelector('.pin-cancel').addEventListener('click', () => { hidePinModal(); });
    modal.querySelector('.pin-input').addEventListener('keydown', (e) => { if (e.key === 'Enter') modal.querySelector('.pin-submit').click(); });
  }

  // Prevent interaction with locked controls and open PIN modal instead
  const driverView = document.querySelector('#driver-view');
  if (driverView) {
    driverView.addEventListener('click', (e) => {
      if (isDriverAuthenticated()) return;
      const target = e.target.closest('.location-btn, .destination-btn, #send-other-alert, #send-destination-other, #announce-btn, .departure-option, #departure-alert-btn, #van-full-return-btn, #no-rides-btn, .request-alert-btn, #access-form button');
      if (target) {
        e.preventDefault();
        e.stopPropagation();
        showPinModal('Driver PIN required');
      }
    }, true);
  }
});
let latestStudentAlertId = 0;
let currentVanLocation = '';

function displayVanName(text) {
  return (text || '').replace(/Van 02|VAN 02/g, '045/048 Van');
}

let accessGrants = loadAccessGrants();

function getSignupUrl() {
  return `${window.location.href.split('#')[0]}#student-signup`;
}

function setSignupMessage(message, isError = false) {
  signupMessage.textContent = message;
  signupMessage.classList.toggle('error', isError);
}

studentSignupQr.src = `https://api.qrserver.com/v1/create-qr-code/?size=312x312&margin=8&data=${encodeURIComponent(getSignupUrl())}`;
qrUrl.textContent = getSignupUrl();

studentSignupForm.addEventListener('submit', (event) => {
  event.preventDefault();
  const name = studentSignupForm.elements.name.value.trim();
  const email = studentSignupForm.elements.email.value.trim().toLowerCase();
  if (!name || !email || !studentSignupForm.elements.email.validity.valid) {
    setSignupMessage('Enter your name and a valid email address.', true);
    return;
  }
  fetch('/api/alerts/signup', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, email })
  }).then((response) => {
    if (!response.ok) throw new Error('Signup failed');
    const signups = JSON.parse(localStorage.getItem(signupStorageKey) || '[]');
    signups.push({ name, email, signedUpAt: new Date().toISOString(), van: '045/048 Van' });
    localStorage.setItem(signupStorageKey, JSON.stringify(signups));
    studentSignupForm.reset();
    setSignupMessage('You are signed up. We will alert you about 045/048 Van updates.');
  }).catch(() => setSignupMessage('Signup is unavailable right now. Please try again.', true));
});

headingToVanForm.addEventListener('submit', (event) => {
  event.preventDefault();
  const name = headingToVanForm.elements.name.value.trim();
  const email = headingToVanForm.elements.email.value.trim().toLowerCase();
  if (!name || !email || !headingToVanForm.elements.email.validity.valid) {
    setHeadingMessage('Enter your name and a valid email address.', true);
    return;
  }
  fetch('/api/student/heading-to-van', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, email })
  }).then((response) => {
    if (!response.ok) throw new Error('Request failed');
    headingToVanForm.reset();
    setHeadingMessage('Driver notified! You\'re on the list.');
    updateWalkingCount();
  }).catch(() => setHeadingMessage('Request failed. Please try again.', true));
});

function setHeadingMessage(message, isError = false) {
  headingMessage.textContent = message;
  headingMessage.classList.toggle('error', isError);
}

function updateWalkingCount() {
  fetch('/api/status', { cache: 'no-store' })
    .then((response) => response.json())
    .then((data) => {
      if (data.walking_count !== undefined) {
        walkingCount.innerHTML = `${data.walking_count} <small>students</small>`;
      }
    })
    .catch(() => {});
}

function resetDriverCounts() {
  waitingCount.innerHTML = '0 <small>students</small>';
  walkingCount.innerHTML = '0 <small>students</small>';
  fetch('/api/driver/clear-walking', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ pin: driverPin, request_id: 0, new_status: '' })
  }).catch(() => {});
}

async function sendDriverAlert(title, detail, toastMessage, location = null) {
  const response = await fetch('/api/driver/broadcast', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ pin: driverPin, current_stop: location || 'North Gate', next_stop: location || 'North Gate', eta_mins: 0, title, detail, location })
  });
  if (!response.ok) throw new Error('Alert failed');
  showToast(toastMessage);
}

async function pollStudentAlert() {
  try {
    const response = await fetch('/api/alerts/latest', { cache: 'no-store' });
    if (!response.ok) return;
    const alert = await response.json();
    if (!alert.id || alert.id === latestStudentAlertId) return;
    latestStudentAlertId = alert.id;
    studentAlertTitle.textContent = displayVanName(alert.title);
    studentAlertDetail.textContent = displayVanName(alert.detail);
    studentAlertTime.textContent = 'Just now';
    const departureMatch = alert.title && alert.title.match(/departs at (.+)$/i);
    if (departureMatch && studentDepartureTime) studentDepartureTime.textContent = departureMatch[1];
    if (alert.location && studentVanLocation) {
      studentVanLocation.textContent = alert.location;
      if (studentVanLocationTime) {
        studentVanLocationTime.textContent = alert.created_at ? `Updated ${formatAlertTime(alert.created_at)}` : 'Updated just now';
      }
    }
  } catch {
    // Keep the student view usable while the server is temporarily unavailable.
  }
}

pollStudentAlert();
window.setInterval(pollStudentAlert, 5000);

function formatAlertTime(timestamp) {
  const adjustedTimestamp = new Date(new Date(timestamp).getTime() - 4 * 60 * 60 * 1000);
  return new Intl.DateTimeFormat(undefined, { hour: 'numeric', minute: '2-digit' }).format(adjustedTimestamp);
}

function loadAccessGrants() {
  try {
    const storedGrants = JSON.parse(localStorage.getItem(accessStorageKey) || '[]');
    return Array.isArray(storedGrants) ? storedGrants.filter((grant) => grant && grant.name && grant.email && grant.grantedAt) : [];
  } catch {
    return [];
  }
}

function formatGrantTime(timestamp) {
  return new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(timestamp));
}

function escapeHtml(value) {
  return value.replace(/[&<>'"]/g, (character) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' }[character]));
}

function renderAccessHistory() {
  const sortedGrants = [...accessGrants].sort((first, second) => new Date(second.grantedAt) - new Date(first.grantedAt));
  accessCount.textContent = `${sortedGrants.length} ${sortedGrants.length === 1 ? 'grant' : 'grants'}`;
  accessHistory.innerHTML = sortedGrants.length ? sortedGrants.map((grant) => `
    <div class="access-entry">
      <div class="request-avatar access-avatar">${escapeHtml(grant.name.split(' ').map((part) => part[0]).join('').slice(0, 2).toUpperCase())}</div>
      <div class="access-entry-info"><strong>${escapeHtml(grant.name)}</strong><span>${escapeHtml(grant.email)}</span><small>Granted by ${escapeHtml(grant.grantedBy || 'Jordan Miles')}</small></div>
      <div class="access-entry-meta"><span class="access-scope">FULL CONSOLE</span><time datetime="${grant.grantedAt}">${formatGrantTime(grant.grantedAt)}</time></div>
    </div>`).join('') : '<p class="access-empty">No drivers have been granted access yet.</p>';
}

function setAccessMessage(message, isError = false) {
  accessFormMessage.textContent = message;
  accessFormMessage.classList.toggle('error', isError);
}

accessForm.addEventListener('submit', (event) => {
  event.preventDefault();
  const name = accessForm.elements.name.value.trim();
  const email = accessForm.elements.email.value.trim().toLowerCase();
  if (!name || !email || !accessForm.elements.email.validity.valid) {
    setAccessMessage('Enter a driver name and a valid email address.', true);
    return;
  }
  if (accessGrants.some((grant) => grant.email.toLowerCase() === email)) {
    setAccessMessage('That driver already has access.', true);
    return;
  }
  const grant = { id: crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random()}`, name, email, grantedBy: 'Jordan Miles', grantedAt: new Date().toISOString(), permission: 'full-console' };
  accessGrants.push(grant);
  localStorage.setItem(accessStorageKey, JSON.stringify(accessGrants));
  accessForm.reset();
  renderAccessHistory();
  setAccessMessage(`Access granted to ${name}.`);
  showToast(`Driver access granted to ${name}`);
});

function renderRequests() {
  requestList.innerHTML = requests.map((request) => `
    <div class="request-item">
      <div class="request-avatar ${request.tone}">${request.initials}</div>
      <div class="request-info"><strong>${request.name}</strong><span>${request.route}</span></div>
      <span class="request-time">${request.time}</span>
      <button class="request-alert-btn" data-student="${request.name}" data-pickup="${request.pickup}" title="Alert ${request.name}">Alert student</button>
    </div>`).join('');
  requestBadge.textContent = requests.length;
  waitingCount.innerHTML = `${requests.length} <small>students</small>`;
}

function showToast(message) {
  toast.textContent = message;
  toast.classList.add('show');
  window.setTimeout(() => toast.classList.remove('show'), 3000);
}

function switchView(view) {
  document.querySelectorAll('.view').forEach((section) => section.classList.remove('active-view'));
  document.querySelector(`#${view}-view`).classList.add('active-view');
  document.querySelectorAll('[data-view]').forEach((button) => button.classList.toggle('active', button.dataset.view === view));
  document.querySelector('#page-title').innerHTML = view === 'driver' ? 'Monitor the App and be Accurate <span>✦</span>' : 'Your ride, on your time <span>✦</span>';
}

document.querySelectorAll('[data-view]').forEach((button) => button.addEventListener('click', () => switchView(button.dataset.view)));
function showDestinationStep(location) {
  currentVanLocation = location;
  document.querySelector('#location-prompt').textContent = `Step 2: The Van is going to... (currently at ${location})`;
  document.querySelector('#destination-controls').classList.add('visible');
  document.querySelector('#other-location').classList.remove('visible');
}

function resetLocationWorkflow() {
  currentVanLocation = '';
  document.querySelector('#location-prompt').textContent = 'Step 1: Choose where the Van is now.';
  document.querySelector('#destination-controls').classList.remove('visible');
  document.querySelector('#other-location').classList.remove('visible');
  document.querySelector('#other-destination').classList.remove('visible');
  document.querySelector('#other-location-input').value = '';
  document.querySelector('#other-destination-input').value = '';
}

function sendLocationUpdate(destination) {
  const currentLocation = currentVanLocation;
  sendDriverAlert(`045/048 Van is at ${currentLocation}`, `The Van is going to ${destination}.`, `Student alert sent: ${currentLocation} to ${destination}`, currentLocation)
    .then(resetLocationWorkflow)
    .catch(() => showToast('Unable to send student alert'));
}

document.querySelectorAll('.location-btn').forEach((button) => button.addEventListener('click', () => {
  resetDriverCounts();
  const otherLocation = document.querySelector('#other-location');
  if (button.dataset.location === 'Other') {
    otherLocation.classList.toggle('visible');
    if (otherLocation.classList.contains('visible')) document.querySelector('#other-location-input').focus();
    return;
  }
  showDestinationStep(button.dataset.location);
}));
document.querySelector('#send-other-alert').addEventListener('click', () => {
  resetDriverCounts();
  const input = document.querySelector('#other-location-input');
  const location = input.value.trim();
  if (!location) {
    input.focus();
    return;
  }
  showDestinationStep(location);
});
document.querySelectorAll('.destination-btn').forEach((button) => button.addEventListener('click', () => {
  resetDriverCounts();
  const otherDestination = document.querySelector('#other-destination');
  if (button.dataset.location === 'Other') {
    otherDestination.classList.toggle('visible');
    if (otherDestination.classList.contains('visible')) document.querySelector('#other-destination-input').focus();
    return;
  }
  sendLocationUpdate(button.dataset.location);
}));
document.querySelector('#send-destination-other').addEventListener('click', () => {
  resetDriverCounts();
  const input = document.querySelector('#other-destination-input');
  const destination = input.value.trim();
  if (!destination) {
    input.focus();
    return;
  }
  sendLocationUpdate(destination);
});
const announceButton = document.querySelector('#announce-btn');
if (announceButton) announceButton.addEventListener('click', () => sendDriverAlert('Boarding update', 'Students waiting for 045/048 Van may board now.', 'Boarding update sent to students').catch(() => showToast('Unable to send student alert')));
document.querySelectorAll('.departure-option').forEach((button) => button.addEventListener('click', () => {
  document.querySelectorAll('.departure-option').forEach((option) => option.classList.remove('active'));
  button.classList.add('active');
  departureTime.textContent = `${button.dataset.wait} min`;
}));
departureAlertButton.addEventListener('click', () => {
  const waitTime = document.querySelector('.departure-option.active').dataset.wait;
  const departure = new Date(Date.now() + Number(waitTime) * 60000);
  const departureLabel = departure.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
  studentAlertTitle.textContent = `045/048 Van departs at ${departureLabel}`;
  studentAlertDetail.textContent = `The driver expects to leave in about ${waitTime} minutes.`;
  studentDepartureTime.textContent = departureLabel;
  studentAlertTime.textContent = 'Just now';
  sendDriverAlert(`045/048 Van departs at ${departureLabel}`, `The driver expects to leave in about ${waitTime} minutes.`, `Students alerted: departure expected at ${departureLabel}`).catch(() => showToast('Unable to send student alert'));
  departureAlertButton.textContent = 'Students alerted';
  departureAlertButton.disabled = true;
  window.setTimeout(() => {
    departureAlertButton.textContent = 'Alert students';
    departureAlertButton.disabled = false;
  }, 3000);
});
function sendAvailabilityAlert(title, detail, toastMessage, button) {
  studentAlertTitle.textContent = title;
  studentAlertDetail.textContent = detail;
  studentAlertTime.textContent = 'Just now';
  sendDriverAlert(title, detail, toastMessage).catch(() => showToast('Unable to send student alert'));
  button.classList.add('sent');
  window.setTimeout(() => button.classList.remove('sent'), 3000);
}

vanFullReturnButton.addEventListener('click', () => sendAvailabilityAlert(
  '045/048 Van is currently full',
  'The driver will return for more rides shortly.',
  'Students alerted: the van is full and will be back soon',
  vanFullReturnButton
));

noRidesButton.addEventListener('click', () => sendAvailabilityAlert(
  'No rides available right now',
  'Please check back later for the next available ride.',
  'Students alerted: no rides are available at this time',
  noRidesButton
));
if (requestList) requestList.addEventListener('click', (event) => {
  const button = event.target.closest('.request-alert-btn');
  if (!button) return;
  showToast(`Alert sent to ${button.dataset.student}: 045/048 Van is at ${button.dataset.pickup}`);
  button.textContent = 'Alert sent';
  button.disabled = true;
});

if (requestList) renderRequests();
renderAccessHistory();
updateDriverControls();
updateWalkingCount();
window.setInterval(updateWalkingCount, 5000);
if (window.location.hash === '#student-signup') {
  switchView('student');
  document.querySelector('#student-signup').scrollIntoView({ behavior: 'smooth' });
}
// ----- ntfy push-alert integration -----
// Fetch the server's ntfy topic config and populate the driver + student
// info panels (topic names, subscribe URLs, and QR codes).
(function initNtfyPanels() {
  const qrApi = 'https://api.qrserver.com/v1/create-qr-code/?size=312x312&margin=8&data=';
  const driverTopic = document.querySelector('#ntfy-students-topic');
  const driverUrl = document.querySelector('#ntfy-students-url');
  const driverQr = document.querySelector('#ntfy-students-qr');
  const studentTopic = document.querySelector('#ntfy-student-topic');
  const studentUrl = document.querySelector('#ntfy-student-url');
  const studentQr = document.querySelector('#ntfy-student-qr');

  function paint(cfg) {
    const s = cfg && cfg.students;
    const d = cfg && cfg.driver;
    if (s && s.topic) {
      if (driverTopic) driverTopic.textContent = s.topic;
      if (studentTopic) studentTopic.textContent = s.topic;
      if (driverUrl) { driverUrl.textContent = s.url; driverUrl.href = s.url; }
      if (studentUrl) { studentUrl.textContent = s.url; studentUrl.href = s.url; }
      if (driverQr) driverQr.src = qrApi + encodeURIComponent(s.url);
      if (studentQr) studentQr.src = qrApi + encodeURIComponent(s.url);
    }
  }

  fetch('/api/ntfy/config', { cache: 'no-store' })
    .then((r) => (r.ok ? r.json() : null))
    .then((cfg) => { if (cfg) paint(cfg); })
    .catch(() => { /* keep the hardcoded defaults already in the HTML */ });
})();
