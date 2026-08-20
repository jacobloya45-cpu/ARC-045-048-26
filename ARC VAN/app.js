const requests = [
  { initials: 'AL', name: 'Avery Lee', pickup: 'North Gate', route: 'North Gate → Student Union', time: '4 min ago', tone: '' },
  { initials: 'KS', name: 'Kai Santos', pickup: 'Library entrance', route: 'Library entrance → East Parking', time: '2 min ago', tone: 'yellow' },
  { initials: 'MR', name: 'Maya Rivera', pickup: 'West Residences', route: 'West Residences → Arts Quad', time: 'Just now', tone: 'blue' }
];

const requestList = document.querySelector('#request-list');
const waitingCount = document.querySelector('#waiting-count');
const requestBadge = document.querySelector('#request-badge');
const toast = document.querySelector('#toast');
const departureTime = document.querySelector('#departure-time');
const departureAlertButton = document.querySelector('#departure-alert-btn');
const studentAlertTitle = document.querySelector('#student-alert-title');
const studentAlertDetail = document.querySelector('#student-alert-detail');
const studentAlertTime = document.querySelector('#student-alert-time');
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
const driverPin = '045048';
let latestStudentAlertId = 0;

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
    signups.push({ name, email, signedUpAt: new Date().toISOString(), van: 'Van 02' });
    localStorage.setItem(signupStorageKey, JSON.stringify(signups));
    studentSignupForm.reset();
    setSignupMessage('You are signed up. We will alert you about Van 02 updates.');
  }).catch(() => setSignupMessage('Signup is unavailable right now. Please try again.', true));
});

async function sendDriverAlert(title, detail, toastMessage) {
  const response = await fetch('/api/driver/broadcast', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ pin: driverPin, current_stop: 'North Gate', next_stop: 'North Gate', eta_mins: 0, title, detail })
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
    studentAlertTitle.textContent = alert.title;
    studentAlertDetail.textContent = alert.detail;
    studentAlertTime.textContent = 'Just now';
  } catch {
    // Keep the student view usable while the server is temporarily unavailable.
  }
}

pollStudentAlert();
window.setInterval(pollStudentAlert, 5000);

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
  document.querySelector('#page-title').innerHTML = view === 'driver' ? 'Good morning, Jordan <span>✦</span>' : 'Your ride, on your time <span>✦</span>';
}

document.querySelectorAll('[data-view]').forEach((button) => button.addEventListener('click', () => switchView(button.dataset.view)));
document.querySelectorAll('.location-btn').forEach((button) => button.addEventListener('click', () => {
  const otherLocation = document.querySelector('#other-location');
  if (button.dataset.location === 'Other') {
    otherLocation.classList.toggle('visible');
    if (otherLocation.classList.contains('visible')) document.querySelector('#other-location-input').focus();
    return;
  }
  otherLocation.classList.remove('visible');
  sendDriverAlert(`Van 02 is at ${button.dataset.location}`, `The van is currently at ${button.dataset.location}.`, `Student alert sent: Van 02 is at ${button.dataset.location}`).catch(() => showToast('Unable to send student alert'));
}));
document.querySelector('#send-other-alert').addEventListener('click', () => {
  const input = document.querySelector('#other-location-input');
  const location = input.value.trim();
  if (!location) {
    input.focus();
    return;
  }
  sendDriverAlert(`Van 02 is at ${location}`, `The van is currently at ${location}.`, `Student alert sent: ${location}`).catch(() => showToast('Unable to send student alert'));
  input.value = '';
  document.querySelector('#other-location').classList.remove('visible');
});
document.querySelector('#announce-btn').addEventListener('click', () => sendDriverAlert('Boarding update', 'Students waiting for Van 02 may board now.', 'Boarding update sent to students').catch(() => showToast('Unable to send student alert')));
document.querySelectorAll('.departure-option').forEach((button) => button.addEventListener('click', () => {
  document.querySelectorAll('.departure-option').forEach((option) => option.classList.remove('active'));
  button.classList.add('active');
  departureTime.textContent = `${button.dataset.wait} min`;
}));
departureAlertButton.addEventListener('click', () => {
  const waitTime = document.querySelector('.departure-option.active').dataset.wait;
  const departure = new Date(Date.now() + Number(waitTime) * 60000);
  const departureLabel = departure.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
  studentAlertTitle.textContent = `Van 02 departs at ${departureLabel}`;
  studentAlertDetail.textContent = `The driver expects to leave in about ${waitTime} minutes.`;
  studentAlertTime.textContent = 'Just now';
  sendDriverAlert(`Van 02 departs at ${departureLabel}`, `The driver expects to leave in about ${waitTime} minutes.`, `Students alerted: departure expected at ${departureLabel}`).catch(() => showToast('Unable to send student alert'));
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
  'Van 02 is currently full',
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
requestList.addEventListener('click', (event) => {
  const button = event.target.closest('.request-alert-btn');
  if (!button) return;
  showToast(`Alert sent to ${button.dataset.student}: Van 02 is at ${button.dataset.pickup}`);
  button.textContent = 'Alert sent';
  button.disabled = true;
});

renderRequests();
renderAccessHistory();
if (window.location.hash === '#student-signup') {
  switchView('student');
  document.querySelector('#student-signup').scrollIntoView({ behavior: 'smooth' });
}
