const requestList = document.querySelector('#request-list');
const waitingCount = document.querySelector('#waiting-count');
const walkingCount = document.querySelector('#walking-count');
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
const headingToVanForm = document.querySelector('#heading-to-van-form');
const driverRequestList = document.querySelector('#driver-request-list');
const driverWalkerList = document.querySelector('#driver-walker-list');
const clearAllWalkersBtn = document.querySelector('#clear-all-walkers-btn');

const driverPocForm = document.querySelector('#driver-poc-form');
const driverPocNameInput = document.querySelector('#driver-poc-name');
const driverPocContactInput = document.querySelector('#driver-poc-contact');
const driverPocClearBtn = document.querySelector('#driver-poc-clear');

const studentDisplayDriverName = document.querySelector('#student-display-driver-name');
const studentDisplayDriverContact = document.querySelector('#student-display-driver-contact');
const studentPocActionContainer = document.querySelector('#student-poc-action-container');
const sidebarDriverName = document.querySelector('#sidebar-driver-name');
const sidebarDriverAvatar = document.querySelector('#sidebar-driver-avatar');

const driverAppQr = document.querySelector('#driver-app-qr');
const studentAppQr = document.querySelector('#student-app-qr');
const driverQrUrl = document.querySelector('.driver-qr-url');
const studentQrUrl = document.querySelector('.student-qr-url');

const driverAuthKey = 'arc-van-driver-auth';
const driverPinKey = 'arc-van-driver-token';

let currentVanLocation = '';
let studentSelectedPickup = '';
let socket = null;
let heartbeatTimer = null;

function initQRCodes() {
  const currentUrl = window.location.origin;
  const qrApiUrl = `https://api.qrserver.com/v1/create-qr-code/?size=312x312&margin=8&data=${encodeURIComponent(currentUrl)}`;

  if (driverAppQr) driverAppQr.src = qrApiUrl;
  if (studentAppQr) studentAppQr.src = qrApiUrl;
  if (driverQrUrl) driverQrUrl.textContent = currentUrl;
  if (studentQrUrl) studentQrUrl.textContent = currentUrl;
}

function isDriverAuthenticated() {
  return sessionStorage.getItem(driverAuthKey) === 'true';
}

function getStoredDriverPin() {
  return sessionStorage.getItem(driverPinKey) || '';
}

function setDriverAuthenticated(token, pin) {
  if (token) {
    sessionStorage.setItem(driverAuthKey, 'true');
    sessionStorage.setItem(driverPinKey, pin);
  } else {
    sessionStorage.removeItem(driverAuthKey);
    sessionStorage.removeItem(driverPinKey);
  }
}

function updateDriverControls() {
  const driverView = document.querySelector('#driver-view');
  if (!driverView) return;
  const controls = driverView.querySelectorAll('.location-btn, .destination-btn, #send-other-alert, #send-destination-other, #announce-btn, .departure-option, #departure-alert-btn, #van-full-return-btn, #no-rides-btn, .request-alert-btn, #clear-all-walkers-btn, #driver-poc-form input, #driver-poc-form button');
  const authed = isDriverAuthenticated();
  controls.forEach((el) => {
    try { el.disabled = !authed; } catch (e) {}
    el.classList.toggle('locked', !authed);
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

function playAlertTone() {
  try {
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.type = 'sine';
    osc.frequency.setValueAtTime(587.33, ctx.currentTime);
    osc.frequency.setValueAtTime(880, ctx.currentTime + 0.1);
    gain.gain.setValueAtTime(0.15, ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.4);
    osc.start();
    osc.stop(ctx.currentTime + 0.4);
  } catch (e) {}
}

function initWebSocket() {
  if (socket && (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING)) {
    return;
  }

  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const wsUrl = `${protocol}//${window.location.host}/ws/alerts`;

  socket = new WebSocket(wsUrl);

  socket.onopen = () => {
    console.log('✅ Realtime WebSocket Connected');
    if (heartbeatTimer) clearInterval(heartbeatTimer);
    heartbeatTimer = setInterval(() => {
      if (socket && socket.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({ type: 'PING' }));
      }
    }, 15000);
  };

  socket.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      if (data.type === 'PONG') return;

      if (data.type === 'NEW_ALERT') {
        renderReceivedAlert(data.alert);
      } else if (data.type === 'REQUESTS_UPDATED') {
        renderDriverRequests(data.requests || []);
      } else if (data.type === 'WALKERS_UPDATED') {
        if (walkingCount) walkingCount.innerHTML = `${data.count} <small>students</small>`;
        renderDriverWalkers(data.walkers || []);
        if (data.new_name) {
          playAlertTone();
          showToast(`🚶 Incoming: ${data.new_name} is walking to the van!`);
        }
      } else if (data.type === 'POC_UPDATED') {
        renderDriverPOC(data.poc);
        showToast('Driver POC updated live');
      } else if (data.type === 'NEW_RIDE_REQUEST') {
        playAlertTone();
        showToast(`🚖 New Ride: ${data.name} (${data.pickup} → ${data.dropoff})`);
      }
    } catch (err) {
      console.error('Socket parse error', err);
    }
  };

  socket.onclose = () => {
    if (heartbeatTimer) clearInterval(heartbeatTimer);
    setTimeout(initWebSocket, 2000);
  };

  socket.onerror = () => {
    try { socket.close(); } catch (e) {}
  };
}

function renderReceivedAlert(alert) {
  playAlertTone();
  if (studentAlertTitle) studentAlertTitle.textContent = displayVanName(alert.title);
  if (studentAlertDetail) studentAlertDetail.textContent = displayVanName(alert.detail);
  if (studentAlertTime) studentAlertTime.textContent = 'Just now';

  const departureMatch = alert.title && alert.title.match(/departs at (.+)$/i);
  if (departureMatch && studentDepartureTime) {
    studentDepartureTime.textContent = departureMatch[1];
  }

  if (alert.location && studentVanLocation) {
    studentVanLocation.textContent = alert.location;
    if (studentVanLocationTime) studentVanLocationTime.textContent = 'Updated just now';
  }

  showToast(`🚐 ${alert.title}`);
}

function renderDriverPOC(poc) {
  if (!poc) return;
  const name = (poc.driver_name || '').trim();
  const contact = (poc.contact_info || '').trim();

  // Populate driver inputs if not actively being typed in
  if (driverPocNameInput && document.activeElement !== driverPocNameInput) {
    driverPocNameInput.value = name;
  }
  if (driverPocContactInput && document.activeElement !== driverPocContactInput) {
    driverPocContactInput.value = contact;
  }

  // Update sidebar branding
  if (sidebarDriverName) {
    sidebarDriverName.textContent = name || 'On-Duty Driver';
  }
  if (sidebarDriverAvatar) {
    sidebarDriverAvatar.textContent = name ? name.slice(0, 2).toUpperCase() : 'DV';
  }

  // Update student display
  if (studentDisplayDriverName) {
    studentDisplayDriverName.textContent = name ? `Duty Driver: ${name}` : '045/048 Duty Driver';
  }

  if (studentDisplayDriverContact) {
    if (contact) {
      studentDisplayDriverContact.innerHTML = `Direct Contact: <strong style="color:var(--coral); font-size: 14px;">${contact}</strong>`;
    } else {
      studentDisplayDriverContact.textContent = 'No direct phone/signal listed. Use the alert and request buttons below.';
    }
  }

  if (studentPocActionContainer) {
    if (contact) {
      const isPhone = contact.replace(/[^0-9]/g, '').length >= 7;
      if (isPhone) {
        studentPocActionContainer.innerHTML = `
          <a href="tel:${contact}" class="primary-btn" style="text-decoration:none; display:inline-block; padding:8px 14px; font-size:12px;">📞 Call Driver</a>
        `;
      } else {
        studentPocActionContainer.innerHTML = `
          <button class="secondary-btn" id="copy-poc-btn" type="button" style="padding:8px 12px; font-size:11px;">📋 Copy Contact</button>
        `;
        const copyBtn = document.querySelector('#copy-poc-btn');
        if (copyBtn) {
          copyBtn.addEventListener('click', () => {
            try {
              navigator.clipboard.writeText(contact);
            } catch (e) {
              const temp = document.createElement('input');
              temp.value = contact;
              document.body.appendChild(temp);
              temp.select();
              document.execCommand('copy');
              document.body.removeChild(temp);
            }
            showToast('Driver contact copied!');
          });
        }
      }
    } else {
      studentPocActionContainer.innerHTML = '';
    }
  }
}

function displayVanName(text) {
  return (text || '').replace(/Van 02|VAN 02/g, '045/048 Van');
}

window.addEventListener('load', () => {
  switchView('student');
  updateDriverControls();
  initWebSocket();
  initQRCodes();
  syncInitialData();

  document.querySelectorAll('[data-view]').forEach((button) => {
    button.addEventListener('click', () => {
      if (button.dataset.view === 'driver' && !isDriverAuthenticated()) {
        showPinModal('Enter Driver PIN to unlock console');
      } else {
        switchView(button.dataset.view);
        if (button.dataset.view === 'driver') syncInitialData();
      }
    });
  });

  const modal = document.querySelector('#driver-pin-modal');
  if (modal) {
    modal.querySelector('.pin-submit').addEventListener('click', async () => {
      const pinValue = modal.querySelector('.pin-input').value.trim();
      const errBox = modal.querySelector('.pin-error');
      
      try {
        const res = await fetch('/api/driver/verify-pin', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ pin: pinValue })
        });

        if (res.ok) {
          const data = await res.json();
          setDriverAuthenticated(data.token, pinValue);
          hidePinModal();
          updateDriverControls();
          switchView('driver');
          syncInitialData();
          showToast('Driver console unlocked');
        } else {
          errBox.textContent = 'Invalid PIN. Access denied.';
          modal.querySelector('.pin-input').focus();
        }
      } catch (err) {
        errBox.textContent = 'Connection error verifying PIN.';
      }
    });

    modal.querySelector('.pin-cancel').addEventListener('click', () => {
      hidePinModal();
      switchView('student');
    });

    modal.querySelector('.pin-input').addEventListener('keydown', (e) => {
      if (e.key === 'Enter') modal.querySelector('.pin-submit').click();
    });
  }

  const driverView = document.querySelector('#driver-view');
  if (driverView) {
    driverView.addEventListener('click', (e) => {
      if (isDriverAuthenticated()) return;
      const target = e.target.closest('.location-btn, .destination-btn, #send-other-alert, #send-destination-other, #announce-btn, .departure-option, #departure-alert-btn, #van-full-return-btn, #no-rides-btn, #clear-all-walkers-btn, #driver-poc-form button');
      if (target) {
        e.preventDefault();
        e.stopPropagation();
        showPinModal('Driver PIN required');
      }
    }, true);
  }
});

// Driver POC Form submit handler
if (driverPocForm) {
  driverPocForm.addEventListener('submit', (e) => {
    e.preventDefault();
    if (!isDriverAuthenticated()) return;
    const name = driverPocNameInput ? driverPocNameInput.value.trim() : '';
    const contact = driverPocContactInput ? driverPocContactInput.value.trim() : '';

    fetch('/api/driver/poc', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        pin: getStoredDriverPin(),
        driver_name: name,
        contact_info: contact
      })
    })
    .then((res) => res.json())
    .then((data) => {
      renderDriverPOC(data.poc);
      showToast('Driver POC published for students!');
    })
    .catch(() => showToast('Failed to save POC.'));
  });
}

if (driverPocClearBtn) {
  driverPocClearBtn.addEventListener('click', () => {
    if (!isDriverAuthenticated()) return;
    fetch('/api/driver/poc', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        pin: getStoredDriverPin(),
        driver_name: '',
        contact_info: ''
      })
    })
    .then((res) => res.json())
    .then((data) => {
      renderDriverPOC(data.poc);
      showToast('Driver POC cleared');
    })
    .catch(() => showToast('Failed to clear POC.'));
  });
}

async function sendDriverAlert(title, detail, toastMessage, location = null) {
  try {
    const response = await fetch('/api/driver/broadcast', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ 
        pin: getStoredDriverPin(), 
        current_stop: location || currentVanLocation || 'Shuttle Route', 
        next_stop: location || 'Shuttle Route', 
        eta_mins: 0, 
        title: title, 
        detail: detail, 
        location: location || currentVanLocation 
      })
    });
    if (!response.ok) throw new Error('Alert failed');
    showToast(toastMessage);
  } catch (err) {
    showToast('Failed to broadcast alert');
  }
}

function showDestinationStep(location) {
  currentVanLocation = location;
  const prompt = document.querySelector('#location-prompt');
  if (prompt) prompt.textContent = `Step 2: The Van is going to... (currently at ${location})`;
  const destControls = document.querySelector('#destination-controls');
  if (destControls) destControls.classList.add('visible');
  const otherLoc = document.querySelector('#other-location');
  if (otherLoc) otherLoc.classList.remove('visible');

  sendDriverAlert(
    `045/048 Van is at ${location}`,
    `045/048 Van has arrived at ${location}. Active pickup requests here completed.`,
    `Van location sent: ${location}`,
    location
  );
}

function resetLocationWorkflow() {
  currentVanLocation = '';
  const prompt = document.querySelector('#location-prompt');
  if (prompt) prompt.textContent = 'Step 1: Choose where the Van is now.';
  const destControls = document.querySelector('#destination-controls');
  if (destControls) destControls.classList.remove('visible');
  const otherLoc = document.querySelector('#other-location');
  if (otherLoc) otherLoc.classList.remove('visible');
  const otherDest = document.querySelector('#other-destination');
  if (otherDest) otherDest.classList.remove('visible');
  const otherLocInput = document.querySelector('#other-location-input');
  if (otherLocInput) otherLocInput.value = '';
  const otherDestInput = document.querySelector('#other-destination-input');
  if (otherDestInput) otherDestInput.value = '';
}

function sendLocationUpdate(destination) {
  const currentLocation = currentVanLocation || 'Van Route';
  sendDriverAlert(
    `045/048 Van En Route to ${destination}`,
    `The Van is leaving ${currentLocation} and heading to ${destination}.`,
    `Alert sent: Heading to ${destination}`,
    currentLocation
  ).then(resetLocationWorkflow);
}

document.querySelectorAll('#driver-view .location-btn').forEach((button) => button.addEventListener('click', () => {
  if (!isDriverAuthenticated()) return;
  const otherLocation = document.querySelector('#other-location');
  if (button.dataset.location === 'Other') {
    if (otherLocation) {
      otherLocation.classList.toggle('visible');
      if (otherLocation.classList.contains('visible')) {
        const input = document.querySelector('#other-location-input');
        if (input) input.focus();
      }
    }
    return;
  }
  showDestinationStep(button.dataset.location);
}));

const sendOtherAlertBtn = document.querySelector('#send-other-alert');
if (sendOtherAlertBtn) {
  sendOtherAlertBtn.addEventListener('click', () => {
    if (!isDriverAuthenticated()) return;
    const input = document.querySelector('#other-location-input');
    const location = input ? input.value.trim() : '';
    if (!location) {
      if (input) input.focus();
      return;
    }
    showDestinationStep(location);
  });
}

document.querySelectorAll('#driver-view .destination-btn').forEach((button) => button.addEventListener('click', () => {
  if (!isDriverAuthenticated()) return;
  const otherDestination = document.querySelector('#other-destination');
  if (button.dataset.location === 'Other') {
    if (otherDestination) {
      otherDestination.classList.toggle('visible');
      if (otherDestination.classList.contains('visible')) {
        const input = document.querySelector('#other-destination-input');
        if (input) input.focus();
      }
    }
    return;
  }
  sendLocationUpdate(button.dataset.location);
}));

const sendDestOtherBtn = document.querySelector('#send-destination-other');
if (sendDestOtherBtn) {
  sendDestOtherBtn.addEventListener('click', () => {
    if (!isDriverAuthenticated()) return;
    const input = document.querySelector('#other-destination-input');
    const destination = input ? input.value.trim() : '';
    if (!destination) {
      if (input) input.focus();
      return;
    }
    sendLocationUpdate(destination);
  });
}

if (departureAlertButton) {
  departureAlertButton.addEventListener('click', () => {
    if (!isDriverAuthenticated()) return;
    const activeOption = document.querySelector('.departure-option.active');
    const waitTime = activeOption ? activeOption.dataset.wait : '5';
    const departure = new Date(Date.now() + Number(waitTime) * 60000);
    const departureLabel = departure.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
    
    sendDriverAlert(
      `045/048 Van departs at ${departureLabel}`,
      `The driver expects to depart in about ${waitTime} minutes.`,
      `Departure alert sent: ${departureLabel}`
    );
  });
}

if (vanFullReturnButton) {
  vanFullReturnButton.addEventListener('click', () => {
    if (!isDriverAuthenticated()) return;
    sendDriverAlert(
      '045/048 Van is currently full',
      'The van is at capacity. The driver will return shortly for more rides.',
      'Alert sent: Van is full'
    );
  });
}

if (noRidesButton) {
  noRidesButton.addEventListener('click', () => {
    if (!isDriverAuthenticated()) return;
    sendDriverAlert(
      'No rides available right now',
      'Service is paused. Please check back later for the next available ride.',
      'Alert sent: Service paused'
    );
  });
}

document.querySelectorAll('.departure-option').forEach((button) => button.addEventListener('click', () => {
  if (!isDriverAuthenticated()) return;
  document.querySelectorAll('.departure-option').forEach((option) => option.classList.remove('active'));
  button.classList.add('active');
  if (departureTime) departureTime.textContent = `${button.dataset.wait} min`;
}));

function submitStudentRideRequest(pickup, dropoff) {
  const nameInput = document.querySelector('#student-rider-name');
  const name = nameInput ? nameInput.value.trim() : '';
  
  if (!name) {
    showToast('⚠️ Please enter your name first!');
    if (nameInput) nameInput.focus();
    return;
  }

  fetch('/api/request-ride', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name: name, pickup: pickup, dropoff: dropoff })
  })
  .then((res) => res.json())
  .then(() => {
    showToast(`🚖 Ride Requested: Pickup at ${pickup} → ${dropoff}`);
    studentSelectedPickup = '';
    const dropoffSection = document.querySelector('#student-dropoff-step');
    if (dropoffSection) dropoffSection.classList.remove('visible');
    const otherPickupBox = document.querySelector('#student-other-pickup-box');
    if (otherPickupBox) otherPickupBox.classList.remove('visible');
    const otherDropoffBox = document.querySelector('#student-other-dropoff-box');
    if (otherDropoffBox) otherDropoffBox.classList.remove('visible');
    document.querySelectorAll('.student-req-pickup-btn').forEach(b => b.classList.remove('active'));
  })
  .catch(() => {
    showToast('Error requesting ride.');
  });
}

document.querySelectorAll('.student-req-pickup-btn').forEach((btn) => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.student-req-pickup-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');

    const loc = btn.dataset.loc;
    const otherBox = document.querySelector('#student-other-pickup-box');
    const dropoffStep = document.querySelector('#student-dropoff-step');
    const prompt = document.querySelector('#student-dropoff-prompt');

    if (loc === 'Other') {
      if (otherBox) otherBox.classList.add('visible');
      if (dropoffStep) dropoffStep.classList.remove('visible');
      const input = document.querySelector('#student-other-pickup-input');
      if (input) input.focus();
    } else {
      if (otherBox) otherBox.classList.remove('visible');
      studentSelectedPickup = loc;
      if (prompt) prompt.textContent = `STEP 2: WHERE DO YOU NEED TO GO? (Pickup selected: ${loc})`;
      if (dropoffStep) dropoffStep.classList.add('visible');
    }
  });
});

const setOtherPickupBtn = document.querySelector('#student-set-other-pickup');
if (setOtherPickupBtn) {
  setOtherPickupBtn.addEventListener('click', () => {
    const input = document.querySelector('#student-other-pickup-input');
    const loc = input ? input.value.trim() : '';
    if (!loc) {
      if (input) input.focus();
      return;
    }
    studentSelectedPickup = loc;
    const prompt = document.querySelector('#student-dropoff-prompt');
    const dropoffStep = document.querySelector('#student-dropoff-step');
    if (prompt) prompt.textContent = `STEP 2: WHERE DO YOU NEED TO GO? (Pickup selected: ${loc})`;
    if (dropoffStep) dropoffStep.classList.add('visible');
  });
}

document.querySelectorAll('.student-req-dropoff-btn').forEach((btn) => {
  btn.addEventListener('click', () => {
    const dropoffLoc = btn.dataset.loc;
    const otherDropoffBox = document.querySelector('#student-other-dropoff-box');

    if (dropoffLoc === 'Other') {
      if (otherDropoffBox) otherDropoffBox.classList.add('visible');
      const input = document.querySelector('#student-other-dropoff-input');
      if (input) input.focus();
    } else {
      if (otherDropoffBox) otherDropoffBox.classList.remove('visible');
      submitStudentRideRequest(studentSelectedPickup || 'Campus', dropoffLoc);
    }
  });
});

const sendCustomRideBtn = document.querySelector('#student-send-custom-ride');
if (sendCustomRideBtn) {
  sendCustomRideBtn.addEventListener('click', () => {
    const input = document.querySelector('#student-other-dropoff-input');
    const dropoff = input ? input.value.trim() : '';
    if (!dropoff) {
      if (input) input.focus();
      return;
    }
    submitStudentRideRequest(studentSelectedPickup || 'Campus', dropoff);
  });
}

if (headingToVanForm) {
  headingToVanForm.addEventListener('submit', (event) => {
    event.preventDefault();
    const name = headingToVanForm.elements.name.value.trim();
    const email = headingToVanForm.elements.email.value.trim().toLowerCase();
    if (!name || !email) return;
    fetch('/api/student/heading-to-van', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, email })
    }).then(() => {
      headingToVanForm.reset();
      showToast("Driver notified you're heading to the van!");
    });
  });
}

if (clearAllWalkersBtn) {
  clearAllWalkersBtn.addEventListener('click', () => {
    if (!isDriverAuthenticated()) return;
    fetch('/api/driver/clear-walking', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ pin: getStoredDriverPin(), request_id: 0, new_status: '' })
    }).then(() => showToast('All incoming walkers cleared'));
  });
}

function showToast(message) {
  if (!toast) return;
  toast.textContent = message;
  toast.classList.add('show');
  window.setTimeout(() => toast.classList.remove('show'), 3500);
}

function switchView(view) {
  document.querySelectorAll('.view').forEach((section) => section.classList.remove('active-view'));
  const targetView = document.querySelector(`#${view}-view`);
  if (targetView) targetView.classList.add('active-view');
  document.querySelectorAll('[data-view]').forEach((button) => button.classList.toggle('active', button.dataset.view === view));
  const pageTitle = document.querySelector('#page-title');
  if (pageTitle) {
    pageTitle.innerHTML = view === 'driver' ? 'Monitor the App and be Accurate <span>✦</span>' : 'Your ride, on your time <span>✦</span>';
  }
}

function renderDriverWalkers(walkers) {
  if (!driverWalkerList) return;
  if (!walkers || !walkers.length) {
    driverWalkerList.innerHTML = '<p class="access-empty">No students currently walking to the van.</p>';
    return;
  }

  driverWalkerList.innerHTML = walkers.map((walker) => `
    <div class="driver-request-entry" style="border-left: 3px solid var(--coral); padding-left: 10px;">
      <div class="request-avatar" style="background:#fbe3db; color:var(--coral);">${(walker.name || '?').slice(0, 2).toUpperCase()}</div>
      <div class="driver-request-info">
        <strong>${walker.name}</strong>
        <span>Status: <b>Walking to van right now</b></span>
      </div>
      <button class="primary-btn arrive-walker-btn" data-walkerid="${walker.id}" style="padding: 6px 10px; font-size: 11px; margin-left: auto; background: var(--mint-deep);">Boarded / Arrived</button>
    </div>
  `).join('');

  driverWalkerList.querySelectorAll('.arrive-walker-btn').forEach((btn) => {
    btn.addEventListener('click', () => {
      const walkerId = btn.dataset.walkerid;
      fetch('/api/driver/remove-walker', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ pin: getStoredDriverPin(), walker_id: parseInt(walkerId, 10) })
      }).then(() => showToast('Student marked arrived'));
    });
  });
}

function renderDriverRequests(requests) {
  if (!driverRequestList) return;
  if (waitingCount) waitingCount.innerHTML = `${requests.length} <small>students</small>`;

  if (!requests.length) {
    driverRequestList.innerHTML = '<p class="access-empty">No active student pickup requests right now.</p>';
    return;
  }

  driverRequestList.innerHTML = requests.map((request) => `
    <div class="driver-request-entry">
      <div class="request-avatar">${(request[1] || '?').slice(0, 2).toUpperCase()}</div>
      <div class="driver-request-info">
        <strong>${request[1]}</strong>
        <span>Pickup: <b>${request[2]}</b> &rarr; Destination: <b>${request[3]}</b></span>
      </div>
      <button class="primary-btn complete-request-btn" data-reqid="${request[0]}" style="padding: 6px 10px; font-size: 11px; margin-left: auto;">Picked Up</button>
    </div>
  `).join('');

  driverRequestList.querySelectorAll('.complete-request-btn').forEach((btn) => {
    btn.addEventListener('click', () => {
      const reqId = btn.dataset.reqid;
      fetch('/api/driver/complete-request', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ pin: getStoredDriverPin(), request_id: parseInt(reqId, 10) })
      }).then(() => showToast('Request marked picked up'));
    });
  });
}

function syncInitialData() {
  fetch('/api/status', { cache: 'no-store' })
    .then((res) => res.json())
    .then((data) => {
      if (data.manifest) renderDriverRequests(data.manifest);
      if (data.walkers) renderDriverWalkers(data.walkers);
      if (data.poc) renderDriverPOC(data.poc);
      if (data.walking_count !== undefined && walkingCount) {
        walkingCount.innerHTML = `${data.walking_count} <small>students</small>`;
      }
    })
    .catch(() => {});

  fetch('/api/alerts/latest', { cache: 'no-store' })
    .then((res) => res.json())
    .then((alert) => {
      if (alert && alert.id) {
        if (studentAlertTitle) studentAlertTitle.textContent = displayVanName(alert.title);
        if (studentAlertDetail) studentAlertDetail.textContent = displayVanName(alert.detail);
        if (studentAlertTime) studentAlertTime.textContent = 'Active';
      }
    })
    .catch(() => {});
}

setInterval(syncInitialData, 4000);
